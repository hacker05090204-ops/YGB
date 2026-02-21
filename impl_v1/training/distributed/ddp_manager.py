"""
ddp_manager.py — Deterministic Distributed Data Parallel Manager

Handles:
  - NCCL Ring all-reduce
  - torch.distributed init (deterministic)
  - Per-rank seed locking: seed = base_seed + rank
  - Post-epoch weight hash comparison; abort on mismatch
"""

import hashlib
import logging
import os
from dataclasses import dataclass
from typing import Optional, Tuple

logger = logging.getLogger(__name__)


@dataclass
class DDPConfig:
    """Distributed Data Parallel configuration."""
    backend: str = "nccl"         # NCCL for GPU, gloo for CPU
    world_size: int = 1
    rank: int = 0
    base_seed: int = 42
    master_addr: str = "127.0.0.1"
    master_port: str = "29500"
    nccl_algo: str = "Ring"       # Fixed ring for determinism
    nccl_debug: str = "INFO"


def setup_ddp(config: DDPConfig) -> bool:
    """Initialize torch.distributed with deterministic settings.

    Args:
        config: DDP configuration.

    Returns:
        True if init succeeded.
    """
    try:
        import torch
        import torch.distributed as dist
    except ImportError:
        logger.error("[DDP] PyTorch not available")
        return False

    if config.world_size <= 1:
        logger.info("[DDP] Single GPU — DDP not needed")
        return True

    # Set NCCL environment for determinism
    os.environ["NCCL_ALGO"] = config.nccl_algo
    os.environ["NCCL_DEBUG"] = config.nccl_debug
    os.environ["MASTER_ADDR"] = config.master_addr
    os.environ["MASTER_PORT"] = config.master_port
    os.environ["CUBLAS_WORKSPACE_CONFIG"] = ":4096:8"

    # Lock seed per rank
    rank_seed = config.base_seed + config.rank
    torch.manual_seed(rank_seed)
    torch.backends.cudnn.deterministic = True
    torch.backends.cudnn.benchmark = False

    try:
        torch.use_deterministic_algorithms(True)
    except Exception:
        pass

    try:
        dist.init_process_group(
            backend=config.backend,
            world_size=config.world_size,
            rank=config.rank,
        )
        logger.info(
            f"[DDP] Initialized: rank={config.rank}/{config.world_size}, "
            f"backend={config.backend}, algo={config.nccl_algo}, "
            f"seed={rank_seed}"
        )
        return True
    except Exception as e:
        logger.error(f"[DDP] Init failed: {e}")
        return False


def cleanup_ddp():
    """Clean up distributed process group."""
    try:
        import torch.distributed as dist
        if dist.is_initialized():
            dist.destroy_process_group()
            logger.info("[DDP] Process group destroyed")
    except Exception:
        pass


def compute_weight_hash(model) -> str:
    """Compute SHA-256 hash of model weights.

    Args:
        model: PyTorch model.

    Returns:
        64-char hex hash string.
    """
    try:
        import torch
    except ImportError:
        return "unavailable"

    weight_bytes = b""
    for name, param in sorted(model.named_parameters()):
        weight_bytes += param.detach().cpu().numpy().tobytes()

    return hashlib.sha256(weight_bytes).hexdigest()


def verify_weight_consistency(
    local_hash: str,
    world_size: int,
    rank: int,
) -> Tuple[bool, list]:
    """Verify all ranks have identical weight hashes.

    Uses all-gather to collect hashes from all ranks.

    Args:
        local_hash: This rank's weight hash.
        world_size: Total ranks.
        rank: This rank's index.

    Returns:
        Tuple of (all_match, list_of_hashes).
    """
    try:
        import torch
        import torch.distributed as dist
    except ImportError:
        return True, [local_hash]

    if not dist.is_initialized() or world_size <= 1:
        return True, [local_hash]

    # Encode hash as tensor for all-gather
    hash_bytes = local_hash.encode('utf-8')[:64]
    local_tensor = torch.tensor(
        [b for b in hash_bytes],
        dtype=torch.uint8,
    ).cuda(rank)

    gathered = [
        torch.zeros(64, dtype=torch.uint8).cuda(rank)
        for _ in range(world_size)
    ]
    dist.all_gather(gathered, local_tensor)

    # Decode hashes
    hashes = []
    for t in gathered:
        h = bytes(t.cpu().tolist()).decode('utf-8')
        hashes.append(h)

    all_match = len(set(hashes)) == 1

    if all_match:
        logger.info(f"[DDP] Weight hash verified: {local_hash[:16]}...")
    else:
        logger.error(f"[DDP] ABORT: Weight hash mismatch across ranks!")
        for i, h in enumerate(hashes):
            logger.error(f"  Rank {i}: {h[:16]}...")

    return all_match, hashes
