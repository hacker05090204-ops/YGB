"""
STT dataset collector and local training bridge.

Builds a real on-disk supervised dataset from browser voice sessions:
  - stores WAV files
  - appends JSONL manifest entries
  - reports dataset/training quality
  - can trigger local Conformer training when enough samples exist
"""

from __future__ import annotations

import io
import json
import logging
import os
import uuid
import wave
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, UTC
from pathlib import Path
from typing import Any, Dict, List, Tuple

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

try:
    from backend.storage.tiered_storage import get_storage_topology, resolve_path
except Exception:  # pragma: no cover
    get_storage_topology = None
    resolve_path = None


def _dataset_root() -> Path:
    if resolve_path:
        try:
            return resolve_path("dataset") / "stt"
        except Exception:
            pass
    return PROJECT_ROOT / "data" / "stt"


def _audio_root() -> Path:
    root = _dataset_root() / "audio"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _manifest_path() -> Path:
    root = _dataset_root()
    root.mkdir(parents=True, exist_ok=True)
    return root / "stt_manifest.jsonl"


def _status_path() -> Path:
    root = _dataset_root()
    root.mkdir(parents=True, exist_ok=True)
    return root / "stt_dataset_status.json"


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _min_samples_for_training() -> int:
    try:
        return max(20, int(os.environ.get("YGB_STT_MIN_TRAIN_SAMPLES", "200")))
    except Exception:
        return 200


def _sanitize_transcript(text: str) -> str:
    cleaned = " ".join((text or "").strip().split())
    return cleaned[:280]


def _inspect_wav(audio_bytes: bytes) -> Tuple[bool, Dict[str, Any] | str]:
    try:
        with wave.open(io.BytesIO(audio_bytes), "rb") as wf:
            frames = wf.getnframes()
            sample_rate = wf.getframerate()
            channels = wf.getnchannels()
            sample_width = wf.getsampwidth()
        duration_sec = frames / max(sample_rate, 1)
        return True, {
            "frames": frames,
            "sample_rate": sample_rate,
            "channels": channels,
            "sample_width": sample_width,
            "duration_sec": round(duration_sec, 4),
        }
    except Exception as exc:
        return False, type(exc).__name__


@dataclass(frozen=True)
class SampleDecision:
    accepted: bool
    reason: str
    details: Dict[str, Any]


def _evaluate_sample(audio_bytes: bytes, transcript: str) -> SampleDecision:
    transcript = _sanitize_transcript(transcript)
    if len(transcript) < 2:
        return SampleDecision(False, "TRANSCRIPT_TOO_SHORT", {})

    ok, inspected = _inspect_wav(audio_bytes)
    if not ok:
        return SampleDecision(False, f"INVALID_WAV:{inspected}", {})

    duration_sec = float(inspected["duration_sec"])
    if duration_sec < 0.35:
        return SampleDecision(False, "AUDIO_TOO_SHORT", inspected)
    if duration_sec > 20.0:
        return SampleDecision(False, "AUDIO_TOO_LONG", inspected)
    if inspected["channels"] < 1:
        return SampleDecision(False, "NO_AUDIO_CHANNELS", inspected)

    return SampleDecision(True, "ACCEPTED", inspected)


def _write_status(status: Dict[str, Any]) -> None:
    path = _status_path()
    path.write_text(json.dumps(status, indent=2), encoding="utf-8")


def _read_manifest_entries() -> List[Dict[str, Any]]:
    path = _manifest_path()
    if not path.exists():
        return []
    entries: List[Dict[str, Any]] = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return entries


