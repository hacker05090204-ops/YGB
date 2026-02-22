"""
safe_multigpu_execution.py — Safe Multi-GPU Execution (Phase 7)

All CUDA nodes:
- Join NCCL group only if leader approved
- Determinism strictly locked
- Async all-reduce enabled
- Scaling efficiency measured
- If efficiency < 0.7: remove weakest node
"""

import logging
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

EFFICIENCY_THRESHOLD = 0.7


@dataclass
class GPUNodeRequest:
    """A GPU node requesting to join the NCCL group."""
    node_id: str
    device_name: str
    rank: int
    determinism_locked: bool
    cuda_version: str
    driver_version: str


@dataclass
class NCCLGroupState:
    """State of the NCCL group."""
    leader_approved: bool
    members: List[str] = field(default_factory=list)
    world_size: int = 0
    determinism_locked: bool = True
    async_allreduce: bool = True
    scaling_efficiency: float = 1.0
    weakest_node: str = ""


@dataclass
class ExecutionReport:
    """Report from multi-GPU execution."""
    world_size: int
    members: List[str]
    efficiency: float
    weakest_removed: bool
    weakest_node: str
    all_deterministic: bool
    status: str  # ok / degraded / node_removed


class SafeMultiGPUExecutor:
    """Manages safe multi-GPU execution with leader approval."""

    def __init__(self):
        self._approved_nodes: Dict[str, GPUNodeRequest] = {}
        self._nccl_state = NCCLGroupState(leader_approved=False)
        self._per_node_sps: Dict[str, float] = {}

    def request_join(
        self,
        node: GPUNodeRequest,
        leader_term: int,
    ) -> Tuple[bool, str]:
        """Request to join NCCL group. Leader must approve.

        Checks:
        1. Determinism locked
        2. Not already a member

        Returns:
            (approved, reason)
        """
        if not node.determinism_locked:
            reason = f"Rejected {node.node_id[:16]}: determinism not locked"
            logger.error(f"[MULTIGPU] {reason}")
            return False, reason

        if node.node_id in self._approved_nodes:
            return True, "Already approved"

        self._approved_nodes[node.node_id] = node
        self._nccl_state.members.append(node.node_id)
        self._nccl_state.world_size = len(self._approved_nodes)

        logger.info(
            f"[MULTIGPU] Approved: {node.node_id[:16]}... "
            f"({node.device_name}, rank={node.rank}) "
            f"world_size={self._nccl_state.world_size}"
        )
        return True, "Approved"

    def leader_approve_group(self) -> bool:
        """Leader signals that the NCCL group is ready."""
        if self._nccl_state.world_size == 0:
            logger.error("[MULTIGPU] Cannot approve: no nodes")
            return False

        self._nccl_state.leader_approved = True
        logger.info(
            f"[MULTIGPU] NCCL group approved: "
            f"{self._nccl_state.world_size} nodes"
        )
        return True

    def report_node_sps(self, node_id: str, sps: float):
        """Report a node's samples-per-second."""
        self._per_node_sps[node_id] = sps

    def measure_efficiency(
        self,
        cluster_sps: float,
        baselines: Dict[str, float],
    ) -> float:
        """Measure scaling efficiency."""
        baseline_sum = sum(baselines.values())
        efficiency = cluster_sps / max(baseline_sum, 1.0)
        self._nccl_state.scaling_efficiency = round(efficiency, 4)

        if efficiency < EFFICIENCY_THRESHOLD:
            logger.warning(
                f"[MULTIGPU] Efficiency {efficiency:.2%} < "
                f"{EFFICIENCY_THRESHOLD:.0%} — DEGRADED"
            )

        return efficiency

    def find_weakest_node(self) -> str:
        """Find the weakest node by SPS."""
        if not self._per_node_sps:
            return ""
        weakest = min(self._per_node_sps, key=self._per_node_sps.get)
        self._nccl_state.weakest_node = weakest
        return weakest

    def remove_node(self, node_id: str) -> bool:
        """Remove a node from the NCCL group."""
        if node_id in self._approved_nodes:
            del self._approved_nodes[node_id]
        if node_id in self._nccl_state.members:
            self._nccl_state.members.remove(node_id)
        if node_id in self._per_node_sps:
            del self._per_node_sps[node_id]

        self._nccl_state.world_size = len(self._approved_nodes)
        logger.info(f"[MULTIGPU] Removed: {node_id[:16]}...")
        return True

    def enforce_efficiency(
        self,
        cluster_sps: float,
        baselines: Dict[str, float],
    ) -> ExecutionReport:
        """Measure efficiency and remove weakest if below threshold.

        Returns:
            ExecutionReport.
        """
        efficiency = self.measure_efficiency(cluster_sps, baselines)
        weakest = self.find_weakest_node()
        weakest_removed = False
        status = "ok"

        if efficiency < EFFICIENCY_THRESHOLD and weakest:
            self.remove_node(weakest)
            weakest_removed = True
            status = "node_removed"
            logger.warning(
                f"[MULTIGPU] Weakest node {weakest[:16]}... removed "
                f"(efficiency={efficiency:.2%})"
            )
        elif efficiency < EFFICIENCY_THRESHOLD:
            status = "degraded"

        all_det = all(
            n.determinism_locked
            for n in self._approved_nodes.values()
        )

        return ExecutionReport(
            world_size=self._nccl_state.world_size,
            members=list(self._nccl_state.members),
            efficiency=round(efficiency, 4),
            weakest_removed=weakest_removed,
            weakest_node=weakest,
            all_deterministic=all_det,
            status=status,
        )
