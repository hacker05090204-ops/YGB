import logging
import types
from pathlib import Path

import pytest

from backend.assistant import voice_runtime as vr
from backend.assistant.query_router import ResearchResult, ResearchStatus, VoiceMode
from impl_v1.training.voice.voice_executors import ExecStatus


class _FakeIntent:
    def __init__(self, command_type="QUERY_STATUS", route_mode="SECURITY", error=None):
        self.intent_id = "INT-1"
        self.command_type = command_type
        self.args = {}
        self.transcript_text = "status"
        self.route_mode = route_mode
        self.requires_confirmation = False
        self.confirmed = False
        self.executed = False
        self.error = error
        self.result = None
        self.idempotency_key = "idem-1"


class _FakeOrchestrator:
    def __init__(self, intent):
        self.intent = intent
        self.executed_result = None
        self.failed_reason = None

    def get_intent(self, intent_id):
        return self.intent if intent_id == self.intent.intent_id else None

    def confirm_intent(self, intent_id, confirmer_id):
        if intent_id != self.intent.intent_id:
            return False
        self.intent.confirmed = True
        return True

    def is_ready_to_execute(self, intent_id):
        return not self.intent.error

    def mark_executed(self, intent_id, result):
        self.intent.executed = True
        self.executed_result = result

    def mark_failed(self, intent_id, error):
        self.failed_reason = error
        self.intent.error = error


class _FakePolicy:
    class _Verdict:
        def __init__(self, value):
            self.value = value

    def __init__(self, value="ALLOWED", reason="ok"):
        self.value = value
        self.reason = reason

    def evaluate(self, command_type, args):
        return types.SimpleNamespace(
            verdict=self._Verdict(self.value),
            reason=self.reason,
        )


class _FakeAudit:
    def __init__(self):
        self.entries = []

    def log(self, **kwargs):
        self.entries.append(kwargs)


def test_execute_orchestrated_intent_runs_real_dispatch(monkeypatch):
    intent = _FakeIntent(command_type="QUERY_STATUS")
    orch = _FakeOrchestrator(intent)
    audit = _FakeAudit()

    monkeypatch.setattr(
        vr,
        "dispatch_supported_command",
        lambda command_type, args, transcript_text, voice_session=None: {
            "status": "ok",
            "output": "runtime-ok",
            "data": {"query_type": command_type},
        },
    )

    result = vr.execute_orchestrated_intent(
        orch,
        "INT-1",
        None,
        policy=_FakePolicy(),
        audit=audit,
        user_id="user-1",
        device_id="dev-1",
    )

    assert result["status"] == "ok"
    assert result["executed"] is True
    assert orch.executed_result == "runtime-ok"
    assert audit.entries[-1]["action"] == "EXECUTED"


def test_dispatch_supported_command_tracks_and_closes_voice_session(monkeypatch):
    snapshots = []

    def _fake_research(query):
        snapshots.append(vr.get_active_sessions())
        return {"status": "ok", "query": query, "message": "research-complete"}

    monkeypatch.setattr(vr, "run_research_analysis", _fake_research)

    result = vr.dispatch_supported_command(
        "RESEARCH_QUERY_INTERNAL",
        {"query": "what is dns poisoning"},
        "what is dns poisoning",
    )

    assert result["status"] == "ok"
    assert len(snapshots) == 1
    assert len(snapshots[0]) == 1
    session = next(iter(snapshots[0].values()))
    assert session["turn_count"] == 1
    assert session["ended_at"] is None
    assert vr.get_active_sessions() == {}


def test_blocked_command_creates_pending_approval_request(monkeypatch):
    monkeypatch.setattr(vr, "_command_request_log", vr.CommandRequestLog(max_entries=1000))

    result = vr.dispatch_supported_command(
        "START_SCAN",
        {"requested_by": "user-1"},
        "start scan now",
    )

    pending = vr.get_pending_command_requests()
    assert result["status"] == "blocked"
    assert result["approval_request"]["approval_status"] == "PENDING_APPROVAL"
    assert pending
    assert pending[-1].command == "START_SCAN"
    assert pending[-1].requested_by == "user-1"


def test_execute_orchestrated_intent_closes_voice_session_on_exception(monkeypatch):
    intent = _FakeIntent(command_type="QUERY_STATUS")
    orch = _FakeOrchestrator(intent)

    def _raising_dispatch(command_type, args, transcript_text, voice_session=None):
        assert len(vr.get_active_sessions()) == 1
        raise RuntimeError("dispatch exploded")

    monkeypatch.setattr(vr, "dispatch_supported_command", _raising_dispatch)

    with pytest.raises(RuntimeError, match="dispatch exploded"):
        vr.execute_orchestrated_intent(orch, "INT-1", None)

    assert vr.get_active_sessions() == {}


