"""
model_versioning.py — Model Versioning (Phase 4)

After training:
1. Save model weights (FP16)
2. Create compressed archive
3. Store metadata (dataset_hash, merged_weight_hash, hyperparams)
4. Push model weights to Git (NOT dataset)
"""

import hashlib
import json
import logging
import os
import shutil
from dataclasses import dataclass, asdict, field
from datetime import datetime
from typing import Dict, Optional

import numpy as np

logger = logging.getLogger(__name__)

MODEL_DIR = os.path.join('secure_data', 'model_versions')


@dataclass
class ModelVersion:
    """A versioned model snapshot."""
    version_id: str
    dataset_hash: str
    merged_weight_hash: str
    leader_term: int
    epoch: int
    accuracy: float
    hyperparameters: Dict
    fp16: bool
    archive_path: str
    weights_path: str
    timestamp: str = ""


def save_model_fp16(
    model,
    version_id: str,
    dataset_hash: str,
    leader_term: int,
    epoch: int,
    accuracy: float,
    hyperparameters: Dict,
    base_dir: str = MODEL_DIR,
) -> ModelVersion:
    """Save model weights in FP16 format with metadata.

    Args:
        model: PyTorch model (or state_dict)
        version_id: Version identifier
        dataset_hash: SHA-256 of training data
        leader_term: Leader term at save time
        epoch: Epoch number
        accuracy: Final accuracy
        hyperparameters: Training hyperparameters
        base_dir: Output directory

    Returns:
        ModelVersion
    """
    import torch

    version_dir = os.path.join(base_dir, version_id)
    os.makedirs(version_dir, exist_ok=True)

    # Get state dict
    if hasattr(model, 'module'):
        model = model.module
    if hasattr(model, 'state_dict'):
        state_dict = model.state_dict()
    else:
        state_dict = model  # Already a state dict

    # Convert to FP16
    fp16_dict = {}
    for k, v in state_dict.items():
        if v.is_floating_point():
            fp16_dict[k] = v.half()
        else:
            fp16_dict[k] = v

    # Save weights
    weights_path = os.path.join(version_dir, "model_fp16.pt")
    torch.save(fp16_dict, weights_path)

    # Compute weight hash
    h = hashlib.sha256()
    for k in sorted(fp16_dict.keys()):
        h.update(fp16_dict[k].cpu().numpy().tobytes())
    weight_hash = h.hexdigest()

    # Save metadata
    meta = {
        'version_id': version_id,
        'dataset_hash': dataset_hash,
        'merged_weight_hash': weight_hash,
        'leader_term': leader_term,
        'epoch': epoch,
        'accuracy': accuracy,
        'hyperparameters': hyperparameters,
        'fp16': True,
        'timestamp': datetime.now().isoformat(),
    }
    meta_path = os.path.join(version_dir, "metadata.json")
    with open(meta_path, 'w') as f:
        json.dump(meta, f, indent=2)

    # Create ZIP archive
    archive_path = shutil.make_archive(
        os.path.join(base_dir, version_id),
        'zip', version_dir,
    )

    version = ModelVersion(
        version_id=version_id,
        dataset_hash=dataset_hash,
        merged_weight_hash=weight_hash,
        leader_term=leader_term,
        epoch=epoch,
        accuracy=accuracy,
        hyperparameters=hyperparameters,
        fp16=True,
        archive_path=archive_path,
        weights_path=weights_path,
        timestamp=datetime.now().isoformat(),
    )

    logger.info(
        f"[MODEL_VER] Saved: {version_id} — "
        f"FP16, hash={weight_hash[:16]}..."
    )

    return version


def load_model_version(
    version_id: str,
    base_dir: str = MODEL_DIR,
) -> Optional[ModelVersion]:
    """Load model version metadata."""
    meta_path = os.path.join(base_dir, version_id, "metadata.json")
    if not os.path.exists(meta_path):
        return None

    with open(meta_path, 'r') as f:
        meta = json.load(f)

    return ModelVersion(
        version_id=meta['version_id'],
        dataset_hash=meta['dataset_hash'],
        merged_weight_hash=meta['merged_weight_hash'],
        leader_term=meta['leader_term'],
        epoch=meta['epoch'],
        accuracy=meta['accuracy'],
        hyperparameters=meta['hyperparameters'],
        fp16=meta.get('fp16', True),
        archive_path=os.path.join(base_dir, f"{version_id}.zip"),
        weights_path=os.path.join(base_dir, version_id, "model_fp16.pt"),
        timestamp=meta.get('timestamp', ''),
    )


def list_model_versions(base_dir: str = MODEL_DIR) -> list:
    """List all saved model versions."""
    if not os.path.exists(base_dir):
        return []

    versions = []
    for d in sorted(os.listdir(base_dir)):
        meta_path = os.path.join(base_dir, d, "metadata.json")
        if os.path.exists(meta_path):
            versions.append(d)
    return versions


def get_latest_version(base_dir: str = MODEL_DIR) -> Optional[ModelVersion]:
    """Get the latest model version."""
    versions = list_model_versions(base_dir)
    if not versions:
        return None
    return load_model_version(versions[-1], base_dir)
