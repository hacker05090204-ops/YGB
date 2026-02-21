"""
dataset_consensus.py — Multi-Node Dataset Hash Consensus

Before training:
  All nodes compute: SHA256(dataset_bytes + config_json)
  Authority verifies: all hashes identical.
  If mismatch → abort training.
"""

import hashlib
import json
import logging
from dataclasses import dataclass
from typing import Dict, List, Tuple

logger = logging.getLogger(__name__)


@dataclass
class ConsensusResult:
    """Result of dataset hash consensus."""
    passed: bool
    expected_hash: str
    node_hashes: Dict[str, str]
    mismatched_nodes: List[str]


def compute_local_dataset_hash(dataset_bytes: bytes, config: dict) -> str:
    """Compute dataset hash for consensus.

    Args:
        dataset_bytes: Raw dataset content bytes.
        config: Training config dict.

    Returns:
        SHA-256 hex hash.
    """
    config_json = json.dumps(config, sort_keys=True).encode('utf-8')
    combined = dataset_bytes + config_json
    return hashlib.sha256(combined).hexdigest()


def verify_consensus(
    authority_hash: str,
    node_hashes: Dict[str, str],
) -> ConsensusResult:
    """Verify all nodes agree on dataset hash.

    Args:
        authority_hash: Authority node's dataset hash.
        node_hashes: Dict of node_id -> dataset_hash.

    Returns:
        ConsensusResult.
    """
    mismatched = []
    for node_id, h in node_hashes.items():
        if h != authority_hash:
            mismatched.append(node_id)
            logger.error(
                f"[CONSENSUS] Node {node_id[:16]} hash MISMATCH: "
                f"{h[:16]}... vs expected {authority_hash[:16]}..."
            )

    passed = len(mismatched) == 0

    if passed:
        logger.info(
            f"[CONSENSUS] PASS: {len(node_hashes)} nodes agree "
            f"on hash {authority_hash[:16]}..."
        )
    else:
        logger.error(
            f"[CONSENSUS] FAIL: {len(mismatched)}/{len(node_hashes)} "
            f"nodes have mismatched hashes — ABORT TRAINING"
        )

    return ConsensusResult(
        passed=passed,
        expected_hash=authority_hash,
        node_hashes=node_hashes,
        mismatched_nodes=mismatched,
    )