def test_execute_orchestrated_intent_blocks_policy():
    intent = _FakeIntent(command_type="QUERY_STATUS")
    orch = _FakeOrchestrator(intent)
    audit = _FakeAudit()

    result = vr.execute_orchestrated_intent(
        orch,
        "INT-1",
        None,
        policy=_FakePolicy(value="DENIED", reason="Policy blocked"),
        audit=audit,
        user_id="user-1",
        device_id="dev-1",
    )

    assert result["status"] == "blocked"
    assert result["gate"] == "POLICY"
    assert orch.failed_reason == "Policy blocked"
    assert audit.entries[-1]["action"] == "BLOCKED"


def test_build_voice_pipeline_status_truthful(monkeypatch):
    monkeypatch.setattr(
        "impl_v1.training.voice.stt_adapter.get_stt_status",
        lambda: {
            "stt_status": "DEGRADED",
            "browser_relay_available": False,
            "local_only": True,
        },
    )
    monkeypatch.setattr(
        vr,
        "probe_microphone_capabilities",
        lambda: {
            "browser_relay_available": True,
            "browser_runtime": "playwright",
            "local_capture_available": False,
            "local_capture_backend": None,
            "input_device_count": 0,
            "dependency_status": {
                "sounddevice": False,
                "pyaudio": False,
                "playwright": True,
            },
            "reason": "Local capture unavailable; browser transcript relay available via Playwright",
            "timestamp": "2026-03-08T00:00:00+00:00",
        },
    )

    class _FakeTTS:
        def get_stats(self):
            return {
                "status": "IDLE",
                "active_provider": "API_PROXY",
                "privacy_mode": False,
                "total_spoken": 0,
                "total_interrupted": 0,
                "total_errors": 0,
                "provider_health": {"reachable": False, "reason": "proxy_down"},
            }

    monkeypatch.setattr("impl_v1.training.voice.tts_streaming.TTSEngine", _FakeTTS)
    monkeypatch.setattr(
        "impl_v1.training.voice.voice_metrics.get_voice_health",
        lambda: {"total_commands": 1, "success_rate": 0.0, "slo_met": False},
    )

    vr.runtime_state.set("active_voice_mode", "RESEARCH")
    status = vr.build_voice_pipeline_status()

    assert status["pipeline_status"] == "DEGRADED"
    assert status["mode"] == "RESEARCH"
    assert status["microphone"]["browser_relay_available"] is True


def test_whisper_stt_init_logs_warning_and_stays_unavailable_without_dependency(monkeypatch, caplog):
    original_import_optional_dependency = vr._import_optional_dependency
    monkeypatch.setattr(
        vr,
        "_import_optional_dependency",
        lambda name: None if name == "whisper" else original_import_optional_dependency(name),
    )

    with caplog.at_level(logging.WARNING):
        whisper = vr.WhisperSTT()

    assert whisper.available is False
    assert whisper.model_path is None
    assert any("Whisper STT unavailable" in record.message for record in caplog.records)


def test_pyttxs_tts_unavailable_without_dependency(monkeypatch, caplog):
    original_import_optional_dependency = vr._import_optional_dependency
    monkeypatch.setattr(
        vr,
        "_import_optional_dependency",
        lambda name: None if name == "pyttsx3" else original_import_optional_dependency(name),
    )

    with caplog.at_level(logging.WARNING):
        tts = vr.PyttxsTTS()

    assert tts.available is False
    assert any("Local pyttsx3 TTS unavailable" in record.message for record in caplog.records)


def test_probe_microphone_capabilities_disables_browser_relay_without_playwright(monkeypatch):
    monkeypatch.setenv("YGB_BROWSER_RUNTIME", "playwright")
    monkeypatch.setattr(vr, "_import_optional_dependency", lambda name: None)

    capabilities = vr.probe_microphone_capabilities()

    assert capabilities["browser_relay_available"] is False
    assert capabilities["local_capture_available"] is False
    assert capabilities["dependency_status"]["playwright"] is False


def test_build_voice_pipeline_status_fails_gracefully_when_runtime_helpers_raise(monkeypatch, caplog):
    def _stt_boom():
        raise RuntimeError("stt exploded")

    class _BoomTTS:
        def __init__(self):
            raise RuntimeError("tts exploded")

    def _metrics_boom():
        raise RuntimeError("metrics exploded")

    def _mic_boom():
        raise RuntimeError("mic exploded")

    monkeypatch.setattr("impl_v1.training.voice.stt_adapter.get_stt_status", _stt_boom)
    monkeypatch.setattr("impl_v1.training.voice.tts_streaming.TTSEngine", _BoomTTS)
    monkeypatch.setattr("impl_v1.training.voice.voice_metrics.get_voice_health", _metrics_boom)
    monkeypatch.setattr(vr, "probe_microphone_capabilities", _mic_boom)
    monkeypatch.setattr(vr, "_import_optional_dependency", lambda name: None)

    with caplog.at_level(logging.WARNING):
        status = vr.build_voice_pipeline_status()

    assert status["pipeline_status"] == "OFFLINE"
    assert status["microphone"]["browser_relay_available"] is False
    assert status["tts"]["health"]["reachable"] is False
    assert status["stt"]["runtime"]["available"] is False
    assert any("stt exploded" in record.message for record in caplog.records)
    assert any("tts exploded" in record.message for record in caplog.records)


