"""
weight_consensus.py — Consensus Weight Validation (CUDA + MPS)

After each epoch:

CUDA cluster:
  - Verify identical weight hash across all DDP nodes

MPS workers:
  - Verify delta norm < threshold
  - Verify loss improvement

If mismatch or violation → blacklist node.
"""

import hashlib
import json
import logging
import os
from dataclasses import dataclass, asdict
from typing import Dict, List, Tuple

logger = logging.getLogger(__name__)

BLACKLIST_PATH = os.path.join('secure_data', 'node_blacklist.json')


@dataclass
class ConsensusResult:
    """Consensus validation result for one epoch."""
    epoch: int
    cuda_match: bool
    mps_valid: bool
    all_passed: bool
    blacklisted: List[str]
    cuda_hash: str
    mps_violations: List[str]


def validate_epoch_consensus(
    epoch: int,
    cuda_hashes: Dict[str, str],
    mps_deltas: List[dict] = None,
    delta_norm_threshold: float = 10.0,
) -> ConsensusResult:
    """Run consensus validation after an epoch.

    Args:
        epoch: Epoch number.
        cuda_hashes: Dict of CUDA node_id -> weight_hash.
        mps_deltas: List of MPS WeightDelta dicts (node_id, delta_norm, loss_before, loss_after).
        delta_norm_threshold: Max allowed MPS delta norm.

    Returns:
        ConsensusResult.
    """
    blacklisted = []
    mps_violations = []

    # === CUDA: all hashes must be identical ===
    cuda_match = True
    cuda_hash = ""
    if cuda_hashes:
        unique_hashes = set(cuda_hashes.values())
        cuda_match = len(unique_hashes) <= 1
        cuda_hash = list(cuda_hashes.values())[0] if cuda_hashes else ""

        if not cuda_match:
            # Find which nodes differ
            reference = list(cuda_hashes.values())[0]
            for nid, h in cuda_hashes.items():
                if h != reference:
                    blacklisted.append(nid)
                    logger.error(
                        f"[CONSENSUS] CUDA mismatch epoch {epoch}: "
                        f"node {nid[:16]}... blacklisted"
                    )

    # === MPS: delta norm + loss check ===
    mps_valid = True
    if mps_deltas:
        for delta in mps_deltas:
            node_id = delta.get('node_id', '?')
            norm = delta.get('delta_norm', 0)
            loss_before = delta.get('loss_before', 0)
            loss_after = delta.get('loss_after', 0)

            # Check norm threshold
            if norm > delta_norm_threshold:
                mps_valid = False
                mps_violations.append(f"{node_id}: norm={norm:.4f}")
                blacklisted.append(node_id)
                logger.error(
                    f"[CONSENSUS] MPS delta norm {norm:.4f} > {delta_norm_threshold} — "
                    f"node {node_id[:16]}... blacklisted"
                )

            # Check loss improvement (shouldn't diverge >50%)
            if loss_after > loss_before * 1.5 and loss_before > 0:
                mps_valid = False
                mps_violations.append(
                    f"{node_id}: loss diverged {loss_before:.4f}→{loss_after:.4f}"
                )
                blacklisted.append(node_id)
                logger.error(
                    f"[CONSENSUS] MPS loss diverged — "
                    f"node {node_id[:16]}... blacklisted"
                )

    # Blacklist nodes
    if blacklisted:
        _update_blacklist(blacklisted)

    all_passed = cuda_match and mps_valid

    result = ConsensusResult(
        epoch=epoch,
        cuda_match=cuda_match,
        mps_valid=mps_valid,
        all_passed=all_passed,
        blacklisted=blacklisted,
        cuda_hash=cuda_hash,
        mps_violations=mps_violations,
    )

    status = "PASS" if all_passed else "FAIL"
    logger.info(
        f"[CONSENSUS] Epoch {epoch} {status}: "
        f"CUDA={cuda_match}, MPS={mps_valid}, "
        f"blacklisted={len(blacklisted)}"
    )

    return result


def _update_blacklist(node_ids: List[str]):
    """Add nodes to persistent blacklist."""
    blacklist = set()
    if os.path.exists(BLACKLIST_PATH):
        try:
            with open(BLACKLIST_PATH, 'r') as f:
                blacklist = set(json.load(f))
        except Exception:
            pass

    blacklist.update(node_ids)

    os.makedirs(os.path.dirname(BLACKLIST_PATH), exist_ok=True)
    with open(BLACKLIST_PATH, 'w') as f:
        json.dump(list(blacklist), f, indent=2)


def is_blacklisted(node_id: str) -> bool:
    """Check if a node is blacklisted."""
    if os.path.exists(BLACKLIST_PATH):
        try:
            with open(BLACKLIST_PATH, 'r') as f:
                return node_id in json.load(f)
        except Exception:
            pass
    return False
