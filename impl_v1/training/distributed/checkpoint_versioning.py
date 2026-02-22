"""
checkpoint_versioning.py — Term-Aware Checkpoint Versioning (Phase 3)

Each checkpoint tagged with election term.
Stale (lower-term) checkpoints rejected.
"""

import hashlib
import json
import logging
import os
import time
from dataclasses import dataclass, asdict, field
from datetime import datetime
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

VERSIONED_CKPT_DIR = os.path.join('secure_data', 'versioned_checkpoints')


@dataclass
class VersionedCheckpoint:
    """Checkpoint tagged with election term."""
    checkpoint_id: str
    term: int
    epoch: int
    dataset_hash: str
    merged_weight_hash: str
    world_size: int
    shard_proportions: Dict[str, float]
    fencing_token: int = 0
    timestamp: str = ""


def create_versioned_checkpoint(
    term: int,
    epoch: int,
    dataset_hash: str,
    merged_weight_hash: str,
    world_size: int,
    shard_proportions: Dict[str, float],
    fencing_token: int = 0,
) -> VersionedCheckpoint:
    """Create a term-versioned checkpoint."""
    ckpt = VersionedCheckpoint(
        checkpoint_id=f"ckpt_t{term:04d}_e{epoch:04d}_{int(time.time())}",
        term=term,
        epoch=epoch,
        dataset_hash=dataset_hash,
        merged_weight_hash=merged_weight_hash,
        world_size=world_size,
        shard_proportions=shard_proportions,
        fencing_token=fencing_token,
        timestamp=datetime.now().isoformat(),
    )
    logger.info(
        f"[CKPT_VER] Created: term={term}, epoch={epoch}, "
        f"fence={fencing_token}"
    )
    return ckpt


def validate_checkpoint(
    ckpt: VersionedCheckpoint,
    current_term: int,
    current_fencing_token: int = 0,
) -> Tuple[bool, str]:
    """Reject stale checkpoints from old terms.

    Returns:
        (valid, reason)
    """
    if ckpt.term < current_term:
        reason = (
            f"Stale: checkpoint term {ckpt.term} < current {current_term}"
        )
        logger.error(f"[CKPT_VER] REJECTED: {reason}")
        return False, reason

    if current_fencing_token > 0 and ckpt.fencing_token < current_fencing_token:
        reason = (
            f"Stale fence: {ckpt.fencing_token} < {current_fencing_token}"
        )
        logger.error(f"[CKPT_VER] REJECTED: {reason}")
        return False, reason

    logger.info(
        f"[CKPT_VER] Accepted: term={ckpt.term}, epoch={ckpt.epoch}"
    )
    return True, "Valid"


def save_versioned_checkpoint(
    ckpt: VersionedCheckpoint,
    base_dir: str = VERSIONED_CKPT_DIR,
) -> str:
    """Save checkpoint to disk with atomic write."""
    os.makedirs(base_dir, exist_ok=True)
    path = os.path.join(base_dir, f"{ckpt.checkpoint_id}.json")
    tmp = path + ".tmp"

    with open(tmp, 'w') as f:
        json.dump(asdict(ckpt), f, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)

    logger.info(f"[CKPT_VER] Saved: {path}")
    return path


def load_latest_checkpoint(
    base_dir: str = VERSIONED_CKPT_DIR,
) -> Optional[VersionedCheckpoint]:
    """Load the latest (highest term+epoch) checkpoint."""
    if not os.path.exists(base_dir):
        return None

    best = None
    for fname in os.listdir(base_dir):
        if not fname.endswith('.json'):
            continue
        try:
            with open(os.path.join(base_dir, fname), 'r') as f:
                data = json.load(f)
            ckpt = VersionedCheckpoint(**data)
            if best is None or (ckpt.term, ckpt.epoch) > (best.term, best.epoch):
                best = ckpt
        except Exception:
            continue

    return best
