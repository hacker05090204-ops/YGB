"""
cluster_scaler.py — GPU Count Auto-Scaling & Cluster Detection

Detects at startup:
  - Single GPU
  - Multi-GPU (same machine)
  - Multi-node cluster

If world_size > 1: auto-enable DDP.

Logs: cluster_nodes, total_gpu_count, world_size
"""

import logging
import os
from dataclasses import dataclass, asdict
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class ClusterTopology:
    """Detected cluster topology."""
    mode: str              # "single_gpu", "multi_gpu", "multi_node", "cpu_only"
    cluster_nodes: int
    total_gpu_count: int
    world_size: int
    local_rank: int
    ddp_enabled: bool
    backend: str           # "nccl", "gloo", "none"


def detect_topology() -> ClusterTopology:
    """Detect GPU/cluster topology at startup.

    Returns:
        ClusterTopology describing the current environment.
    """
    # Check environment for distributed launch
    world_size = int(os.environ.get("WORLD_SIZE", "1"))
    local_rank = int(os.environ.get("LOCAL_RANK", "0"))
    rank = int(os.environ.get("RANK", "0"))

    try:
        import torch
        cuda_available = torch.cuda.is_available()
        gpu_count = torch.cuda.device_count() if cuda_available else 0
    except ImportError:
        cuda_available = False
        gpu_count = 0

    # Determine mode
    if world_size > 1:
        mode = "multi_node"
        cluster_nodes = world_size
        total_gpus = world_size  # Assume 1 GPU per node for typical setups
        backend = "nccl" if cuda_available else "gloo"
        ddp = True
    elif gpu_count > 1:
        mode = "multi_gpu"
        cluster_nodes = 1
        total_gpus = gpu_count
        world_size = gpu_count
        backend = "nccl"
        ddp = True
    elif gpu_count == 1:
        mode = "single_gpu"
        cluster_nodes = 1
        total_gpus = 1
        backend = "none"
        ddp = False
    else:
        mode = "cpu_only"
        cluster_nodes = 1
        total_gpus = 0
        backend = "none"
        ddp = False

    topology = ClusterTopology(
        mode=mode,
        cluster_nodes=cluster_nodes,
        total_gpu_count=total_gpus,
        world_size=world_size,
        local_rank=local_rank,
        ddp_enabled=ddp,
        backend=backend,
    )

    logger.info(
        f"[CLUSTER] Topology: mode={mode}, nodes={cluster_nodes}, "
        f"gpus={total_gpus}, world_size={world_size}, ddp={ddp}"
    )

    return topology


def get_cluster_log(topology: ClusterTopology = None) -> dict:
    """Get cluster info for telemetry logging."""
    if topology is None:
        topology = detect_topology()
    return asdict(topology)
