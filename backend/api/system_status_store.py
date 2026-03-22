from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SYSTEM_STATUS_PATH = Path("data/system_status.json")
RUNTIME_STATUS_PATH = Path("data/runtime_status.json")
HONEST_ACCURACY_PATH = Path("data/honest_accuracy_results.json")
BASELINE_ACCURACY_PATH = Path("data/accuracy_benchmark_results.json")
INGESTION_STATUS_PATH = Path("data/ingestion_status.json")
SYNC_STATUS_PATH = Path("data/sync_status.json")
LEGACY_RUNTIME_STATE_PATH = Path("reports/runtime_state.json")
LEGACY_TRAINING_STATUS_PATH = Path("reports/g38_training_worker.status.json")
TRAINING_STATE_PATH = Path("checkpoints/training_state.json")
CHECKPOINT_PATH = Path("checkpoints/g38_model_checkpoint.safetensors")
RAW_ROOT = Path("data/raw")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(f"{path.suffix}.tmp")
    temp_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    os.replace(temp_path, path)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _checkpoint_sha256() -> str:
    if not CHECKPOINT_PATH.exists():
        return ""
    return _sha256_file(CHECKPOINT_PATH)


def _latest_accuracy() -> float:
    for candidate in (HONEST_ACCURACY_PATH, BASELINE_ACCURACY_PATH):
        payload = _read_json(candidate)
        value = payload.get("accuracy")
        if value is None:
            continue
        try:
            return float(value)
        except (TypeError, ValueError):
            continue
    return 0.0


def _latest_epoch() -> int:
    epochs: list[int] = []
    for payload in (
        _read_json(LEGACY_RUNTIME_STATE_PATH),
        _read_json(LEGACY_TRAINING_STATUS_PATH),
        _read_json(TRAINING_STATE_PATH),
    ):
        for key in ("completed_epochs", "epoch_number", "epoch", "last_epoch"):
            value = payload.get(key)
            if isinstance(value, int):
                epochs.append(value)
    return max(epochs, default=0)


def _training_state() -> dict[str, Any]:
    from backend.training.state_manager import get_training_state_manager

    progress = get_training_state_manager().get_training_progress()
    runtime_status = _read_json(RUNTIME_STATUS_PATH)
    state = str(progress.status or "idle").upper()
    if state == "COMPLETED":
        state = "IDLE"
    return {
        "state": state,
        "last_epoch": _latest_epoch(),
        "last_accuracy": float(_latest_accuracy()),
        "precision_breach": bool(runtime_status.get("precision_breach", False)),
        "checkpoint_sha256": _checkpoint_sha256(),
    }


def _latest_raw_write_time() -> str:
    latest_timestamp = 0.0
    if not RAW_ROOT.exists():
        return ""
    for source_dir in RAW_ROOT.iterdir():
        try:
            candidate = source_dir.stat().st_mtime
        except OSError:
            continue
        latest_timestamp = max(latest_timestamp, candidate)
    if latest_timestamp <= 0:
        return ""
    return datetime.fromtimestamp(latest_timestamp, tz=timezone.utc).isoformat()


def _sources_active() -> list[str]:
    if not RAW_ROOT.exists():
        return []
    return sorted(path.name for path in RAW_ROOT.iterdir() if path.is_dir())


def _ingestion_state() -> dict[str, Any]:
    ingestion_status = _read_json(INGESTION_STATUS_PATH)
    legacy_runtime = _read_json(LEGACY_RUNTIME_STATE_PATH)
    return {
        "last_cycle_time": str(ingestion_status.get("last_cycle_time") or _latest_raw_write_time()),
        "last_new_count": int(ingestion_status.get("last_new_count", 0) or 0),
        "last_duplicate_rate": float(
            ingestion_status.get("duplicate_rate", legacy_runtime.get("duplicate_rate", 0.0)) or 0.0
        ),
        "sources_active": _sources_active(),
    }


def _sync_state() -> dict[str, Any]:
    payload = _read_json(SYNC_STATUS_PATH)
    return {
        "last_sync_time": str(payload.get("last_sync_time", "")),
        "peers_connected": int(payload.get("peers_connected", 0) or 0),
        "files_synced_last_cycle": int(payload.get("files_synced_last_cycle", 0) or 0),
    }


def _gpu_state() -> dict[str, Any]:
    from backend.training.state_manager import get_training_state_manager

    gpu = get_training_state_manager().get_gpu_metrics(force_emit=True)
    return {
        "available": bool(gpu.get("gpu_available", False)),
        "utilization_pct": float(gpu.get("gpu_usage_percent") or 0.0),
        "memory_used_mb": int(round(float(gpu.get("gpu_memory_used_mb") or 0.0))),
    }


def build_system_status_snapshot() -> dict[str, Any]:
    return {
        "schema_version": 2,
        "last_updated": _utc_now(),
        "training": _training_state(),
        "ingestion": _ingestion_state(),
        "sync": _sync_state(),
        "gpu": _gpu_state(),
    }


def refresh_system_status_file(path: Path = SYSTEM_STATUS_PATH) -> dict[str, Any]:
    payload = build_system_status_snapshot()
    _atomic_write_json(path, payload)
    return payload
