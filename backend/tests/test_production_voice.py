from __future__ import annotations

import logging
import struct
from types import SimpleNamespace
from dataclasses import dataclass
from datetime import datetime, timezone

import backend.voice.production_voice as production_voice
from backend.voice.vad import EnergyVAD, detect_segments, strip_silence
from backend.assistant.query_router import ResearchResult, ResearchStatus, VoiceMode
from backend.voice.streaming_pipeline import AudioFrame, SynthesisResult, Transcript
from scripts.device_manager import DeviceConfiguration


class _SequentialSTT:
    def __init__(self, texts: list[str]) -> None:
        self._texts = list(texts)
        self.available = True
        self.warning = ""

    def transcribe(self, audio, *, language_hint=None) -> Transcript:
        text = self._texts.pop(0)
        return Transcript(
            text=text,
            language=language_hint or "en",
            confidence=0.95,
            latency_ms=1.25,
        )


class _FakeTTS:
    available = True
    warning = ""

    def synthesize(self, text: str, language: str = "en") -> SynthesisResult:
        return SynthesisResult(audio=text.encode("utf-8"), provider=f"fake:{language}", latency_ms=0.5)


class _CountingSTT:
    def __init__(self) -> None:
        self.calls = 0
        self.available = True
        self.warning = ""

    def transcribe(self, audio, *, language_hint=None) -> Transcript:
        self.calls += 1
        return Transcript(
            text="speech",
            language=language_hint or "en",
            confidence=0.9,
            latency_ms=0.5,
        )


@dataclass
class _FakeResearchPipeline:
    def search(self, query: str) -> ResearchResult:
        summary = f"Answer for: {query}"
        return ResearchResult(
            query=query,
            status=ResearchStatus.SUCCESS,
            title=query,
            summary=summary,
            source="unit-test",
            key_terms=("answer",),
            word_count=len(summary.split()),
            elapsed_ms=2.0,
            mode=VoiceMode.RESEARCH,
            timestamp=datetime.now(timezone.utc).isoformat(),
            query_result=None,
        )


def _device_configuration(*, selected_device: str, total_memory_gb: float) -> DeviceConfiguration:
    return DeviceConfiguration(
        requested_device=selected_device,
        selected_device=selected_device,
        torch_device="cuda:0" if selected_device == "cuda" else selected_device,
        device_name=f"test-{selected_device}",
        accelerator=selected_device,
        distributed_backend="nccl" if selected_device == "cuda" else "gloo",
        mixed_precision="fp16" if selected_device == "cuda" else "fp32",
        amp_enabled=selected_device == "cuda",
        bf16_supported=False,
        pin_memory=selected_device == "cuda",
        non_blocking=selected_device == "cuda",
        supports_distributed_training=selected_device == "cuda",
        is_colab=False,
        torch_available=True,
        torch_version="test",
        cuda_available=selected_device == "cuda",
        mps_available=selected_device == "mps",
        gpu_count=1 if selected_device == "cuda" else 0,
        total_memory_gb=total_memory_gb,
        cuda_version="12.1" if selected_device == "cuda" else "",
        fallback_reason="",
    )


def _pcm16(values: list[int]) -> bytes:
    return b"".join(struct.pack("<h", value) for value in values)


def test_smoke_probe_gracefully_reports_missing_optional_dependencies(monkeypatch, caplog):
    monkeypatch.setattr(production_voice, "_import_optional_dependency", lambda name: None)
    monkeypatch.setattr(
        production_voice,
        "_resolve_executable",
        lambda explicit_path=None, *, env_names=(), candidates=(): None,
    )

    for env_name in (
        "YGB_FASTER_WHISPER_MODEL",
        "FASTER_WHISPER_MODEL_PATH",
        "YGB_PIPER_MODEL",
        "PIPER_MODEL",
        "YGB_PIPER_MODEL_EN",
        "YGB_PIPER_MODEL_HI",
        "YGB_PIPER_MODEL_MR",
    ):
        monkeypatch.delenv(env_name, raising=False)

    with caplog.at_level(logging.WARNING):
        payload = production_voice.smoke_probe()

    assert payload["stt"]["available"] is False
    assert payload["tts"]["available"] is False
    assert payload["pipeline"]["initialized"] is True
    assert payload["pipeline"]["degraded"] is True
    assert any("unavailable" in record.message.lower() for record in caplog.records)