def test_run_research_analysis_includes_verification(monkeypatch):
    def _fake_search(self, query):
        return ResearchResult(
            query=query,
            status=ResearchStatus.SUCCESS,
            title="Latest News",
            summary="Important update from two sources.",
            source="bing.com",
            key_terms=("latest", "news"),
            word_count=5,
            elapsed_ms=12.0,
            mode=VoiceMode.RESEARCH,
            timestamp="2026-03-08T00:00:00+00:00",
        )

    def _fake_fetch(self, query):
        html = """
        <a href="https://nvd.nist.gov/vuln/detail/CVE-2024-0001">nvd</a>
        <a href="https://owasp.org/www-project-top-ten/">owasp</a>
        """
        return html, "bing.com"

    monkeypatch.setattr(vr.ResearchSearchPipeline, "search", _fake_search)
    monkeypatch.setattr(vr.ResearchSearchPipeline, "_fetch_search_html", _fake_fetch)

    result = vr.run_research_analysis("what's latest security news")

    assert result["status"] == "ok"
    assert result["research"]["summary"] == "Important update from two sources."
    assert result["research"]["query_result"] is None
    assert result["verification"]["confidence"] in {"LIKELY", "UNVERIFIED"}
    assert len(result["verification"]["sources"]) >= 2


def test_dispatch_supported_command_runs_host_action(monkeypatch):
    monkeypatch.setenv("YGB_APPROVAL_SECRET", "voice-runtime-secret")
    monkeypatch.setattr(
        "backend.governance.host_action_governor.HostActionGovernor.validate_request",
        lambda self, session_id, action, args: {
            "allowed": True,
            "canonical_app": "notepad",
            "command": [r"C:\Windows\System32\notepad.exe"],
        },
    )
    monkeypatch.setattr(
        "impl_v1.training.voice.voice_executors.AppRunnerExecutor.execute",
        lambda self, intent_id, action, app_name, launch_command=None: types.SimpleNamespace(
            status=ExecStatus.SUCCESS,
            output="Launched notepad",
            executor="AppRunnerExecutor",
            audit_hash="audit-hash",
            execution_ms=4.2,
        ),
    )

    result = vr.dispatch_supported_command(
        "LAUNCH_APP",
        {
            "app": "notepad",
            "host_session_id": "HAG-1",
            "_intent_id": "INT-HOST",
        },
        "open notepad",
    )

    assert result["status"] == "ok"
    assert result["output"] == "Launched notepad"
    assert result["executor"] == "AppRunnerExecutor"


def test_set_objective_blocks_second_until_complete(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "backend.assistant.task_focus.FOCUS_STATE_PATH",
        Path(tmp_path / "focus.json"),
    )

    first = vr.dispatch_supported_command(
        "SET_OBJECTIVE",
        {"title": "Finish project A", "requested_by": "user-1"},
        "focus on finish project A",
    )
    second = vr.dispatch_supported_command(
        "SET_OBJECTIVE",
        {"title": "Start project B", "requested_by": "user-1"},
        "focus on start project B",
    )

    assert first["status"] == "ok"
    assert second["status"] == "blocked"
    assert "ACTIVE_OBJECTIVE_IN_PROGRESS" in second["message"]


def test_record_objective_progress_appends_grounded_step(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "backend.assistant.task_focus.FOCUS_STATE_PATH",
        Path(tmp_path / "focus.json"),
    )

    vr.dispatch_supported_command(
        "SET_OBJECTIVE",
        {"title": "Inspect runtime", "requested_by": "user-1"},
        "focus on inspect runtime",
    )

    intent = types.SimpleNamespace(command_type="QUERY_STATUS", route_mode="SECURITY")
    vr.record_objective_progress(
        intent,
        {"status": "ok", "output": "Runtime collected successfully"},
    )

    from backend.assistant.task_focus import TaskFocusManager

    snapshot = TaskFocusManager(state_path=tmp_path / "focus.json").status_snapshot()
    assert snapshot["active_objective"]["steps"][-1]["summary"] == "Runtime collected successfully"
