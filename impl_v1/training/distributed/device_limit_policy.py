"""
device_limit_policy.py — Max Device Limit Policy (Phase 7)

If device_count > 6:
  Run scaling benchmark first.
  Enable new nodes only if efficiency remains > 0.75.
  Prevent cluster from degrading by over-scaling.

Hard cap: 10 devices.
"""

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# =============================================================================
# LIMITS
# =============================================================================

SOFT_LIMIT = 6           # Above this → benchmark required
HARD_LIMIT = 10          # Absolute maximum
MIN_EFFICIENCY = 0.75    # Required efficiency to approve scale-up


# =============================================================================
# TYPES
# =============================================================================

@dataclass
class ScaleRequest:
    """Request to add a new device to the cluster."""
    node_id: str
    device_name: str
    vram_mb: float
    estimated_sps: float


@dataclass
class ScaleDecision:
    """Decision on a scale request."""
    approved: bool
    reason: str
    current_count: int
    requested_count: int
    predicted_efficiency: float
    benchmark_required: bool
    benchmark_passed: bool


# =============================================================================
# POLICY ENGINE
# =============================================================================

def evaluate_scale_request(
    current_nodes: List[dict],
    new_node: ScaleRequest,
    current_baselines: Dict[str, float],
    current_cluster_sps: float,
) -> ScaleDecision:
    """Evaluate whether a new device should be admitted.

    Args:
        current_nodes: Currently active nodes.
        new_node: The requesting new node.
        current_baselines: Per-node baseline sps.
        current_cluster_sps: Current cluster throughput.

    Returns:
        ScaleDecision with approve/deny.
    """
    current_count = len(current_nodes)
    requested_count = current_count + 1

    # Hard cap
    if requested_count > HARD_LIMIT:
        reason = (
            f"DENIED: Hard limit ({HARD_LIMIT}) exceeded. "
            f"Current={current_count}, requested={requested_count}"
        )
        logger.error(f"[DEVICE_POLICY] {reason}")
        return ScaleDecision(
            approved=False, reason=reason,
            current_count=current_count,
            requested_count=requested_count,
            predicted_efficiency=0.0,
            benchmark_required=True,
            benchmark_passed=False,
        )

    # Below soft limit → approve immediately
    if requested_count <= SOFT_LIMIT:
        reason = f"APPROVED: {requested_count} <= soft limit ({SOFT_LIMIT})"
        logger.info(f"[DEVICE_POLICY] {reason}")
        return ScaleDecision(
            approved=True, reason=reason,
            current_count=current_count,
            requested_count=requested_count,
            predicted_efficiency=1.0,
            benchmark_required=False,
            benchmark_passed=True,
        )

    # Above soft limit → need benchmark
    benchmark_required = True
    sum_baselines = sum(current_baselines.values()) + new_node.estimated_sps

    # Predict efficiency with communication overhead model
    # Simplified: overhead grows ~O(n) with node count
    overhead_factor = 1.0 - (0.03 * requested_count)  # ~3% per node
    predicted_sps = sum_baselines * max(overhead_factor, 0.5)
    predicted_efficiency = predicted_sps / max(sum_baselines, 1.0)

    benchmark_passed = predicted_efficiency >= MIN_EFFICIENCY

    if benchmark_passed:
        reason = (
            f"APPROVED: predicted efficiency {predicted_efficiency:.2%} "
            f">= {MIN_EFFICIENCY:.0%} for {requested_count} devices"
        )
        logger.info(f"[DEVICE_POLICY] {reason}")
    else:
        reason = (
            f"DENIED: predicted efficiency {predicted_efficiency:.2%} "
            f"< {MIN_EFFICIENCY:.0%} for {requested_count} devices — "
            f"cluster would degrade"
        )
        logger.warning(f"[DEVICE_POLICY] {reason}")

    return ScaleDecision(
        approved=benchmark_passed,
        reason=reason,
        current_count=current_count,
        requested_count=requested_count,
        predicted_efficiency=round(predicted_efficiency, 4),
        benchmark_required=benchmark_required,
        benchmark_passed=benchmark_passed,
    )


def get_policy_summary(current_count: int) -> dict:
    """Get current device limit policy summary."""
    return {
        'current_count': current_count,
        'soft_limit': SOFT_LIMIT,
        'hard_limit': HARD_LIMIT,
        'min_efficiency': MIN_EFFICIENCY,
        'can_add': current_count < HARD_LIMIT,
        'benchmark_required': current_count >= SOFT_LIMIT,
    }
