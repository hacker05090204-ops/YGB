"""
STT dataset collector and local training bridge.

Builds a real on-disk supervised dataset from browser voice sessions:
  - stores WAV files
  - appends JSONL manifest entries
  - reports dataset/training quality
  - can trigger local Conformer training when enough samples exist
  - tracks training sessions/checkpoints truthfully
  - rejects exact duplicate auto-grab samples
"""

from __future__ import annotations

import hashlib
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
    from backend.training.state_manager import get_optimized_dataloader_kwargs
except Exception:  # pragma: no cover
    def get_optimized_dataloader_kwargs() -> Dict[str, Any]:
        return {
            "num_workers": 4,
            "pin_memory": True,
            "persistent_workers": True,
        }

try:
    from backend.storage.tiered_storage import get_storage_topology, resolve_path
except Exception:  # pragma: no cover
    get_storage_topology = None
    resolve_path = None

try:
    from impl_v1.training.voice.stt_model import _CHECKPOINT_DIR
except Exception:  # pragma: no cover
    _CHECKPOINT_DIR = PROJECT_ROOT / "checkpoints" / "stt"

try:
    from impl_v1.training.checkpoints.checkpoint_hardening import (
        HardenedCheckpointManager,
    )
except Exception:  # pragma: no cover
    HardenedCheckpointManager = None


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


def _training_status_path() -> Path:
    root = _dataset_root()
    root.mkdir(parents=True, exist_ok=True)
    return root / "stt_training_status.json"


def _training_lock_path() -> Path:
    root = _dataset_root()
    root.mkdir(parents=True, exist_ok=True)
    return root / "stt_training.lock"


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


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _sha256_text(payload: str) -> str:
    return hashlib.sha256(payload.encode("utf-8", errors="ignore")).hexdigest()


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


def _read_training_status() -> Dict[str, Any]:
    path = _training_status_path()
    if not path.exists():
        return {
            "status": "IDLE",
            "last_training_at": None,
            "last_completed_session": None,
            "latest_checkpoint": None,
            "best_checkpoint": None,
        }
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {
            "status": "UNKNOWN",
            "last_training_at": None,
            "last_completed_session": None,
            "latest_checkpoint": None,
            "best_checkpoint": None,
        }


def _write_training_status(payload: Dict[str, Any]) -> None:
    _training_status_path().write_text(json.dumps(payload, indent=2), encoding="utf-8")


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


def _checkpoint_info() -> Dict[str, Any]:
    checkpoint_dir = Path(_CHECKPOINT_DIR)

    def _file_info(path: Path) -> Dict[str, Any] | None:
        if not path.exists():
            return None
        try:
            stat = path.stat()
            return {
                "path": str(path),
                "size_bytes": stat.st_size,
                "modified_at": datetime.fromtimestamp(stat.st_mtime, UTC).isoformat(),
            }
        except Exception:
            return {"path": str(path)}

    if HardenedCheckpointManager is not None:
        try:
            manager = HardenedCheckpointManager(checkpoint_dir)
            latest_id = manager.get_latest_valid_checkpoint()
            best_id = manager.get_best_checkpoint()
            latest_path = manager.get_checkpoint_path(latest_id) if latest_id else None
            best_path = manager.get_checkpoint_path(best_id) if best_id else None
            return {
                "checkpoint_dir": str(checkpoint_dir),
                "latest_checkpoint": _file_info(latest_path) if latest_path else None,
                "best_checkpoint": _file_info(best_path) if best_path else None,
            }
        except Exception:
            pass

    latest = checkpoint_dir / "conformer_ctc_latest.pt"
    best = checkpoint_dir / "conformer_ctc_best.pt"

    return {
        "checkpoint_dir": str(checkpoint_dir),
        "latest_checkpoint": _file_info(latest),
        "best_checkpoint": _file_info(best),
    }


