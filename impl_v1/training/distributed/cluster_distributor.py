"""
cluster_distributor.py — Cluster Distribution (Phase 4)

All CUDA nodes join DDP.
MPS nodes act as shard workers.
CPU-only nodes validation only.

Ensure scaling_efficiency > 0.75, else rebalance.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

EFFICIENCY_THRESHOLD = 0.75


@dataclass
class ClusterNode:
    """A node in the training cluster."""
    node_id: str
    device_type: str    # cuda / mps / cpu
    device_name: str
    vram_mb: float
    role: str = ""      # ddp_worker / shard_worker / validator
    alive: bool = True
    sps: float = 0.0


@dataclass
class ClusterDistribution:
    """How work is distributed across cluster."""
    ddp_nodes: List[str]
    shard_nodes: List[str]
    validator_nodes: List[str]
    world_size: int
    scaling_efficiency: float
    balanced: bool


class ClusterDistributor:
    """Distributes workload across heterogeneous cluster.

    CUDA → DDP training workers
    MPS  → shard replication workers
    CPU  → validation only
    """

    def __init__(self):
        self._nodes: Dict[str, ClusterNode] = {}
        self._baseline_sps: Dict[str, float] = {}

    def register_node(self, node: ClusterNode):
        """Register a cluster node."""
        # Auto-assign role
        if node.device_type == "cuda":
            node.role = "ddp_worker"
        elif node.device_type == "mps":
            node.role = "shard_worker"
        else:
            node.role = "validator"

        self._nodes[node.node_id] = node
        logger.info(
            f"[CLUSTER] Registered: {node.node_id} "
            f"({node.device_name}) → {node.role}"
        )

    def set_baseline_sps(self, node_id: str, sps: float):
        """Set single-node baseline SPS for efficiency calc."""
        self._baseline_sps[node_id] = sps

    def distribute(self) -> ClusterDistribution:
        """Compute optimal work distribution."""
        ddp = [n.node_id for n in self._nodes.values()
               if n.role == "ddp_worker" and n.alive]
        shard = [n.node_id for n in self._nodes.values()
                 if n.role == "shard_worker" and n.alive]
        validators = [n.node_id for n in self._nodes.values()
                      if n.role == "validator" and n.alive]

        # Scaling efficiency
        cluster_sps = sum(
            n.sps for n in self._nodes.values()
            if n.role == "ddp_worker" and n.alive
        )
        baseline_sum = sum(
            self._baseline_sps.get(nid, 0)
            for nid in ddp
        )
        efficiency = cluster_sps / max(baseline_sum, 1.0)
        balanced = efficiency >= EFFICIENCY_THRESHOLD

        dist = ClusterDistribution(
            ddp_nodes=ddp,
            shard_nodes=shard,
            validator_nodes=validators,
            world_size=len(ddp),
            scaling_efficiency=round(efficiency, 4),
            balanced=balanced,
        )

        if balanced:
            logger.info(
                f"[CLUSTER] ✓ Balanced: eff={efficiency:.2%} "
                f"world_size={len(ddp)}"
            )
        else:
            logger.warning(
                f"[CLUSTER] ✗ Imbalanced: eff={efficiency:.2%} "
                f"< {EFFICIENCY_THRESHOLD:.0%} — rebalancing"
            )

        return dist

    def rebalance(self) -> ClusterDistribution:
        """Rebalance: remove weakest DDP node if below threshold."""
        dist = self.distribute()

        if dist.balanced or len(dist.ddp_nodes) <= 1:
            return dist

        # Find weakest DDP node
        ddp_nodes = [
            self._nodes[nid] for nid in dist.ddp_nodes
        ]
        weakest = min(ddp_nodes, key=lambda n: n.sps)

        if weakest.sps > 0:
            weakest.role = "shard_worker"
            logger.info(
                f"[CLUSTER] Rebalanced: {weakest.node_id} "
                f"demoted to shard_worker (sps={weakest.sps:.0f})"
            )

        return self.distribute()

    def mark_offline(self, node_id: str):
        if node_id in self._nodes:
            self._nodes[node_id].alive = False

    def mark_online(self, node_id: str):
        if node_id in self._nodes:
            self._nodes[node_id].alive = True

    def update_sps(self, node_id: str, sps: float):
        if node_id in self._nodes:
            self._nodes[node_id].sps = sps
