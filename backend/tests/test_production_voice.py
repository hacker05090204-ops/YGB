from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone

import backend.voice.production_voice as production_voice
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
