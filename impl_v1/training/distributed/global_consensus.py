"""
global_consensus.py — Global Dataset Consensus for Distributed Training

Before distributed training:
  All nodes compute dataset_hash.
  Authority collects all hashes.
  If ANY mismatch → abort. No silent fallback.
"""

import hashlib
import json
import logging
from dataclasses import dataclass
from typing import Dict, List

logger = logging.getLogger(__name__)


@dataclass
class GlobalConsensus:
    """Global dataset consensus result."""
    passed: bool
    authority_hash: str
    node_count: int
    mismatched_nodes: List[str]
    abort_reason: str


def enforce_consensus(
    authority_hash: str,
    node_hashes: Dict[str, str],
) -> GlobalConsensus:
    """Enforce strict dataset hash consensus.

    If ANY node hash differs from authority → abort training.
    No fallback. No partial training.

    Args:
        authority_hash: Authority node's dataset hash.
        node_hashes: Dict of node_id -> dataset_hash.

    Returns:
        GlobalConsensus.
    """
    mismatched = []

    for node_id, h in node_hashes.items():
        if h != authority_hash:
            mismatched.append(node_id)
            logger.error(
                f"[CONSENSUS] MISMATCH: node {node_id[:16]}... "
                f"hash={h[:16]}... vs authority={authority_hash[:16]}..."
            )

    if mismatched:
        abort_reason = (
            f"{len(mismatched)} node(s) have mismatched dataset hashes. "
            f"TRAINING ABORTED. Do not fallback silently."
        )
        logger.error(f"[CONSENSUS] ABORT: {abort_reason}")

        return GlobalConsensus(
            passed=False,
            authority_hash=authority_hash,
            node_count=len(node_hashes),
            mismatched_nodes=mismatched,
            abort_reason=abort_reason,
        )

    logger.info(
        f"[CONSENSUS] PASS: {len(node_hashes)} nodes agree on "
        f"hash {authority_hash[:16]}..."
    )

    return GlobalConsensus(
        passed=True,
        authority_hash=authority_hash,
        node_count=len(node_hashes),
        mismatched_nodes=[],
        abort_reason="",
    )


def compute_dataset_hash(dataset_bytes: bytes, config: dict) -> str:
    """Compute dataset hash for consensus."""
    config_json = json.dumps(config, sort_keys=True).encode('utf-8')
    return hashlib.sha256(dataset_bytes + config_json).hexdigest()
