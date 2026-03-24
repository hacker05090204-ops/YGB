from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from typing import Any, Dict


def checkpoint_paths_for(base_dir: str) -> tuple[str, str, str]:
    base = os.path.join(base_dir, "g38_model_checkpoint")
    return (base + ".safetensors", base + ".json", base + ".pt")


def build_checkpoint_metadata(
    *,
    epoch: int,
    accuracy: float,
    holdout_accuracy: float,
    loss: float,
    real_samples_processed: int,
) -> Dict[str, Any]:
    return {
        "schema_version": 1,
        "format": "safetensors",
        "epoch": int(epoch),
        "accuracy": float(accuracy),
        "holdout_accuracy": float(holdout_accuracy),
        "loss": float(loss),
        "real_samples_processed": int(real_samples_processed),
        "saved_at": datetime.now(timezone.utc).isoformat(),
    }


def save_checkpoint_bundle(
    *,
    checkpoint_path: str,
    checkpoint_meta_path: str,
    model_state: Dict[str, Any],
    metadata: Dict[str, Any],
    safetensors_available: bool,
    save_safetensors_file,
    atomic_write_json,
) -> None:
    if not safetensors_available or save_safetensors_file is None:
        raise RuntimeError("safetensors package not available")

    os.makedirs(os.path.dirname(checkpoint_path), exist_ok=True)
    fd, tmp_weights = tempfile.mkstemp(
        dir=os.path.dirname(checkpoint_path),
        prefix=os.path.basename(checkpoint_path) + ".",
        suffix=".tmp",
    )
    os.close(fd)
    try:
        save_safetensors_file(model_state, tmp_weights)
        os.replace(tmp_weights, checkpoint_path)
    except Exception:
        try:
            os.remove(tmp_weights)
        except OSError:
            pass
        raise

    atomic_write_json(checkpoint_meta_path, metadata)


def load_checkpoint_metadata(checkpoint_meta_path: str) -> Dict[str, Any]:
    try:
        with open(checkpoint_meta_path, "r", encoding="utf-8") as handle:
            payload = json.load(handle)
        if isinstance(payload, dict):
            return payload
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        pass
    return {}


def archive_legacy_checkpoint(legacy_checkpoint_path: str) -> None:
    if not legacy_checkpoint_path or not os.path.exists(legacy_checkpoint_path):
        return
    archived_path = legacy_checkpoint_path + ".legacy"
    os.replace(legacy_checkpoint_path, archived_path)
