"""
cluster_lock.py — Cluster Lock During Training (Phase 4)

When training cycle starts: lock world_size.
If node joins mid-cycle: queue for next cycle.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional

logger = logging.getLogger(__name__)


@dataclass
class PendingNode:
    """A node queued for next cycle."""
    node_id: str
    device_type: str
    queued_at: str


@dataclass
class ClusterLockState:
    """Cluster lock state."""
    locked: bool
    locked_world_size: int
    pending_joins: List[PendingNode]
    cycle_id: int


class ClusterLock:
    """Locks cluster world_size during training cycle.

    No changes mid-cycle. Queued nodes join at next cycle.
    """

    def __init__(self):
        self._locked = False
        self._locked_world_size = 0
        self._pending: List[PendingNode] = []
        self._cycle_id = 0

    def lock(self, world_size: int):
        """Lock cluster for training cycle."""
        self._locked = True
        self._locked_world_size = world_size
        self._cycle_id += 1
        logger.info(
            f"[CLUSTER_LOCK] Locked: world_size={world_size} "
            f"cycle={self._cycle_id}"
        )

    def unlock(self) -> List[PendingNode]:
        """Unlock cluster, return pending nodes."""
        self._locked = False
        pending = list(self._pending)
        self._pending.clear()

        if pending:
            logger.info(
                f"[CLUSTER_LOCK] Unlocked: {len(pending)} pending nodes"
            )
        else:
            logger.info("[CLUSTER_LOCK] Unlocked: no pending nodes")

        return pending

    def request_join(self, node_id: str, device_type: str) -> bool:
        """Request to join cluster.

        If locked: queue for next cycle.
        If unlocked: allow immediately.
        """
        if self._locked:
            self._pending.append(PendingNode(
                node_id=node_id,
                device_type=device_type,
                queued_at=datetime.now().isoformat(),
            ))
            logger.info(
                f"[CLUSTER_LOCK] Queued: {node_id} "
                f"(locked, cycle {self._cycle_id})"
            )
            return False  # Queued, not joined
        return True  # Can join immediately

    def get_state(self) -> ClusterLockState:
        return ClusterLockState(
            locked=self._locked,
            locked_world_size=self._locked_world_size,
            pending_joins=list(self._pending),
            cycle_id=self._cycle_id,
        )

    @property
    def is_locked(self) -> bool:
        return self._locked

    @property
    def world_size(self) -> int:
        return self._locked_world_size
