"""
ha_leader.py — High Availability Leader (Phase 7)

Python wrapper for leader election:
1. Leader election with term fencing
2. Owner node always highest priority when online
3. If owner offline → RTX3050 temporary leader
4. On rejoin → term reconciliation
"""

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

OWNER_PRIORITY = 100
SECONDARY_PRIORITY = 80
DEFAULT_PRIORITY = 50


@dataclass
class LeaderState:
    """Current leader state."""
    leader_id: str
    term: int
    fencing_token: int
    is_owner: bool
    temporary: bool
    nodes: Dict[str, dict] = field(default_factory=dict)


class HALeaderManager:
    """Manages HA leader election with owner priority.

    Rules:
    - Owner node (RTX2050) = priority 100
    - Secondary (RTX3050) = priority 80
    - Other nodes = priority 50
    - Owner always reclaims leadership on rejoin
    """

    def __init__(
        self,
        owner_node_id: str = "",
        secondary_node_id: str = "",
    ):
        self.owner_node_id = owner_node_id
        self.secondary_node_id = secondary_node_id
        self._nodes: Dict[str, dict] = {}
        self._term = 0
        self._fencing_token = 0
        self._leader_id: Optional[str] = None

    def register_node(
        self,
        node_id: str,
        device_name: str = "",
        priority: Optional[int] = None,
    ):
        """Register a node for election."""
        if priority is None:
            if node_id == self.owner_node_id:
                priority = OWNER_PRIORITY
            elif node_id == self.secondary_node_id:
                priority = SECONDARY_PRIORITY
            else:
                priority = DEFAULT_PRIORITY

        self._nodes[node_id] = {
            'device_name': device_name,
            'priority': priority,
            'alive': True,
            'joined_at': datetime.now().isoformat(),
        }

        logger.info(
            f"[HA_LEADER] Registered: {node_id[:16]}... "
            f"priority={priority} device={device_name}"
        )

    def run_election(self) -> LeaderState:
        """Run leader election.

        Highest-priority alive node wins.
        """
        self._term += 1
        self._fencing_token = self._term * 1000 + int(time.time()) % 1000

        alive = {
            nid: info for nid, info in self._nodes.items()
            if info.get('alive', True)
        }

        if not alive:
            logger.error("[HA_LEADER] No alive nodes")
            return LeaderState(
                leader_id="", term=self._term,
                fencing_token=self._fencing_token,
                is_owner=False, temporary=True, nodes=self._nodes,
            )

        # Pick highest priority
        winner = max(alive, key=lambda nid: alive[nid]['priority'])
        self._leader_id = winner

        is_owner = winner == self.owner_node_id
        temporary = not is_owner

        state = LeaderState(
            leader_id=winner,
            term=self._term,
            fencing_token=self._fencing_token,
            is_owner=is_owner,
            temporary=temporary,
            nodes=self._nodes,
        )

        logger.info(
            f"[HA_LEADER] Term {self._term}: leader={winner[:16]}... "
            f"{'OWNER' if is_owner else 'TEMPORARY'} "
            f"fence={self._fencing_token}"
        )

        return state

    def mark_offline(self, node_id: str):
        """Mark node as offline."""
        if node_id in self._nodes:
            self._nodes[node_id]['alive'] = False
            logger.info(f"[HA_LEADER] Node offline: {node_id[:16]}...")

    def mark_online(self, node_id: str):
        """Mark node as online (rejoin)."""
        if node_id in self._nodes:
            self._nodes[node_id]['alive'] = True
            logger.info(f"[HA_LEADER] Node online: {node_id[:16]}...")

    def reconcile_on_rejoin(self, rejoining_node_id: str) -> LeaderState:
        """Reconcile leadership when a node rejoins.

        If owner rejoins → re-election (owner wins).
        If non-owner rejoins → no change.
        """
        self.mark_online(rejoining_node_id)

        if rejoining_node_id == self.owner_node_id:
            logger.info(
                "[HA_LEADER] Owner rejoined — re-election triggered"
            )
            return self.run_election()
        else:
            logger.info(
                f"[HA_LEADER] Non-owner rejoined: {rejoining_node_id[:16]}... "
                f"— no leadership change"
            )
            return self.get_state()

    def get_state(self) -> LeaderState:
        """Get current leader state."""
        is_owner = self._leader_id == self.owner_node_id
        return LeaderState(
            leader_id=self._leader_id or "",
            term=self._term,
            fencing_token=self._fencing_token,
            is_owner=is_owner,
            temporary=not is_owner,
            nodes=self._nodes,
        )

    @property
    def leader(self) -> Optional[str]:
        return self._leader_id

    @property
    def term(self) -> int:
        return self._term
