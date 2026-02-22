"""
authority_state_manager.py — Authority Resilience (Phase 1)

Persists authority state to disk after:
  - dataset lock
  - world size lock
  - shard allocation
  - epoch completion

On restart:
  - Reload cluster state
  - Validate all nodes rejoin
  - Resume from last checkpoint

Heartbeat monitor aborts training if authority loses quorum.
"""

import json
import logging
import os
import threading
import time
from dataclasses import dataclass, asdict, field
from datetime import datetime
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

STATE_PATH = os.path.join('secure_data', 'authority_state.json')


# =============================================================================
# STATE
# =============================================================================

@dataclass
class ShardAllocation:
    """Per-node shard assignment."""
    node_id: str
    shard_start: int
    shard_end: int
    shard_size: int
    optimal_batch: int


@dataclass
class AuthorityState:
    """Full authority cluster state — persisted to disk."""
    dataset_hash: str = ""
    dataset_locked: bool = False
    world_size: int = 0
    world_size_locked: bool = False
    shard_allocations: List[dict] = field(default_factory=list)
    last_completed_epoch: int = -1
    last_checkpoint_id: str = ""
    node_registry: Dict[str, dict] = field(default_factory=dict)
    timestamp: str = ""
    training_active: bool = False


# =============================================================================
# PERSIST / RELOAD
# =============================================================================

def persist_state(state: AuthorityState, path: str = STATE_PATH):
    """Atomically persist authority state to disk."""
    state.timestamp = datetime.now().isoformat()

    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp_path = path + ".tmp"

    with open(tmp_path, 'w') as f:
        json.dump(asdict(state), f, indent=2)
        f.flush()
        os.fsync(f.fileno())

    # Atomic rename
    if os.path.exists(path):
        os.replace(tmp_path, path)
    else:
        os.rename(tmp_path, path)

    logger.info(
        f"[AUTHORITY] State persisted: epoch={state.last_completed_epoch}, "
        f"world_size={state.world_size}, nodes={len(state.node_registry)}"
    )


def reload_state(path: str = STATE_PATH) -> Optional[AuthorityState]:
    """Reload authority state from disk on restart."""
    if not os.path.exists(path):
        logger.info("[AUTHORITY] No saved state found — fresh start")
        return None

    try:
        with open(path, 'r') as f:
            data = json.load(f)
        state = AuthorityState(**data)
        logger.info(
            f"[AUTHORITY] State reloaded: epoch={state.last_completed_epoch}, "
            f"world_size={state.world_size}, "
            f"nodes={len(state.node_registry)}"
        )
        return state
    except Exception as e:
        logger.error(f"[AUTHORITY] Failed to reload state: {e}")
        return None


# =============================================================================
# STATE TRANSITIONS (persist after each)
# =============================================================================

def lock_dataset(state: AuthorityState, dataset_hash: str) -> AuthorityState:
    """Lock dataset hash — no changes allowed after this."""
    state.dataset_hash = dataset_hash
    state.dataset_locked = True
    persist_state(state)
    logger.info(f"[AUTHORITY] Dataset locked: {dataset_hash[:16]}...")
    return state


def lock_world_size(state: AuthorityState, world_size: int) -> AuthorityState:
    """Lock world size — node count frozen for this session."""
    state.world_size = world_size
    state.world_size_locked = True
    persist_state(state)
    logger.info(f"[AUTHORITY] World size locked: {world_size}")
    return state


def set_shard_allocation(
    state: AuthorityState,
    allocations: List[ShardAllocation],
) -> AuthorityState:
    """Record shard allocations for all nodes."""
    state.shard_allocations = [asdict(a) for a in allocations]
    persist_state(state)
    logger.info(f"[AUTHORITY] Shard allocation set for {len(allocations)} nodes")
    return state


def complete_epoch(
    state: AuthorityState,
    epoch: int,
    checkpoint_id: str = "",
) -> AuthorityState:
    """Record epoch completion."""
    state.last_completed_epoch = epoch
    state.last_checkpoint_id = checkpoint_id
    persist_state(state)
    logger.info(f"[AUTHORITY] Epoch {epoch} completed, checkpoint={checkpoint_id}")
    return state


def register_node(
    state: AuthorityState,
    node_id: str,
    node_info: dict,
) -> AuthorityState:
    """Register a node in the authority."""
    state.node_registry[node_id] = {
        **node_info,
        'registered_at': datetime.now().isoformat(),
        'alive': True,
    }
    persist_state(state)
    logger.info(f"[AUTHORITY] Node registered: {node_id[:16]}...")
    return state


# =============================================================================
# REJOIN VALIDATION
# =============================================================================

def validate_rejoin(
    saved_state: AuthorityState,
    rejoining_node_ids: List[str],
) -> dict:
    """Validate that all expected nodes rejoin after restart.

    Returns:
        dict with 'valid', 'missing', 'unexpected' keys.
    """
    expected = set(saved_state.node_registry.keys())
    rejoining = set(rejoining_node_ids)

    missing = expected - rejoining
    unexpected = rejoining - expected

    valid = len(missing) == 0

    if missing:
        logger.warning(
            f"[AUTHORITY] Rejoin: {len(missing)} node(s) missing: "
            f"{[n[:16] + '...' for n in missing]}"
        )
    if unexpected:
        logger.info(
            f"[AUTHORITY] Rejoin: {len(unexpected)} new node(s) detected"
        )

    return {
        'valid': valid,
        'missing': list(missing),
        'unexpected': list(unexpected),
        'resume_epoch': saved_state.last_completed_epoch + 1,
        'checkpoint_id': saved_state.last_checkpoint_id,
    }


# =============================================================================
# HEARTBEAT MONITOR
# =============================================================================

class AuthorityHeartbeat:
    """Background heartbeat monitor for authority quorum.

    Pings all registered nodes. If >50% unresponsive for
    consecutive intervals, aborts training.
    """

    def __init__(
        self,
        state: AuthorityState,
        interval_sec: float = 5.0,
        max_failures: int = 3,
        check_fn=None,
    ):
        self.state = state
        self.interval = interval_sec
        self.max_failures = max_failures
        self.check_fn = check_fn or self._default_check
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self._consecutive_failures = 0
        self.quorum_lost = False

    def start(self):
        """Start heartbeat monitoring in background thread."""
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._monitor_loop,
            daemon=True,
            name="authority-heartbeat",
        )
        self._thread.start()
        logger.info("[HEARTBEAT] Monitor started")

    def stop(self):
        """Stop the heartbeat monitor."""
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=self.interval * 2)
        logger.info("[HEARTBEAT] Monitor stopped")

    def _monitor_loop(self):
        while not self._stop.is_set():
            alive = 0
            total = len(self.state.node_registry)

            if total == 0:
                self._stop.wait(self.interval)
                continue

            for node_id, info in self.state.node_registry.items():
                if self.check_fn(node_id, info):
                    alive += 1

            quorum_ratio = alive / total if total > 0 else 0

            if quorum_ratio <= 0.5:
                self._consecutive_failures += 1
                logger.warning(
                    f"[HEARTBEAT] Quorum low: {alive}/{total} alive "
                    f"(failure {self._consecutive_failures}/{self.max_failures})"
                )
                if self._consecutive_failures >= self.max_failures:
                    self.quorum_lost = True
                    logger.error(
                        "[HEARTBEAT] QUORUM LOST — training must abort"
                    )
                    return
            else:
                self._consecutive_failures = 0

            self._stop.wait(self.interval)

    @staticmethod
    def _default_check(node_id: str, info: dict) -> bool:
        """Default check — assumes all local nodes are alive."""
        return info.get('alive', True)