def test_pipeline_returns_observable_stt_failure_when_unavailable(monkeypatch):
    monkeypatch.setattr(production_voice, "_import_optional_dependency", lambda name: None)
    stt = production_voice.FasterWhisperSTT()
    pipeline = production_voice.ProductionVoicePipeline(stt=stt, tts=_FakeTTS())

    result = pipeline.process_audio(
        AudioFrame(pcm16=b"\x01\x02", sample_rate=16000),
        synthesize_response=False,
    )

    assert result.status == "error"
    assert result.route_mode == "ERROR"
    assert "STT unavailable" in result.response_text
    assert result.warnings


def test_vad_detects_segments_and_strips_silence():
    silence = [0] * 3200
    speech = [6000] * 4800
    pcm = _pcm16(silence + speech + silence)

    vad = EnergyVAD(
        frame_ms=20,
        hop_ms=10,
        energy_threshold_db=-30.0,
        min_speech_ms=60,
        min_silence_ms=80,
        padding_ms=10,
    )
    segments = detect_segments(pcm, 16000, vad=vad)
    stripped = strip_silence(pcm, 16000, vad=vad)

    assert len(segments) == 1
    assert 0 < len(stripped) < len(pcm)


def test_pipeline_returns_no_speech_error_after_vad_stripping():
    stt = _CountingSTT()
    pipeline = production_voice.ProductionVoicePipeline(
        stt=stt,
        tts=_FakeTTS(),
        vad=EnergyVAD(
            frame_ms=20,
            hop_ms=10,
            energy_threshold_db=-25.0,
            min_speech_ms=80,
            min_silence_ms=80,
            padding_ms=10,
        ),
        min_voiced_duration_ms=80,
    )

    silence = AudioFrame(pcm16=b"\x00\x00" * 16000, sample_rate=16000)
    result = pipeline.process_audio(silence, synthesize_response=False)

    assert result.status == "error"
    assert result.route_mode == "ERROR"
    assert "No speech detected" in result.response_text
    assert stt.calls == 0
    assert result.metrics["vad_output_duration_ms"] == 0.0


def test_faster_whisper_transcribe_returns_metadata_and_retries_without_vad_filter(monkeypatch, tmp_path):
    model_path = tmp_path / "model.bin"
    model_path.write_bytes(b"model")
    calls: list[dict[str, object]] = []

    class _FakeWhisperModel:
        def __init__(self, model, device, compute_type):
            self.model = model
            self.device = device
            self.compute_type = compute_type

        def transcribe(self, audio_source, language=None, beam_size=1, **kwargs):
            calls.append({"audio_source": audio_source, "language": language, "beam_size": beam_size, **kwargs})
            if kwargs.get("vad_filter"):
                raise TypeError("unexpected keyword argument 'vad_filter'")
            return [SimpleNamespace(text="hello world")], SimpleNamespace(language="en", language_probability=0.87)

    monkeypatch.setattr(
        production_voice,
        "_import_optional_dependency",
        lambda name: SimpleNamespace(WhisperModel=_FakeWhisperModel),
    )

    stt = production_voice.FasterWhisperSTT(
        model_path=model_path,
        device_configuration=_device_configuration(selected_device="cpu", total_memory_gb=8.0),
    )
    payload = stt.transcribe(AudioFrame(pcm16=b"\x01\x00" * 640, sample_rate=16000))

    assert payload["text"] == "hello world"
    assert payload["language"] == "en"
    assert payload["language_probability"] == 0.87
    assert payload["transcription_time_s"] >= 0.0
    assert payload["error"] is None
    assert calls[0]["vad_filter"] is True
    assert "vad_filter" not in calls[1]


