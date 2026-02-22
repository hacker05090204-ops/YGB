"""
safe_shutdown.py — Safe Shutdown (Phase 9)

If owner laptop closes:
1. Leader heartbeat lost
2. Election triggered
3. Secondary becomes leader
4. Continue training seamlessly

If all nodes offline:
Cluster safely halts — state preserved.
"""

import json
import logging
import os
import threading
import time
from dataclasses import dataclass, asdict, field
from datetime import datetime
from typing import Dict, List, Optional, Callable

logger = logging.getLogger(__name__)

SHUTDOWN_STATE_PATH = os.path.join('secure_data', 'shutdown_state.json')


@dataclass
class ShutdownEvent:
    """A detected shutdown event."""
    event_type: str      # leader_lost / node_lost / all_offline / manual
    node_id: str
    detected_at: str
    action_taken: str


@dataclass
class ShutdownState:
    """State preserved during shutdown."""
    events: List[dict] = field(default_factory=list)
    cluster_halted: bool = False
    state_preserved: bool = False
    new_leader: str = ""
    training_continued: bool = False
    timestamp: str = ""


class SafeShutdownManager:
    """Manages graceful shutdown and failover.

    Monitors leader heartbeat and triggers failover
    when the leader goes offline.
    """

    def __init__(
        self,
        heartbeat_timeout: float = 10.0,
        check_interval: float = 2.0,
        on_leader_lost: Optional[Callable] = None,
        on_all_offline: Optional[Callable] = None,
    ):
        self.heartbeat_timeout = heartbeat_timeout
        self.check_interval = check_interval
        self.on_leader_lost = on_leader_lost
        self.on_all_offline = on_all_offline

        self._nodes: Dict[str, dict] = {}
        self._leader_id: Optional[str] = None
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self._events: List[ShutdownEvent] = []
        self._new_leader: Optional[str] = None
        self._halted = False

    def register_node(self, node_id: str, is_leader: bool = False, priority: int = 50):
        """Register a node for monitoring."""
        self._nodes[node_id] = {
            'alive': True,
            'is_leader': is_leader,
            'priority': priority,
            'last_heartbeat': datetime.now().isoformat(),
        }
        if is_leader:
            self._leader_id = node_id

    def heartbeat(self, node_id: str):
        """Update a node's heartbeat."""
        if node_id in self._nodes:
            self._nodes[node_id]['last_heartbeat'] = datetime.now().isoformat()
            self._nodes[node_id]['alive'] = True

    def mark_offline(self, node_id: str):
        """Mark a node as offline (e.g. laptop lid closed)."""
        if node_id in self._nodes:
            self._nodes[node_id]['alive'] = False
            logger.warning(f"[SHUTDOWN] Node {node_id[:16]}... marked offline")

    def start_monitoring(self):
        """Start background shutdown monitor."""
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._monitor_loop,
            daemon=True,
            name="shutdown-monitor",
        )
        self._thread.start()
        logger.info("[SHUTDOWN] Monitor started")

    def stop_monitoring(self):
        """Stop shutdown monitor."""
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=self.check_interval * 2)

    def _monitor_loop(self):
        while not self._stop.is_set():
            now = datetime.now()
            alive_nodes = []
            dead_nodes = []

            for nid, info in self._nodes.items():
                if not info.get('alive', True):
                    dead_nodes.append(nid)
                    continue

                # Check heartbeat timeout
                last_hb = info.get('last_heartbeat', '')
                if last_hb:
                    try:
                        dt = datetime.fromisoformat(last_hb)
                        elapsed = (now - dt).total_seconds()
                        if elapsed > self.heartbeat_timeout:
                            info['alive'] = False
                            dead_nodes.append(nid)
                            continue
                    except Exception:
                        pass

                alive_nodes.append(nid)

            # Check: leader lost?
            if self._leader_id and self._leader_id in dead_nodes:
                self._handle_leader_lost(alive_nodes)

            # Check: all offline?
            if len(alive_nodes) == 0 and len(self._nodes) > 0:
                self._handle_all_offline()
                return  # Stop monitoring

            self._stop.wait(self.check_interval)

    def _handle_leader_lost(self, alive_nodes: List[str]):
        """Handle leader going offline — trigger failover."""
        event = ShutdownEvent(
            event_type="leader_lost",
            node_id=self._leader_id or "",
            detected_at=datetime.now().isoformat(),
            action_taken="election_triggered",
        )
        self._events.append(event)

        logger.warning(
            f"[SHUTDOWN] Leader {self._leader_id[:16]}... lost — "
            f"triggering failover"
        )

        # Elect new leader: highest priority alive node
        new_leader = None
        best_priority = -1
        for nid in alive_nodes:
            p = self._nodes[nid].get('priority', 0)
            if p > best_priority:
                best_priority = p
                new_leader = nid

        if new_leader:
            self._nodes[new_leader]['is_leader'] = True
            self._leader_id = new_leader
            self._new_leader = new_leader

            logger.info(
                f"[SHUTDOWN] New leader: {new_leader[:16]}... "
                f"(priority={best_priority}) — training continues"
            )

            if self.on_leader_lost:
                self.on_leader_lost(new_leader)
        else:
            logger.error("[SHUTDOWN] No alive nodes for failover")
            self._handle_all_offline()

    def _handle_all_offline(self):
        """Handle all nodes going offline — safe halt."""
        event = ShutdownEvent(
            event_type="all_offline",
            node_id="",
            detected_at=datetime.now().isoformat(),
            action_taken="cluster_halted",
        )
        self._events.append(event)
        self._halted = True

        logger.error("[SHUTDOWN] ALL NODES OFFLINE — cluster safely halted")

        if self.on_all_offline:
            self.on_all_offline()

        self._save_state()

    def _save_state(self):
        """Persist shutdown state."""
        state = ShutdownState(
            events=[asdict(e) for e in self._events],
            cluster_halted=self._halted,
            state_preserved=True,
            new_leader=self._new_leader or "",
            training_continued=self._new_leader is not None,
            timestamp=datetime.now().isoformat(),
        )
        os.makedirs(os.path.dirname(SHUTDOWN_STATE_PATH) or '.', exist_ok=True)
        with open(SHUTDOWN_STATE_PATH, 'w') as f:
            json.dump(asdict(state), f, indent=2)

    def get_failover_report(self) -> dict:
        """Get current failover state."""
        return {
            'leader': self._leader_id,
            'new_leader': self._new_leader,
            'halted': self._halted,
            'events': len(self._events),
            'alive_count': sum(
                1 for v in self._nodes.values() if v.get('alive', True)
            ),
            'total_nodes': len(self._nodes),
        }

    @property
    def is_halted(self) -> bool:
        return self._halted

    @property
    def new_leader(self) -> Optional[str]:
        return self._new_leader
