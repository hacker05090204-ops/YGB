"""
scaling_efficiency.py — Real Scaling Efficiency Measurement (Phase 3)

After each distributed epoch, compute:

  efficiency = cluster_sps / sum(single_node_baseline_sps)

If efficiency < 0.7:
  Log degradation warning.
  Optionally disable weakest node.
"""

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

EFFICIENCY_THRESHOLD = 0.70
CRITICAL_THRESHOLD = 0.50


# =============================================================================
# RESULT TYPES
# =============================================================================

@dataclass
class ScalingMetrics:
    """Scaling efficiency metrics for one epoch."""
    epoch: int
    cluster_sps: float
    single_node_baselines: Dict[str, float]
    sum_baselines: float
    efficiency: float
    degraded: bool
    critical: bool
    weakest_node: str
    weakest_sps: float


@dataclass
class ScalingReport:
    """Accumulated scaling report across epochs."""
    epoch_metrics: List[ScalingMetrics] = field(default_factory=list)
    disabled_nodes: List[str] = field(default_factory=list)
    avg_efficiency: float = 0.0


# =============================================================================
# SINGLE NODE BASELINE
# =============================================================================

def measure_single_node_baseline(
    node_id: str,
    input_dim: int = 256,
    num_samples: int = 4000,
    batch_size: int = 1024,
    epochs: int = 1,
) -> float:
    """Measure single-node throughput baseline (samples/sec).

    Runs a quick training loop on one node in isolation.
    """
    try:
        import time
        import numpy as np
        import torch
        import torch.nn as nn
        import torch.optim as optim
    except ImportError:
        return 0.0

    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')

    rng = np.random.RandomState(42)
    X = torch.from_numpy(
        rng.randn(num_samples, input_dim).astype(np.float32)
    ).to(device)
    y = torch.from_numpy(
        rng.randint(0, 2, num_samples).astype(np.int64)
    ).to(device)

    model = nn.Sequential(
        nn.Linear(input_dim, 512), nn.ReLU(),
        nn.Linear(512, 256), nn.ReLU(),
        nn.Linear(256, 2),
    ).to(device)

    optimizer = optim.Adam(model.parameters(), lr=0.001)
    criterion = nn.CrossEntropyLoss()
    model.train()

    t0 = time.perf_counter()
    processed = 0

    for ep in range(epochs):
        for i in range(0, num_samples, batch_size):
            bx = X[i:i + batch_size]
            by = y[i:i + batch_size]
            optimizer.zero_grad()
            loss = criterion(model(bx), by)
            loss.backward()
            optimizer.step()
            processed += bx.size(0)

    elapsed = time.perf_counter() - t0
    sps = processed / max(elapsed, 0.001)

    del model, optimizer, X, y
    if torch.cuda.is_available():
        torch.cuda.empty_cache()

    logger.info(f"[SCALING] Baseline {node_id}: {sps:.0f} sps")
    return round(sps, 2)


# =============================================================================
# EFFICIENCY MEASUREMENT
# =============================================================================

def measure_efficiency(
    epoch: int,
    cluster_sps: float,
    per_node_sps: Dict[str, float],
    single_node_baselines: Dict[str, float],
) -> ScalingMetrics:
    """Compute scaling efficiency after an epoch.

    Args:
        epoch: Epoch number.
        cluster_sps: Aggregate cluster samples/sec.
        per_node_sps: Per-node sps from this epoch.
        single_node_baselines: Per-node baseline sps (measured solo).

    Returns:
        ScalingMetrics with efficiency ratio and warnings.
    """
    sum_baselines = sum(single_node_baselines.values())
    efficiency = cluster_sps / max(sum_baselines, 1.0)

    degraded = efficiency < EFFICIENCY_THRESHOLD
    critical = efficiency < CRITICAL_THRESHOLD

    # Find weakest node
    weakest_node = ""
    weakest_sps = float('inf')
    for nid, sps in per_node_sps.items():
        if sps < weakest_sps:
            weakest_sps = sps
            weakest_node = nid

    result = ScalingMetrics(
        epoch=epoch,
        cluster_sps=round(cluster_sps, 2),
        single_node_baselines=single_node_baselines,
        sum_baselines=round(sum_baselines, 2),
        efficiency=round(efficiency, 4),
        degraded=degraded,
        critical=critical,
        weakest_node=weakest_node,
        weakest_sps=round(weakest_sps, 2),
    )

    if critical:
        logger.error(
            f"[SCALING] CRITICAL: Epoch {epoch} efficiency={efficiency:.2%} "
            f"(< {CRITICAL_THRESHOLD:.0%}) — weakest={weakest_node}"
        )
    elif degraded:
        logger.warning(
            f"[SCALING] DEGRADED: Epoch {epoch} efficiency={efficiency:.2%} "
            f"(< {EFFICIENCY_THRESHOLD:.0%}) — weakest={weakest_node}"
        )
    else:
        logger.info(
            f"[SCALING] Epoch {epoch} efficiency={efficiency:.2%} — healthy"
        )

    return result


def should_disable_node(
    metrics: ScalingMetrics,
    min_sps_ratio: float = 0.3,
) -> Tuple[bool, str]:
    """Determine if the weakest node should be disabled.

    Disable if the weakest node's throughput is less than
    min_sps_ratio * average of other nodes.

    Returns:
        (should_disable, reason)
    """
    if not metrics.degraded:
        return False, "Efficiency is healthy"

    baselines = metrics.single_node_baselines
    if len(baselines) <= 1:
        return False, "Cannot disable with only 1 node"

    # Average sps excluding weakest
    other_sps = [
        sps for nid, sps in baselines.items()
        if nid != metrics.weakest_node
    ]
    avg_others = sum(other_sps) / max(len(other_sps), 1)

    if metrics.weakest_sps < avg_others * min_sps_ratio:
        reason = (
            f"Node {metrics.weakest_node} sps={metrics.weakest_sps:.0f} "
            f"< {min_sps_ratio:.0%} of avg others ({avg_others:.0f})"
        )
        logger.warning(f"[SCALING] RECOMMEND DISABLE: {reason}")
        return True, reason

    return False, "Weakest node within acceptable range"
