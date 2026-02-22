"""
checkpoint_consensus.py — Checkpoint Consensus (Phase 6)

After each epoch:

1. Save global checkpoint with:
   - dataset_hash
   - merged_weight_hash
   - world_size
   - shard_proportions

2. Require ALL nodes to acknowledge before advancing (strict mode).

Extends existing checkpoint_hardening.py for distributed use.
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

CONSENSUS_PATH = os.path.join('secure_data', 'checkpoint_consensus.json')


# =============================================================================
# TYPES
# =============================================================================

@dataclass
class ConsensusCheckpoint:
    """Global checkpoint with consensus metadata."""
    checkpoint_id: str
    epoch: int
    dataset_hash: str
    merged_weight_hash: str
    world_size: int
    shard_proportions: Dict[str, float]
    node_acks: Dict[str, bool]
    majority_reached: bool
    timestamp: str
    confirmed_count: int
    required_count: int


@dataclass
class ConsensusState:
    """Accumulated consensus state across epochs."""
    checkpoints: List[dict] = field(default_factory=list)
    current_epoch: int = -1
    all_confirmed: bool = True


# =============================================================================
# CHECKPOINT CREATION
# =============================================================================

def create_consensus_checkpoint(
    epoch: int,
    dataset_hash: str,
    merged_weight_hash: str,
    world_size: int,
    shard_proportions: Dict[str, float],
    strict: bool = True,
) -> ConsensusCheckpoint:
    """Create a consensus checkpoint.

    In strict mode (default), ALL nodes must confirm.
    In non-strict mode, majority is sufficient.

    Args:
        epoch: Current epoch.
        dataset_hash: SHA-256 of the dataset.
        merged_weight_hash: SHA-256 of merged model weights.
        world_size: Number of nodes in the cluster.
        shard_proportions: Dict of node_id -> proportion (0.0 - 1.0).
        strict: If True, require ALL nodes (default). If False, majority.

    Returns:
        ConsensusCheckpoint awaiting node ACKs.
    """
    checkpoint_id = f"consensus_e{epoch:04d}_{int(time.time())}"
    required = world_size if strict else (world_size // 2) + 1

    ckpt = ConsensusCheckpoint(
        checkpoint_id=checkpoint_id,
        epoch=epoch,
        dataset_hash=dataset_hash,
        merged_weight_hash=merged_weight_hash,
        world_size=world_size,
        shard_proportions=shard_proportions,
        node_acks={},
        majority_reached=False,
        timestamp=datetime.now().isoformat(),
        confirmed_count=0,
        required_count=required,
    )

    mode = "STRICT (all)" if strict else f"MAJORITY ({required}/{world_size})"
    logger.info(
        f"[CONSENSUS_CKPT] Created: epoch={epoch}, "
        f"mode={mode}, requires {required}/{world_size}"
    )

    return ckpt


# =============================================================================
# ACK COLLECTION
# =============================================================================

def submit_node_ack(
    checkpoint: ConsensusCheckpoint,
    node_id: str,
    node_weight_hash: str,
) -> Tuple[bool, str]:
    """Submit a node's ACK for a consensus checkpoint.

    The node must provide its weight hash which must match
    the merged_weight_hash in the checkpoint.

    Args:
        checkpoint: The checkpoint to confirm.
        node_id: Confirming node's ID.
        node_weight_hash: Node's computed weight hash.

    Returns:
        (accepted, reason)
    """
    # Verify hash matches
    if node_weight_hash != checkpoint.merged_weight_hash:
        reason = (
            f"Weight hash mismatch: node={node_weight_hash[:16]}... "
            f"vs expected={checkpoint.merged_weight_hash[:16]}..."
        )
        logger.error(f"[CONSENSUS_CKPT] Node {node_id[:16]}... ACK REJECTED: {reason}")
        checkpoint.node_acks[node_id] = False
        return False, reason

    checkpoint.node_acks[node_id] = True
    checkpoint.confirmed_count = sum(
        1 for v in checkpoint.node_acks.values() if v
    )

    # Check majority
    if checkpoint.confirmed_count >= checkpoint.required_count:
        checkpoint.majority_reached = True
        logger.info(
            f"[CONSENSUS_CKPT] MAJORITY REACHED: "
            f"{checkpoint.confirmed_count}/{checkpoint.world_size} "
            f"confirmed epoch {checkpoint.epoch}"
        )
    else:
        logger.info(
            f"[CONSENSUS_CKPT] ACK from {node_id[:16]}...: "
            f"{checkpoint.confirmed_count}/{checkpoint.required_count} needed"
        )

    return True, "ACK accepted"


def can_advance(checkpoint: ConsensusCheckpoint) -> bool:
    """Check if majority reached and epoch can advance."""
    return checkpoint.majority_reached


# =============================================================================
# PERSISTENCE
# =============================================================================

def persist_consensus_state(
    state: ConsensusState,
    path: str = CONSENSUS_PATH,
):
    """Persist consensus state to disk."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp_path = path + ".tmp"

    with open(tmp_path, 'w') as f:
        json.dump(asdict(state), f, indent=2)
        f.flush()
        os.fsync(f.fileno())

    if os.path.exists(path):
        os.replace(tmp_path, path)
    else:
        os.rename(tmp_path, path)

    logger.info(
        f"[CONSENSUS_CKPT] State persisted: "
        f"{len(state.checkpoints)} checkpoints"
    )


def load_consensus_state(path: str = CONSENSUS_PATH) -> ConsensusState:
    """Load consensus state from disk."""
    if os.path.exists(path):
        try:
            with open(path, 'r') as f:
                data = json.load(f)
            return ConsensusState(**data)
        except Exception as e:
            logger.error(f"[CONSENSUS_CKPT] Failed to load state: {e}")

    return ConsensusState()


# =============================================================================
# FULL EPOCH CONSENSUS FLOW
# =============================================================================

def run_epoch_consensus(
    epoch: int,
    dataset_hash: str,
    merged_weight_hash: str,
    world_size: int,
    shard_proportions: Dict[str, float],
    node_weight_hashes: Dict[str, str],
) -> ConsensusCheckpoint:
    """Run full consensus flow for one epoch.

    Creates checkpoint, collects all node ACKs, checks majority.

    Args:
        epoch: Current epoch.
        dataset_hash: Dataset hash.
        merged_weight_hash: Authority's merged weight hash.
        world_size: Cluster size.
        shard_proportions: Per-node data proportions.
        node_weight_hashes: Dict of node_id -> weight_hash from each node.

    Returns:
        ConsensusCheckpoint with majority status.
    """
    ckpt = create_consensus_checkpoint(
        epoch=epoch,
        dataset_hash=dataset_hash,
        merged_weight_hash=merged_weight_hash,
        world_size=world_size,
        shard_proportions=shard_proportions,
    )

    for node_id, w_hash in node_weight_hashes.items():
        submit_node_ack(ckpt, node_id, w_hash)

    if not ckpt.majority_reached:
        logger.error(
            f"[CONSENSUS_CKPT] Epoch {epoch}: majority NOT reached "
            f"({ckpt.confirmed_count}/{ckpt.required_count}) — "
            f"BLOCKING epoch advance"
        )

    return ckpt
