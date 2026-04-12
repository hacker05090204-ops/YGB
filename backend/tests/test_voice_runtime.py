import logging

from backend.api.system_status import _get_voice_status
from backend.assistant import voice_runtime as vr


def test_phase12_whisper_availability_false_when_missing(monkeypatch, caplog):
    original_import_optional_dependency = vr._import_optional_dependency
    monkeypatch.setattr(
        vr,
        "_import_optional_dependency",
        lambda name: None if name == "whisper" else original_import_optional_dependency(name),
    )

    with caplog.at_level(logging.WARNING):
        whisper = vr.WhisperSTT()

    assert whisper.available is False
    assert whisper.dependency_available is False
    assert whisper.status()["available"] is False
    assert whisper.transcribe("sample.wav") == ""
    assert any("Whisper STT unavailable" in record.message for record in caplog.records)


def test_phase12_pyttsx_availability_false_when_missing(monkeypatch, caplog):
    original_import_optional_dependency = vr._import_optional_dependency
    monkeypatch.setattr(
        vr,
        "_import_optional_dependency",
        lambda name: None if name == "pyttsx3" else original_import_optional_dependency(name),
    )

    with caplog.at_level(logging.WARNING):
        tts = vr.PyttsxTTS()

    assert tts.available is False
    assert tts.dependency_available is False
    assert tts.status()["available"] is False
    assert tts.speak("hello world") is False
    assert any("Local pyttsx3 TTS unavailable" in record.message for record in caplog.records)


def test_phase12_browser_relay_false_without_playwright(monkeypatch):
    monkeypatch.setenv("YGB_BROWSER_RUNTIME", "playwright")
    monkeypatch.setattr(vr, "_import_optional_dependency", lambda name: None)

    capabilities = vr.probe_microphone_capabilities()

    assert capabilities["browser_relay_available"] is False
    assert capabilities["playwright_available"] is False
    assert capabilities["dependency_status"]["playwright"] is False
    assert capabilities["local_capture_available"] is False


def test_phase12_voice_runtime_degrades_instead_of_crashing_when_deps_missing(monkeypatch):
    monkeypatch.setattr(
        "impl_v1.training.voice.stt_adapter.get_stt_status",
        lambda: {
            "stt_status": "DEGRADED",
            "browser_relay_available": False,
            "local_only": True,
        },
    )

    class _FakeTTS:
        def get_stats(self):
            return {
                "status": "ERROR",
                "active_provider": "UNAVAILABLE",
                "privacy_mode": False,
                "total_spoken": 0,
                "total_interrupted": 0,
                "total_errors": 0,
                "provider_health": {"reachable": False, "reason": "missing_deps"},
                "stream_health": {},
            }

    monkeypatch.setattr("impl_v1.training.voice.tts_streaming.TTSEngine", _FakeTTS)
    monkeypatch.setattr(
        "impl_v1.training.voice.voice_metrics.get_voice_health",
        lambda: {"total_commands": 0, "success_rate": 0.0, "slo_met": False},
    )
    monkeypatch.setattr(vr, "_import_optional_dependency", lambda name: None)

    status = _get_voice_status()

    assert status["pipeline_status"] == "OFFLINE"
    assert status["microphone"]["browser_relay_available"] is False
    assert status["microphone"]["whisper_available"] is False
    assert status["microphone"]["tts_available"] is False
    assert status["stt"]["runtime"]["available"] is False
    assert status["tts"]["runtime"]["available"] is False
