import asyncio
import base64
import io
import math
import wave

from api import voice_gateway
from backend.training import stt_dataset_collector as collector


def _make_wav_bytes(duration_sec=0.6, sample_rate=16000):
    frame_count = int(duration_sec * sample_rate)
    payload = io.BytesIO()
    with wave.open(payload, "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        frames = bytearray()
        for idx in range(frame_count):
            sample = int(12000 * math.sin(2 * math.pi * 220 * idx / sample_rate))
            frames.extend(int(sample).to_bytes(2, byteorder="little", signed=True))
        wav_file.writeframes(bytes(frames))
    return payload.getvalue()


class _FakeAudit:
    def __init__(self):
        self.entries = []

    def log(self, **kwargs):
        self.entries.append(kwargs)


def _redirect_stt_storage(monkeypatch, tmp_path):
    monkeypatch.setattr(collector, "resolve_path", lambda category: tmp_path / category)
    monkeypatch.setattr(
        collector,
        "get_storage_topology",
        lambda: {"active_root": str(tmp_path), "status": "PRIMARY"},
    )


def test_save_sample_persists_real_wav_and_manifest(tmp_path, monkeypatch):
    _redirect_stt_storage(monkeypatch, tmp_path)

    result = collector.save_sample(
        audio_bytes=_make_wav_bytes(),
        transcript="hello offline model",
        user_id="user-1",
        device_id="browser-1",
        language="en-US",
        provider="BROWSER_WEBSPEECH",
    )

    assert result["accepted"] is True
    assert (tmp_path / "dataset" / "stt" / "stt_manifest.jsonl").exists()
    assert (tmp_path / "dataset" / "stt" / "stt_dataset_status.json").exists()

    status = collector.get_dataset_status()
    assert status["sample_count"] == 1
    assert status["languages"]["en-US"] == 1
    assert status["providers"]["BROWSER_WEBSPEECH"] == 1
    assert status["training_ready"] is False


def test_upload_stt_sample_endpoint_appends_dataset_entry(tmp_path, monkeypatch):
    _redirect_stt_storage(monkeypatch, tmp_path)
    audit = _FakeAudit()
    monkeypatch.setattr(voice_gateway, "_get_audit", lambda: audit)

    req = voice_gateway.STTSampleRequest(
        audio_wav_b64=base64.b64encode(_make_wav_bytes()).decode("ascii"),
        transcript="collect this sample",
        device_id="browser-2",
        language="en-US",
        provider="BROWSER_WEBSPEECH",
    )

    result = asyncio.run(voice_gateway.upload_stt_sample(req, user={"sub": "user-2"}))

    assert result["accepted"] is True
    assert result["dataset"]["sample_count"] == 1
    assert audit.entries[-1]["intent"] == "STT_SAMPLE_UPLOAD"
    assert audit.entries[-1]["result"] == "ACCEPTED"