def get_dataset_status() -> Dict[str, Any]:
    entries = _read_manifest_entries()
    sample_count = len(entries)
    total_duration_sec = round(
        sum(float(entry.get("duration_sec", 0.0) or 0.0) for entry in entries), 4
    )
    transcript_lengths = [len(str(entry.get("text", ""))) for entry in entries]
    languages = Counter(str(entry.get("language", "unknown")) for entry in entries)
    providers = Counter(str(entry.get("provider", "unknown")) for entry in entries)
    users = Counter(str(entry.get("user_id", "unknown")) for entry in entries)
    topology = get_storage_topology() if get_storage_topology else {}

    quality = "EMPTY"
    if sample_count >= _min_samples_for_training():
        quality = "TRAINING_READY"
    elif sample_count >= max(10, _min_samples_for_training() // 5):
        quality = "COLLECTING"

    status = {
        "status": quality,
        "dataset_root": str(_dataset_root()),
        "manifest_path": str(_manifest_path()),
        "sample_count": sample_count,
        "min_samples_for_training": _min_samples_for_training(),
        "training_ready": sample_count >= _min_samples_for_training(),
        "total_duration_sec": total_duration_sec,
        "total_duration_hours": round(total_duration_sec / 3600.0, 4),
        "avg_duration_sec": round(total_duration_sec / max(sample_count, 1), 4),
        "avg_transcript_chars": round(
            sum(transcript_lengths) / max(sample_count, 1), 2
        ),
        "max_transcript_chars": max(transcript_lengths) if transcript_lengths else 0,
        "languages": dict(languages),
        "providers": dict(providers),
        "unique_users": len(users),
        "last_sample_at": entries[-1].get("captured_at") if entries else None,
        "storage_topology": topology,
        "checked_at": _now(),
    }
    _write_status(status)
    return status


def save_sample(
    *,
    audio_bytes: bytes,
    transcript: str,
    user_id: str,
    device_id: str,
    language: str = "en-US",
    provider: str = "BROWSER_WEBSPEECH",
) -> Dict[str, Any]:
    transcript = _sanitize_transcript(transcript)
    decision = _evaluate_sample(audio_bytes, transcript)
    sample_id = f"STT-{uuid.uuid4().hex[:16].upper()}"

    if not decision.accepted:
        status = get_dataset_status()
        return {
            "accepted": False,
            "sample_id": sample_id,
            "reason": decision.reason,
            "details": decision.details,
            "dataset": status,
        }

    audio_path = _audio_root() / f"{sample_id}.wav"
    with open(audio_path, "wb") as f:
        f.write(audio_bytes)

    entry = {
        "audio": str(audio_path),
        "text": transcript,
        "sample_id": sample_id,
        "user_id": user_id,
        "device_id": device_id,
        "language": language,
        "provider": provider,
        "captured_at": _now(),
        **decision.details,
    }

    with open(_manifest_path(), "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=True) + "\n")

    status = get_dataset_status()
    return {
        "accepted": True,
        "sample_id": sample_id,
        "audio_path": str(audio_path),
        "manifest_path": str(_manifest_path()),
        "details": decision.details,
        "dataset": status,
    }


def _write_subset_manifest(path: Path, entries: List[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for entry in entries:
            f.write(json.dumps(entry, ensure_ascii=True) + "\n")


def train_local_stt_model(
    *,
    epochs: int = 3,
    batch_size: int = 4,
    val_ratio: float = 0.1,
) -> Dict[str, Any]:
    entries = _read_manifest_entries()
    if len(entries) < _min_samples_for_training():
        return {
            "started": False,
            "reason": "INSUFFICIENT_SAMPLES",
            "dataset": get_dataset_status(),
        }

    from torch.utils.data import DataLoader
    from impl_v1.training.voice.stt_trainer import SpeechDataset, STTTrainer, collate_fn

    train_entries: List[Dict[str, Any]] = []
    val_entries: List[Dict[str, Any]] = []
    stride = max(2, int(round(1 / max(min(val_ratio, 0.5), 0.05))))
    for idx, entry in enumerate(entries):
        if idx % stride == 0:
            val_entries.append(entry)
        else:
            train_entries.append(entry)

    if not train_entries or not val_entries:
        split = max(1, len(entries) // 10)
        val_entries = entries[:split]
        train_entries = entries[split:]

    manifests_root = _dataset_root() / "manifests"
    train_manifest = manifests_root / "train_manifest.jsonl"
    val_manifest = manifests_root / "val_manifest.jsonl"
    _write_subset_manifest(train_manifest, train_entries)
    _write_subset_manifest(val_manifest, val_entries)

    trainer = STTTrainer()
    train_ds = SpeechDataset(str(train_manifest))
    val_ds = SpeechDataset(str(val_manifest))
    train_loader = DataLoader(
        train_ds, batch_size=batch_size, shuffle=True, collate_fn=collate_fn
    )
    val_loader = DataLoader(
        val_ds, batch_size=batch_size, shuffle=False, collate_fn=collate_fn
    )
    metrics = trainer.train(train_loader, val_loader, epochs=epochs)

    result = {
        "started": True,
        "epochs": epochs,
        "batch_size": batch_size,
        "train_samples": len(train_entries),
        "val_samples": len(val_entries),
        "metrics": metrics,
        "dataset": get_dataset_status(),
        "completed_at": _now(),
    }
    logger.info("[STT_DATASET] Training complete: %s", result)
    return result
