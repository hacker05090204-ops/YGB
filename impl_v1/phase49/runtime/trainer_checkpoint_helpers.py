from __future__ import annotations

import json
import logging
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict


logger = logging.getLogger(__name__)


def _sha256_file(path: str) -> str:
    import hashlib

    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


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
    from training.safetensors_io import save_safetensors

    os.makedirs(os.path.dirname(checkpoint_path), exist_ok=True)
    file_sha256, tensor_hash = save_safetensors(
        model_state,
        checkpoint_path,
        metadata={
            "checkpoint_path": str(checkpoint_path),
            "schema_version": str(metadata.get("schema_version", 1)),
        },
    )

    metadata_payload = dict(metadata)
    metadata_payload["checkpoint_path"] = str(checkpoint_path)
    metadata_payload["file_sha256"] = file_sha256
    metadata_payload["tensor_hash"] = tensor_hash
    atomic_write_json(checkpoint_meta_path, metadata_payload)


def load_checkpoint_metadata(checkpoint_meta_path: str) -> Dict[str, Any]:
    try:
        with open(checkpoint_meta_path, "r", encoding="utf-8") as handle:
            payload = json.load(handle)
        if isinstance(payload, dict):
            return payload
    except FileNotFoundError:
        logger.debug("Checkpoint metadata file not found: %s", checkpoint_meta_path)
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning(
            "Failed to load checkpoint metadata from %s: %s",
            checkpoint_meta_path,
            exc,
        )
    return {}


def archive_legacy_checkpoint(legacy_checkpoint_path: str) -> None:
    if not legacy_checkpoint_path or not os.path.exists(legacy_checkpoint_path):
        return
    archived_path = legacy_checkpoint_path + ".legacy"
    os.replace(legacy_checkpoint_path, archived_path)
    sidecar_path = legacy_checkpoint_path + ".sha256"
    if os.path.exists(sidecar_path):
        os.replace(sidecar_path, archived_path + ".sha256")
