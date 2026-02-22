"""
standalone_mode.py — Single Node Auto Start + Standalone Cluster (Phase 1 & 4)

If only one node: world_size=1, start immediately.
No mandatory cluster quorum.
If additional nodes join: scale dynamically.
If world_size >= 2: DDP enabled.
"""

import logging
import os
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class NodeInfo:
    """A cluster node."""
    node_id: str
    device_type: str    # cuda / mps / cpu
    device_name: str
    available: bool = True
    joined_at: str = ""


@dataclass
class ClusterMode:
    """Current cluster mode."""
    mode: str               # standalone / ddp
    world_size: int
    leader: str
    nodes: List[str]
    ddp_enabled: bool
    quorum_required: bool   # Always False
    can_start: bool


class StandaloneCluster:
    """Single-node auto-start with dynamic scale-up.

    Rules:
    1. world_size=1 → start immediately (standalone)
    2. No quorum requirement
    3. world_size≥2 → DDP enabled
    4. Nodes can join/leave without blocking
    """

    def __init__(self):
        self._nodes: Dict[str, NodeInfo] = {}
        self._leader: Optional[str] = None

    def register_node(self, node: NodeInfo):
        """Register a node. First CUDA node becomes leader."""
        node.joined_at = datetime.now().isoformat()
        self._nodes[node.node_id] = node

        if self._leader is None and node.device_type == "cuda":
            self._leader = node.node_id
            logger.info(
                f"[CLUSTER] Leader elected: {node.node_id} "
                f"({node.device_name})"
            )

        logger.info(
            f"[CLUSTER] Node joined: {node.node_id} "
            f"({node.device_type}) — world_size={self.world_size}"
        )

    def remove_node(self, node_id: str):
        """Remove a node without blocking training."""
        if node_id in self._nodes:
            del self._nodes[node_id]
            # Re-elect leader if needed
            if self._leader == node_id:
                self._leader = None
                for nid, n in self._nodes.items():
                    if n.device_type == "cuda" and n.available:
                        self._leader = nid
                        break
            logger.info(
                f"[CLUSTER] Node left: {node_id} — "
                f"world_size={self.world_size}"
            )

    def get_mode(self) -> ClusterMode:
        """Get current cluster mode.

        world_size=1 → standalone
        world_size≥2 → ddp
        Always can_start=True (no quorum)
        """
        cuda_nodes = [
            n for n in self._nodes.values()
            if n.device_type == "cuda" and n.available
        ]
        ws = max(len(cuda_nodes), 1)
        mode = "ddp" if ws >= 2 else "standalone"

        return ClusterMode(
            mode=mode,
            world_size=ws,
            leader=self._leader or "",
            nodes=[n.node_id for n in cuda_nodes],
            ddp_enabled=(ws >= 2),
            quorum_required=False,
            can_start=True,  # Always start
        )

    def setup_env(self) -> Dict[str, str]:
        """Set up environment for training."""
        cm = self.get_mode()
        env = {
            'WORLD_SIZE': str(cm.world_size),
            'RANK': '0',
            'LOCAL_RANK': '0',
            'MASTER_ADDR': '127.0.0.1',
            'MASTER_PORT': '29500',
        }

        if cm.mode == "standalone":
            logger.info(
                f"[CLUSTER] Standalone mode: "
                f"leader={cm.leader} world_size=1"
            )
        else:
            logger.info(
                f"[CLUSTER] DDP mode: {cm.world_size} nodes, "
                f"leader={cm.leader}"
            )

        return env

    @property
    def world_size(self) -> int:
        cuda = [
            n for n in self._nodes.values()
            if n.device_type == "cuda" and n.available
        ]
        return max(len(cuda), 1)

    @property
    def can_start(self) -> bool:
        return True  # No quorum needed

    @property
    def leader(self) -> Optional[str]:
        return self._leader
