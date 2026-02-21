"""
mps_shard_worker.py — MPS (Apple Silicon) Independent Shard Worker

Mac M1 runs:
  - Local training on assigned shard
  - Computes weight delta (post - pre training)
  - Sends delta to authority

Authority:
  1. Validates weight delta format + norm
  2. Applies controlled FedAvg merge
  3. Re-broadcasts merged weights

MPS is excluded from NCCL DDP — uses FedAvg instead.
"""

import hashlib
import logging
import os
from dataclasses import dataclass, asdict
from typing import Dict, List, Optional

import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class MPSShardConfig:
    """Configuration for MPS shard worker."""
    shard_start: int
    shard_end: int
    shard_size: int
    batch_size: int
    seed: int
    max_delta_norm: float = 10.0   # Max allowed weight delta norm


@dataclass
class WeightDelta:
    """Weight delta from an MPS worker."""
    node_id: str
    delta_hash: str
    delta_norm: float
    loss_before: float
    loss_after: float
    epoch: int
    valid: bool


def compute_weight_delta(model_before: dict, model_after: dict) -> dict:
    """Compute weight delta between pre/post training states.

    Args:
        model_before: State dict before training.
        model_after: State dict after training.

    Returns:
        Dict of param_name -> delta_tensor.
    """
    delta = {}
    for key in model_before:
        if key in model_after:
            delta[key] = model_after[key] - model_before[key]
    return delta


def compute_delta_norm(delta: dict) -> float:
    """Compute L2 norm of weight delta."""
    total = 0.0
    for key, val in delta.items():
        if hasattr(val, 'numpy'):
            total += np.sum(val.numpy() ** 2)
        else:
            total += np.sum(np.array(val) ** 2)
    return float(np.sqrt(total))


def compute_delta_hash(delta: dict) -> str:
    """Compute SHA-256 hash of weight delta."""
    delta_bytes = b""
    for key in sorted(delta.keys()):
        val = delta[key]
        if hasattr(val, 'numpy'):
            delta_bytes += val.numpy().tobytes()
        else:
            delta_bytes += np.array(val).tobytes()
    return hashlib.sha256(delta_bytes).hexdigest()


def validate_weight_delta(
    delta: dict,
    node_id: str,
    epoch: int,
    loss_before: float,
    loss_after: float,
    max_norm: float = 10.0,
) -> WeightDelta:
    """Validate a weight delta from an MPS worker.

    Checks:
      - Delta norm within threshold
      - Loss improved (or didn't diverge badly)
      - Hash format valid

    Args:
        delta: Weight delta dict.
        node_id: Node identifier.
        epoch: Epoch number.
        loss_before: Loss before this training step.
        loss_after: Loss after this training step.
        max_norm: Maximum allowed delta norm.

    Returns:
        WeightDelta with validation result.
    """
    norm = compute_delta_norm(delta)
    delta_hash = compute_delta_hash(delta)

    valid = True
    if norm > max_norm:
        logger.warning(
            f"[MPS] Delta norm {norm:.4f} exceeds max {max_norm} — "
            f"node {node_id[:16]}..."
        )
        valid = False

    # Loss shouldn't increase by more than 50%
    if loss_after > loss_before * 1.5 and loss_before > 0:
        logger.warning(
            f"[MPS] Loss diverged: {loss_before:.4f} → {loss_after:.4f} — "
            f"node {node_id[:16]}..."
        )
        valid = False

    result = WeightDelta(
        node_id=node_id,
        delta_hash=delta_hash,
        delta_norm=norm,
        loss_before=loss_before,
        loss_after=loss_after,
        epoch=epoch,
        valid=valid,
    )

    if valid:
        logger.info(
            f"[MPS] Delta valid: norm={norm:.4f}, "
            f"loss={loss_before:.4f}→{loss_after:.4f}"
        )

    return result


def fedavg_merge(
    base_state: dict,
    deltas: List[dict],
    weights: List[float] = None,
) -> dict:
    """Apply FedAvg merge of multiple weight deltas.

    merged_weights = base + mean(deltas)

    Args:
        base_state: Base model state dict.
        deltas: List of delta dicts from MPS workers.
        weights: Optional per-worker weights (default: equal).

    Returns:
        Merged state dict.
    """
    if not deltas:
        return base_state.copy()

    n = len(deltas)
    if weights is None:
        weights = [1.0 / n] * n

    merged = {}
    for key in base_state:
        merged_val = base_state[key].clone() if hasattr(base_state[key], 'clone') else base_state[key]

        for i, delta in enumerate(deltas):
            if key in delta:
                merged_val = merged_val + weights[i] * delta[key]

        merged[key] = merged_val

    logger.info(f"[MPS] FedAvg merged {n} deltas into base model")
    return merged
