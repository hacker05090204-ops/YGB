"""
driver_consistency.py — Driver Consistency Enforcement (Phase 3)

During cluster join, record CUDA/driver/compute cap.
Mismatch → allow training but disable determinism promotion.
Require re-sync before LIVE_READY.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class DriverInfo:
    """GPU driver info for a node."""
    node_id: str
    cuda_version: str
    driver_version: str
    compute_capability: str
    gpu_name: str


@dataclass
class ConsistencyCheck:
    """Result of driver consistency check."""
    consistent: bool
    determinism_allowed: bool
    live_ready_allowed: bool
    mismatches: List[str]
    nodes: List[DriverInfo]
    reason: str
    timestamp: str = ""


class DriverConsistency:
    """Enforces GPU driver consistency across cluster.

    If mismatch: training allowed, determinism promotion blocked.
    Require sync for LIVE_READY.
    """

    def __init__(self):
        self._nodes: Dict[str, DriverInfo] = {}

    def register_node(self, info: DriverInfo):
        """Register node driver info."""
        self._nodes[info.node_id] = info
        logger.info(
            f"[DRIVER] Registered: {info.node_id} "
            f"CUDA={info.cuda_version} driver={info.driver_version} "
            f"compute={info.compute_capability}"
        )

    def check(self) -> ConsistencyCheck:
        """Check driver consistency across all nodes."""
        if len(self._nodes) <= 1:
            return ConsistencyCheck(
                consistent=True,
                determinism_allowed=True,
                live_ready_allowed=True,
                mismatches=[],
                nodes=list(self._nodes.values()),
                reason="Single node — consistent",
                timestamp=datetime.now().isoformat(),
            )

        nodes = list(self._nodes.values())
        ref = nodes[0]
        mismatches = []

        for node in nodes[1:]:
            if node.cuda_version != ref.cuda_version:
                mismatches.append(
                    f"CUDA: {ref.node_id}={ref.cuda_version} "
                    f"≠ {node.node_id}={node.cuda_version}"
                )
            if node.driver_version != ref.driver_version:
                mismatches.append(
                    f"Driver: {ref.node_id}={ref.driver_version} "
                    f"≠ {node.node_id}={node.driver_version}"
                )
            if node.compute_capability != ref.compute_capability:
                mismatches.append(
                    f"Compute: {ref.node_id}={ref.compute_capability} "
                    f"≠ {node.node_id}={node.compute_capability}"
                )

        consistent = len(mismatches) == 0

        result = ConsistencyCheck(
            consistent=consistent,
            determinism_allowed=consistent,
            live_ready_allowed=consistent,
            mismatches=mismatches,
            nodes=nodes,
            reason="Consistent" if consistent
                   else f"{len(mismatches)} mismatch(es) — determinism disabled",
            timestamp=datetime.now().isoformat(),
        )

        icon = "✓" if consistent else "⚠"
        logger.info(f"[DRIVER] {icon} {result.reason}")
        for m in mismatches:
            logger.warning(f"  ≠ {m}")

        return result
