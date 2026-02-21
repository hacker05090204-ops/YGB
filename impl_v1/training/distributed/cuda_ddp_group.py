"""
cuda_ddp_group.py — CUDA-Only DDP Group Management

Only CUDA nodes participate in NCCL DDP.
world_size = number of CUDA nodes.
MPS nodes are excluded from DDP.

Manages:
  - CUDA node enumeration
  - NCCL process group init
  - Per-rank seed assignment
  - Post-epoch weight hash sync
"""

import hashlib
import logging
import os
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


@dataclass
class CUDADDPGroup:
    """CUDA DDP group state."""
    world_size: int
    cuda_nodes: List[dict]
    backend: str
    nccl_algo: str
    initialized: bool


def create_cuda_ddp_group(
    all_nodes: List[dict],
    base_seed: int = 42,
) -> CUDADDPGroup:
    """Create a DDP group from CUDA nodes only.

    Filters out MPS and CPU nodes. Only CUDA devices
    participate in NCCL all-reduce.

    Args:
        all_nodes: List of all registered nodes with 'backend' field.
        base_seed: Base random seed.

    Returns:
        CUDADDPGroup with CUDA-only nodes.
    """
    cuda_nodes = [
        n for n in all_nodes
        if n.get('backend', '') == 'cuda' and n.get('ddp_eligible', False)
    ]

    # Assign DDP ranks to CUDA nodes only
    for i, node in enumerate(cuda_nodes):
        node['ddp_rank'] = i
        node['ddp_seed'] = base_seed + i

    excluded = len(all_nodes) - len(cuda_nodes)

    group = CUDADDPGroup(
        world_size=len(cuda_nodes),
        cuda_nodes=cuda_nodes,
        backend="nccl",
        nccl_algo="Ring",
        initialized=False,
    )

    logger.info(
        f"[DDP_GROUP] CUDA-only DDP: {len(cuda_nodes)} nodes, "
        f"{excluded} excluded (MPS/CPU)"
    )

    for n in cuda_nodes:
        logger.info(
            f"  Rank {n['ddp_rank']}: {n.get('device_name', '?')} "
            f"(seed={n['ddp_seed']})"
        )

    return group


def init_cuda_ddp(
    group: CUDADDPGroup,
    local_rank: int,
    master_addr: str = "127.0.0.1",
    master_port: str = "29500",
) -> bool:
    """Initialize NCCL DDP for this CUDA rank.

    Args:
        group: CUDADDPGroup.
        local_rank: This node's DDP rank.
        master_addr: Master address.
        master_port: Master port.

    Returns:
        True if init succeeded.
    """
    if group.world_size <= 1:
        logger.info("[DDP_GROUP] Single CUDA node — DDP not needed")
        group.initialized = True
        return True

    try:
        import torch
        import torch.distributed as dist
    except ImportError:
        return False

    os.environ["NCCL_ALGO"] = group.nccl_algo
    os.environ["NCCL_DEBUG"] = "INFO"
    os.environ["MASTER_ADDR"] = master_addr
    os.environ["MASTER_PORT"] = master_port
    os.environ["CUBLAS_WORKSPACE_CONFIG"] = ":4096:8"

    # Find this node's seed
    seed = 42 + local_rank
    for n in group.cuda_nodes:
        if n['ddp_rank'] == local_rank:
            seed = n['ddp_seed']
            break

    torch.manual_seed(seed)
    torch.backends.cudnn.deterministic = True
    torch.backends.cudnn.benchmark = False

    try:
        dist.init_process_group(
            backend=group.backend,
            world_size=group.world_size,
            rank=local_rank,
        )
        group.initialized = True
        logger.info(
            f"[DDP_GROUP] NCCL init: rank={local_rank}/{group.world_size}, "
            f"seed={seed}"
        )
        return True
    except Exception as e:
        logger.error(f"[DDP_GROUP] NCCL init failed: {e}")
        return False


def verify_cuda_weight_hashes(
    node_hashes: Dict[str, str],
    epoch: int,
) -> Tuple[bool, List[str]]:
    """Verify CUDA DDP nodes have identical weight hashes.

    Args:
        node_hashes: Dict of node_id -> weight_hash.
        epoch: Current epoch.

    Returns:
        Tuple of (all_match, mismatched_node_ids).
    """
    if len(node_hashes) <= 1:
        return True, []

    hashes = list(node_hashes.values())
    reference = hashes[0]
    mismatched = [
        nid for nid, h in node_hashes.items()
        if h != reference
    ]

    if mismatched:
        logger.error(
            f"[DDP_GROUP] ABORT epoch {epoch}: "
            f"{len(mismatched)} CUDA node(s) weight mismatch"
        )
    else:
        logger.info(
            f"[DDP_GROUP] Epoch {epoch}: {len(node_hashes)} CUDA nodes "
            f"hash verified ({reference[:16]}...)"
        )

    return len(mismatched) == 0, mismatched
