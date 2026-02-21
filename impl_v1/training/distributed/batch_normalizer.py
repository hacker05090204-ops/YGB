"""
batch_normalizer.py — Global Batch Normalization Across Heterogeneous GPUs

Authority collects:
  - VRAM total per node
  - Optimal batch per node (from adaptive scaling)

Computes:
  global_batch = sum(optimal_batch_per_node)

Shards dataset proportionally to each node's batch capacity.
Never forces same batch size across different GPUs.
"""

import logging
from dataclasses import dataclass
from typing import Dict, List

logger = logging.getLogger(__name__)


@dataclass
class NodeBatchConfig:
    """Per-node batch configuration."""
    node_id: str
    device_name: str
    vram_total_mb: float
    optimal_batch: int
    shard_start: int
    shard_end: int
    shard_size: int


@dataclass
class GlobalBatchPlan:
    """Global batch normalization plan."""
    global_batch_size: int
    total_samples: int
    node_configs: List[NodeBatchConfig]
    world_size: int


def compute_global_batch_plan(
    node_specs: List[Dict],
    total_samples: int,
) -> GlobalBatchPlan:
    """Compute global batch plan with per-node optimal batches.

    Args:
        node_specs: List of dicts with node_id, device_name, vram_total_mb, optimal_batch.
        total_samples: Total dataset size.

    Returns:
        GlobalBatchPlan with proportional sharding.
    """
    if not node_specs:
        raise ValueError("No nodes provided")

    global_batch = sum(n.get('optimal_batch', 1024) for n in node_specs)
    total_capacity = sum(n.get('optimal_batch', 1024) for n in node_specs)

    configs = []
    offset = 0

    for n in node_specs:
        batch = n.get('optimal_batch', 1024)
        # Proportional shard based on batch capacity
        proportion = batch / total_capacity
        shard_size = int(total_samples * proportion)

        # Last node gets remainder
        if n == node_specs[-1]:
            shard_size = total_samples - offset

        configs.append(NodeBatchConfig(
            node_id=n.get('node_id', ''),
            device_name=n.get('device_name', ''),
            vram_total_mb=n.get('vram_total_mb', 0),
            optimal_batch=batch,
            shard_start=offset,
            shard_end=offset + shard_size,
            shard_size=shard_size,
        ))

        offset += shard_size

    plan = GlobalBatchPlan(
        global_batch_size=global_batch,
        total_samples=total_samples,
        node_configs=configs,
        world_size=len(configs),
    )

    logger.info(
        f"[BATCH_NORM] Global batch={global_batch}, "
        f"{len(configs)} nodes, {total_samples} samples"
    )
    for c in configs:
        logger.info(
            f"  {c.device_name}: batch={c.optimal_batch}, "
            f"shard=[{c.shard_start}:{c.shard_end}] ({c.shard_size} samples)"
        )

    return plan
