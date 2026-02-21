"""
shard_distributor.py — Static Deterministic Shard Distribution

Authority assigns shard ranges:
  shard_i = dataset[i * N / world_size : (i+1) * N / world_size]

Never dynamic sampling.
Never elastic resizing mid-run.
"""

import logging
from dataclasses import dataclass
from typing import List

logger = logging.getLogger(__name__)


@dataclass
class ShardAssignment:
    """Static shard for a rank."""
    rank: int
    world_size: int
    start_index: int
    end_index: int
    shard_size: int
    seed: int  # rank-locked seed


def compute_shards(
    total_samples: int,
    world_size: int,
    base_seed: int = 42,
) -> List[ShardAssignment]:
    """Compute deterministic shard assignments for all ranks.

    Args:
        total_samples: Total dataset size.
        world_size: Number of GPU workers.
        base_seed: Base random seed.

    Returns:
        List of ShardAssignment, one per rank.
    """
    if world_size <= 0:
        raise ValueError("world_size must be > 0")

    shards = []
    for rank in range(world_size):
        start = rank * total_samples // world_size
        end = (rank + 1) * total_samples // world_size
        shards.append(ShardAssignment(
            rank=rank,
            world_size=world_size,
            start_index=start,
            end_index=end,
            shard_size=end - start,
            seed=base_seed + rank,
        ))

    logger.info(
        f"[SHARD] Distributed {total_samples} samples across "
        f"{world_size} ranks (static, no elastic resize)"
    )

    # Verify complete coverage
    total_assigned = sum(s.shard_size for s in shards)
    if total_assigned != total_samples:
        logger.error(
            f"[SHARD] Coverage error: assigned {total_assigned} != {total_samples}"
        )

    return shards


def get_shard_for_rank(
    rank: int,
    total_samples: int,
    world_size: int,
    base_seed: int = 42,
) -> ShardAssignment:
    """Get shard assignment for a specific rank."""
    start = rank * total_samples // world_size
    end = (rank + 1) * total_samples // world_size
    return ShardAssignment(
        rank=rank,
        world_size=world_size,
        start_index=start,
        end_index=end,
        shard_size=end - start,
        seed=base_seed + rank,
    )