def _recent_duplicate(
    entries: List[Dict[str, Any]],
    *,
    transcript_hash: str,
    audio_sha256: str,
    user_id: str,
    device_id: str,
) -> Dict[str, Any] | None:
    # Exact duplicate protection for auto-grabbed browser samples.
    for entry in reversed(entries[-250:]):
        if (
            entry.get("transcript_hash") == transcript_hash
            and entry.get("audio_sha256") == audio_sha256
            and entry.get("user_id") == user_id
            and entry.get("device_id") == device_id
        ):
            return entry
    return None


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
    sessions = Counter(str(entry.get("session_id", "unknown")) for entry in entries)
    topology = get_storage_topology() if get_storage_topology else {}
    training_status = _read_training_status()
    checkpoint_info = _checkpoint_info()

    quality = "EMPTY"
    if sample_count >= _min_samples_for_training():
        quality = "TRAINING_READY"
    elif sample_count >= max(10, _min_samples_for_training() // 5):
        quality = "COLLECTING"

    latest_entry = entries[-1] if entries else None
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
        "unique_sessions": len([s for s in sessions.keys() if s and s != "unknown"]),
        "last_sample_at": latest_entry.get("captured_at") if latest_entry else None,
        "last_sample_id": latest_entry.get("sample_id") if latest_entry else None,
        "last_session_id": latest_entry.get("session_id") if latest_entry else None,
        "storage_topology": topology,
        "training_status": training_status,
        **checkpoint_info,
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
    session_id: str = "",
) -> Dict[str, Any]:
    transcript = _sanitize_transcript(transcript)
    decision = _evaluate_sample(audio_bytes, transcript)
    sample_id = f"STT-{uuid.uuid4().hex[:16].upper()}"
    audio_sha256 = _sha256_bytes(audio_bytes)
    transcript_hash = _sha256_text(transcript)
    normalized_session_id = (session_id or "").strip()[:96] or f"BROWSER-{user_id}-{device_id}"

    if not decision.accepted:
        status = get_dataset_status()
        return {
            "accepted": False,
            "sample_id": sample_id,
            "reason": decision.reason,
            "details": decision.details,
            "dataset": status,
        }

    existing_entries = _read_manifest_entries()
    duplicate = _recent_duplicate(
        existing_entries,
        transcript_hash=transcript_hash,
        audio_sha256=audio_sha256,
        user_id=user_id,
        device_id=device_id,
    )
    if duplicate is not None:
        status = get_dataset_status()
        return {
            "accepted": False,
            "sample_id": sample_id,
            "reason": "DUPLICATE_SAMPLE",
            "details": {
                "existing_sample_id": duplicate.get("sample_id"),
                "existing_captured_at": duplicate.get("captured_at"),
            },
            "dataset": status,
        }

    audio_path = _audio_root() / f"{sample_id}.wav"
    with open(audio_path, "wb") as f:
        f.write(audio_bytes)

    entry = {
        "audio": str(audio_path),
        "text": transcript,
        "sample_id": sample_id,
        "session_id": normalized_session_id,
        "user_id": user_id,
        "device_id": device_id,
        "language": language,
        "provider": provider,
        "captured_at": _now(),
        "audio_sha256": audio_sha256,
        "transcript_hash": transcript_hash,
        **decision.details,
    }

    with open(_manifest_path(), "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=True) + "\n")

    status = get_dataset_status()
    return {
        "accepted": True,
        "sample_id": sample_id,
        "session_id": normalized_session_id,
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

    lock_path = _training_lock_path()
    if lock_path.exists():
        return {
            "started": False,
            "reason": "TRAINING_ALREADY_RUNNING",
            "dataset": get_dataset_status(),
            "training_status": _read_training_status(),
        }

    session_id = f"STT-TRAIN-{uuid.uuid4().hex[:12].upper()}"
    lock_path.write_text(session_id, encoding="utf-8")
    _write_training_status({
        "status": "RUNNING",
        "session_id": session_id,
        "started_at": _now(),
        "requested_epochs": int(epochs),
        "batch_size": int(batch_size),
        "latest_checkpoint": _checkpoint_info().get("latest_checkpoint"),
        "best_checkpoint": _checkpoint_info().get("best_checkpoint"),
    })

    try:
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
        resumed_from_checkpoint = trainer.load_checkpoint()
        train_ds = SpeechDataset(str(train_manifest))
        val_ds = SpeechDataset(str(val_manifest))
        dataloader_kwargs = get_optimized_dataloader_kwargs()
        train_loader = DataLoader(
            train_ds,
            batch_size=batch_size,
            shuffle=True,
            collate_fn=collate_fn,
            **dataloader_kwargs,
        )
        val_loader = DataLoader(
            val_ds,
            batch_size=batch_size,
            shuffle=False,
            collate_fn=collate_fn,
            **dataloader_kwargs,
        )
        metrics = trainer.train(train_loader, val_loader, epochs=epochs)

        checkpoint_info = _checkpoint_info()
        result = {
            "started": True,
            "session_id": session_id,
            "epochs": epochs,
            "batch_size": batch_size,
            "train_samples": len(train_entries),
            "val_samples": len(val_entries),
            "metrics": metrics,
            "resumed_from_checkpoint": bool(resumed_from_checkpoint),
            "checkpoints": checkpoint_info,
            "dataset": get_dataset_status(),
            "completed_at": _now(),
        }
        _write_training_status({
            "status": "COMPLETED",
            "session_id": session_id,
            "started_at": _read_training_status().get("started_at"),
            "completed_at": result["completed_at"],
            "requested_epochs": int(epochs),
            "batch_size": int(batch_size),
            "resumed_from_checkpoint": bool(resumed_from_checkpoint),
            "metrics": metrics,
            "last_training_at": result["completed_at"],
            "last_completed_session": session_id,
            **checkpoint_info,
        })
        logger.info("[STT_DATASET] Training complete: %s", result)
        return result
    except Exception as exc:
        failure = {
            "status": "FAILED",
            "session_id": session_id,
            "failed_at": _now(),
            "error": str(exc),
            **_checkpoint_info(),
        }
        _write_training_status(failure)
        raise
    finally:
        try:
            lock_path.unlink()
        except FileNotFoundError:
            pass
