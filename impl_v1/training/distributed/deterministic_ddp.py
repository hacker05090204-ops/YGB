"""
deterministic_ddp.py — Deterministic Distributed Data Parallel Training

Orchestrates:
  - torch.distributed.init_process_group(backend="nccl")
  - Static shard allocation per node
  - Fixed seed per rank: seed = base_seed + rank
  - Deterministic NCCL ring all-reduce
  - Post-epoch weight hash verification
  - Abort + blacklist on mismatch
"""

import hashlib
import json
import logging
import os
import time
from dataclasses import dataclass, asdict
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

BLACKLIST_PATH = os.path.join('secure_data', 'node_blacklist.json')


@dataclass
class DDPEpochResult:
    """Result of one DDP epoch."""
    epoch: int
    weight_hash: str
    all_hashes_match: bool
    samples_processed: int
    epoch_time_sec: float
    blacklisted_nodes: List[str]


def init_deterministic_ddp(
    rank: int,
    world_size: int,
    base_seed: int = 42,
    master_addr: str = "127.0.0.1",
    master_port: str = "29500",
) -> bool:
    """Initialize deterministic DDP.

    Args:
        rank: This process's rank.
        world_size: Total number of processes.
        base_seed: Base seed (per-rank = base_seed + rank).
        master_addr: Master node address.
        master_port: Master node port.

    Returns:
        True if init succeeded.
    """
    try:
        import torch
        import torch.distributed as dist
    except ImportError:
        logger.error("[DDP] PyTorch not available")
        return False

    if world_size <= 1:
        logger.info("[DDP] Single process — DDP not needed")
        return True

    # Deterministic environment
    os.environ["NCCL_ALGO"] = "Ring"
    os.environ["NCCL_DEBUG"] = "INFO"
    os.environ["MASTER_ADDR"] = master_addr
    os.environ["MASTER_PORT"] = master_port
    os.environ["CUBLAS_WORKSPACE_CONFIG"] = ":4096:8"

    rank_seed = base_seed + rank
    torch.manual_seed(rank_seed)
    torch.backends.cudnn.deterministic = True
    torch.backends.cudnn.benchmark = False
    try:
        torch.use_deterministic_algorithms(True)
    except Exception:
        pass

    backend = "nccl" if torch.cuda.is_available() else "gloo"

    try:
        dist.init_process_group(
            backend=backend,
            world_size=world_size,
            rank=rank,
        )
        logger.info(
            f"[DDP] Init: rank={rank}/{world_size}, "
            f"seed={rank_seed}, backend={backend}"
        )
        return True
    except Exception as e:
        logger.error(f"[DDP] Init failed: {e}")
        return False


def compute_weight_hash(model) -> str:
    """Compute SHA-256 of model weights."""
    weight_bytes = b""
    for name, param in sorted(model.named_parameters()):
        weight_bytes += param.detach().cpu().numpy().tobytes()
    return hashlib.sha256(weight_bytes).hexdigest()


def verify_epoch_hashes(
    authority_hash: str,
    node_hashes: Dict[str, str],
    epoch: int,
) -> Tuple[bool, List[str]]:
    """Verify all nodes have identical weight hashes.

    Args:
        authority_hash: Authority's weight hash.
        node_hashes: Dict of node_id -> weight_hash.
        epoch: Current epoch.

    Returns:
        Tuple of (all_match, blacklisted_node_ids).
    """
    blacklisted = []

    for node_id, h in node_hashes.items():
        if h != authority_hash:
            blacklisted.append(node_id)
            logger.error(
                f"[DDP] ABORT: Epoch {epoch} weight mismatch — "
                f"node {node_id[:16]}... BLACKLISTED"
            )

    if blacklisted:
        _add_to_blacklist(blacklisted)

    return len(blacklisted) == 0, blacklisted


def _add_to_blacklist(node_ids: List[str]):
    """Add nodes to blacklist."""
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

    logger.warning(f"[DDP] Blacklisted {len(node_ids)} node(s)")


def is_blacklisted(node_id: str) -> bool:
    """Check if a node is blacklisted."""
    if os.path.exists(BLACKLIST_PATH):
        try:
            with open(BLACKLIST_PATH, 'r') as f:
                blacklist = json.load(f)
            return node_id in blacklist
        except Exception:
            pass
    return False


def cleanup_ddp():
    """Clean up distributed process group."""
    try:
        import torch.distributed as dist
        if dist.is_initialized():
            dist.destroy_process_group()
    except Exception:
        pass