def test_piper_synthesize_returns_metadata_and_graceful_failures(monkeypatch, tmp_path):
    model_path = tmp_path / "voice.onnx"
    model_path.write_bytes(b"voice")
    binary_path = tmp_path / "piper.exe"
    binary_path.write_bytes(b"binary")

    def _successful_run(command, input, capture_output, check, timeout):
        output_file = command[command.index("--output_file") + 1]
        output_path = tmp_path / output_file.split("\\")[-1]
        if output_path.name != output_file:
            output_path = __import__("pathlib").Path(output_file)
        output_path.write_bytes(b"RIFFTEST")
        return SimpleNamespace(returncode=0, stderr=b"")

    monkeypatch.setattr(production_voice.subprocess, "run", _successful_run)
    tts = production_voice.PiperTTS(
        voice_model_path=model_path,
        binary_path=binary_path,
        device_configuration=_device_configuration(selected_device="cpu", total_memory_gb=8.0),
    )
    payload = tts.synthesize("hello world", "en")

    assert payload["output_path"] is not None
    assert payload["synthesis_time_s"] >= 0.0
    assert payload["chars_per_second"] > 0.0
    assert payload["audio"] == b"RIFFTEST"
    assert payload["error"] is None

    monkeypatch.setattr(production_voice.subprocess, "run", lambda *args, **kwargs: (_ for _ in ()).throw(OSError("boom")))
    failed = tts.synthesize("hello world", "en")

    assert failed["output_path"] is None
    assert failed["audio"] == b""
    assert "boom" in failed["error"]


def test_pipeline_normalizes_dict_stt_and_tts_payloads(tmp_path):
    class _DictSTT:
        available = True
        warning = ""

        def transcribe(self, audio, *, language_hint=None):
            return {
                "text": "What is DNS poisoning?",
                "language": language_hint or "en",
                "language_probability": 0.91,
                "transcription_time_s": 0.002,
            }

    class _DictTTS:
        available = True
        warning = ""

        def synthesize(self, text: str, language: str = "en"):
            output_path = tmp_path / "reply.wav"
            output_path.write_bytes(text.encode("utf-8"))
            return {
                "output_path": str(output_path),
                "synthesis_time_s": 0.01,
                "chars_per_second": len(text) / 0.01,
                "audio": text.encode("utf-8"),
                "provider": f"fake:{language}",
            }

    pipeline = production_voice.ProductionVoicePipeline(
        stt=_DictSTT(),
        tts=_DictTTS(),
        research_pipeline=_FakeResearchPipeline(),
    )

    result = pipeline.process_audio(AudioFrame(pcm16=b"x" * 640, sample_rate=16000))

    assert result.status == "ok"
    assert result.transcript is not None
    assert result.transcript.confidence == 0.91
    assert result.synthesis is not None
    assert result.synthesis.provider == "fake:en"
    assert result.metrics["tts_chars_per_second"] > 0.0


def test_pipeline_routes_research_and_pages_context():
    pipeline = production_voice.ProductionVoicePipeline(
        stt=_SequentialSTT(["What is DNS poisoning?", "Explain TLS encryption"]),
        tts=_FakeTTS(),
        research_pipeline=_FakeResearchPipeline(),
        context_page_size=2,
    )

    first = pipeline.process_audio(AudioFrame(pcm16=b"first", sample_rate=16000))
    second = pipeline.process_audio(AudioFrame(pcm16=b"second", sample_rate=16000))

    assert first.status == "ok"
    assert first.route_mode == VoiceMode.RESEARCH.value
    assert first.synthesis is not None
    assert first.synthesis.provider == "fake:en"

    assert second.status == "ok"
    assert second.route_mode == VoiceMode.RESEARCH.value
    assert second.synthesis is not None
    assert second.synthesis.audio == second.response_text.encode("utf-8")
    assert "[page 2/2]" in second.conversation_context
    assert "What is DNS poisoning?" not in second.conversation_context
    assert "Explain TLS encryption" in second.conversation_context


def test_pipeline_uses_reusable_disk_pager_when_cuda_vram_is_low(tmp_path):
    pipeline = production_voice.ProductionVoicePipeline(
        stt=_SequentialSTT(["What is DNS poisoning?", "Explain TLS encryption"]),
        tts=_FakeTTS(),
        research_pipeline=_FakeResearchPipeline(),
        context_page_size=2,
        device_configuration=_device_configuration(selected_device="cuda", total_memory_gb=2.0),
        context_storage_root=tmp_path,
    )

    pipeline.process_audio(AudioFrame(pcm16=b"first", sample_rate=16000))
    result = pipeline.process_audio(AudioFrame(pcm16=b"second", sample_rate=16000))
    status = pipeline.status()

    assert pipeline.context.storage_mode == "disk"
    assert pipeline.context.storage_path is not None
    assert pipeline.context.storage_path.exists()
    assert any(p.name.startswith("page_") for p in pipeline.context.storage_path.glob("page_*.jsonl"))
    assert status["context_storage_mode"] == "disk"
    assert "cuda_low_vram" in status["context_storage_reason"]
    assert "[page 2/2]" in result.conversation_context
