"""
cluster_authority.py — Unified Cluster Authority (Phase 1)

Production-grade authority that survives crash/restart.

Manages:
  - Persistent cluster state (cluster_state.json)
  - Node registration and lifecycle
  - Dataset lock, world size lock, shard allocation
  - Epoch tracking with scaling efficiency
  - Heartbeat-based node monitoring
  - Crash recovery and quorum validation
"""

import hashlib
import json
import logging
import os
import threading
import time
from dataclasses import dataclass, asdict, field
from datetime import datetime
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

STATE_DIR = os.path.join('secure_data')
STATE_FILE = 'cluster_state.json'
STATE_PATH = os.path.join(STATE_DIR, STATE_FILE)


# =============================================================================
# CLUSTER STATE
# =============================================================================

@dataclass
class NodeInfo:
    """Registered node information."""
    node_id: str
    device_name: str
    device_type: str       # 'cuda', 'mps', 'cpu'
    vram_mb: float
    rank: int
    shard_start: int = 0
    shard_end: int = 0
    shard_proportion: float = 0.0
    optimal_batch: int = 0
    baseline_sps: float = 0.0
    last_heartbeat: str = ""
    alive: bool = True


@dataclass
class ClusterState:
    """Full persistent cluster state."""
    # Identity
    dataset_hash: str = ""
    world_size: int = 0
    training_active: bool = False

    # Locks
    dataset_locked: bool = False
    world_size_locked: bool = False

    # Nodes
    active_nodes: Dict[str, dict] = field(default_factory=dict)
    shard_proportions: Dict[str, float] = field(default_factory=dict)

    # Epoch tracking
    epoch_number: int = -1
    merged_weight_hash: str = ""
    scaling_efficiency: float = 0.0

    # Per-node perf
    per_node_sps: Dict[str, float] = field(default_factory=dict)
    cluster_sps: float = 0.0

    # Meta
    timestamp: str = ""
    last_checkpoint_id: str = ""
    authority_id: str = ""


# =============================================================================
# ATOMIC PERSISTENCE
# =============================================================================

def _atomic_write(data: dict, path: str):
    """Write JSON atomically: temp file → fsync → rename."""
    os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, 'w') as f:
        json.dump(data, f, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def _load_json(path: str) -> Optional[dict]:
    """Load JSON from disk."""
    if not os.path.exists(path):
        return None
    try:
        with open(path, 'r') as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"[AUTHORITY] Load failed: {e}")
        return None


# =============================================================================
# CLUSTER AUTHORITY
# =============================================================================

class ClusterAuthority:
    """Unified cluster authority.

    Orchestrates all cluster state transitions with atomic persistence.
    Survives crash/restart via cluster_state.json.
    """

    def __init__(
        self,
        authority_id: str = "",
        state_path: str = STATE_PATH,
        heartbeat_interval: float = 5.0,
        heartbeat_timeout: float = 15.0,
    ):
        self.state_path = state_path
        self.heartbeat_interval = heartbeat_interval
        self.heartbeat_timeout = heartbeat_timeout
        self._heartbeat_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self.abort_requested = False
        self.abort_reason = ""

        # Try reload, else fresh
        loaded = self._load_state()
        if loaded:
            self.state = loaded
            logger.info(
                f"[AUTHORITY] Resumed from epoch={self.state.epoch_number}, "
                f"world_size={self.state.world_size}"
            )
        else:
            self.state = ClusterState(authority_id=authority_id or self._gen_id())
            logger.info("[AUTHORITY] Fresh cluster state created")

    @staticmethod
    def _gen_id() -> str:
        return hashlib.sha256(
            f"authority-{time.time()}".encode()
        ).hexdigest()[:16]

    # -----------------------------------------------------------------
    # PERSISTENCE
    # -----------------------------------------------------------------

    def _persist(self):
        """Persist current state atomically."""
        self.state.timestamp = datetime.now().isoformat()
        _atomic_write(asdict(self.state), self.state_path)
        logger.debug("[AUTHORITY] State persisted")

    def _load_state(self) -> Optional[ClusterState]:
        """Load state from disk."""
        data = _load_json(self.state_path)
        if data:
            try:
                return ClusterState(**data)
            except Exception as e:
                logger.error(f"[AUTHORITY] Parse error: {e}")
        return None

    # -----------------------------------------------------------------
    # NODE MANAGEMENT
    # -----------------------------------------------------------------

    def register_node(self, node: NodeInfo) -> bool:
        """Register a node. Fails if world_size locked and full."""
        if self.state.world_size_locked:
            if len(self.state.active_nodes) >= self.state.world_size:
                logger.error(
                    f"[AUTHORITY] Cannot register {node.node_id[:16]}: "
                    f"world_size={self.state.world_size} locked and full"
                )
                return False

        self.state.active_nodes[node.node_id] = asdict(node)
        self.state.active_nodes[node.node_id]['last_heartbeat'] = (
            datetime.now().isoformat()
        )
        self._persist()
        logger.info(
            f"[AUTHORITY] Node registered: {node.node_id[:16]}... "
            f"({node.device_name}, rank={node.rank})"
        )
        return True

    def deregister_node(self, node_id: str):
        """Remove a node from the cluster."""
        if node_id in self.state.active_nodes:
            del self.state.active_nodes[node_id]
            if node_id in self.state.shard_proportions:
                del self.state.shard_proportions[node_id]
            self._persist()
            logger.info(f"[AUTHORITY] Node deregistered: {node_id[:16]}...")

    def update_heartbeat(self, node_id: str):
        """Update a node's heartbeat timestamp."""
        if node_id in self.state.active_nodes:
            self.state.active_nodes[node_id]['last_heartbeat'] = (
                datetime.now().isoformat()
            )
            self.state.active_nodes[node_id]['alive'] = True

    # -----------------------------------------------------------------
    # LOCKS
    # -----------------------------------------------------------------

    def lock_dataset(self, dataset_hash: str):
        """Lock the dataset hash — immutable after this."""
        self.state.dataset_hash = dataset_hash
        self.state.dataset_locked = True
        self._persist()
        logger.info(f"[AUTHORITY] Dataset locked: {dataset_hash[:16]}...")

    def lock_world_size(self, world_size: int):
        """Lock world size — no more nodes accepted."""
        self.state.world_size = world_size
        self.state.world_size_locked = True
        self._persist()
        logger.info(f"[AUTHORITY] World size locked: {world_size}")

    def allocate_shards(self, proportions: Dict[str, float]):
        """Set shard allocations for all nodes."""
        self.state.shard_proportions = proportions
        self._persist()
        logger.info(
            f"[AUTHORITY] Shards allocated to {len(proportions)} nodes"
        )

    # -----------------------------------------------------------------
    # EPOCH LIFECYCLE
    # -----------------------------------------------------------------

    def start_training(self):
        """Mark training as active."""
        self.state.training_active = True
        self._persist()
        logger.info("[AUTHORITY] Training started")

    def complete_epoch(
        self,
        epoch: int,
        merged_weight_hash: str,
        cluster_sps: float,
        per_node_sps: Dict[str, float],
        baseline_sum: float,
        checkpoint_id: str = "",
    ):
        """Record epoch completion with scaling efficiency.

        Persists all metrics to cluster_state.json.
        """
        efficiency = cluster_sps / max(baseline_sum, 1.0)

        self.state.epoch_number = epoch
        self.state.merged_weight_hash = merged_weight_hash
        self.state.cluster_sps = round(cluster_sps, 2)
        self.state.per_node_sps = per_node_sps
        self.state.scaling_efficiency = round(efficiency, 4)
        self.state.last_checkpoint_id = checkpoint_id

        self._persist()

        status = "HEALTHY"
        if efficiency < 0.7:
            status = "DEGRADED"
            weakest = min(per_node_sps, key=per_node_sps.get) if per_node_sps else "?"
            logger.warning(
                f"[AUTHORITY] Epoch {epoch}: efficiency={efficiency:.2%} "
                f"DEGRADED — weakest={weakest}"
            )
        else:
            logger.info(
                f"[AUTHORITY] Epoch {epoch}: efficiency={efficiency:.2%} — {status}"
            )

    def stop_training(self):
        """Mark training as inactive."""
        self.state.training_active = False
        self._persist()
        logger.info("[AUTHORITY] Training stopped")

    # -----------------------------------------------------------------
    # RESTART & QUORUM
    # -----------------------------------------------------------------

    def validate_quorum(self, rejoining_ids: List[str]) -> dict:
        """Validate that all expected nodes rejoin after restart.

        Returns dict with 'valid', 'missing', 'unexpected', 'resume_epoch'.
        """
        expected = set(self.state.active_nodes.keys())
        rejoining = set(rejoining_ids)

        missing = expected - rejoining
        unexpected = rejoining - expected

        valid = len(missing) == 0

        if missing:
            logger.warning(
                f"[AUTHORITY] Quorum: {len(missing)} missing: "
                f"{[n[:16] for n in missing]}"
            )
        if unexpected:
            logger.info(
                f"[AUTHORITY] Quorum: {len(unexpected)} unexpected new nodes"
            )

        result = {
            'valid': valid,
            'missing': list(missing),
            'unexpected': list(unexpected),
            'resume_epoch': self.state.epoch_number + 1,
            'checkpoint_id': self.state.last_checkpoint_id,
        }

        if valid:
            logger.info("[AUTHORITY] Quorum validated — resume OK")

        return result

    def restart_from_state(self) -> Tuple[bool, str]:
        """Attempt to restart from saved state.

        Returns:
            (success, message)
        """
        if self.state.epoch_number < 0:
            return False, "No previous epoch — fresh training required"

        if not self.state.last_checkpoint_id:
            return False, "No checkpoint saved — cannot resume"

        logger.info(
            f"[AUTHORITY] Restart: resuming from epoch "
            f"{self.state.epoch_number + 1}, "
            f"checkpoint={self.state.last_checkpoint_id}"
        )
        return True, f"Resuming from epoch {self.state.epoch_number + 1}"

    # -----------------------------------------------------------------
    # HEARTBEAT MONITOR
    # -----------------------------------------------------------------

    def start_heartbeat(self):
        """Start background heartbeat monitor."""
        self._stop_event.clear()
        self.abort_requested = False
        self._heartbeat_thread = threading.Thread(
            target=self._heartbeat_loop,
            daemon=True,
            name="authority-heartbeat",
        )
        self._heartbeat_thread.start()
        logger.info("[AUTHORITY] Heartbeat monitor started")

    def stop_heartbeat(self):
        """Stop heartbeat monitor."""
        self._stop_event.set()
        if self._heartbeat_thread:
            self._heartbeat_thread.join(timeout=self.heartbeat_interval * 2)
        logger.info("[AUTHORITY] Heartbeat monitor stopped")

    def _heartbeat_loop(self):
        """Monitor node heartbeats."""
        while not self._stop_event.is_set():
            now = datetime.now()
            timed_out = []

            for nid, info in self.state.active_nodes.items():
                last_hb = info.get('last_heartbeat', '')
                if not last_hb:
                    continue
                try:
                    dt = datetime.fromisoformat(last_hb)
                    elapsed = (now - dt).total_seconds()
                    if elapsed > self.heartbeat_timeout:
                        timed_out.append(nid)
                        info['alive'] = False
                except Exception:
                    pass

            if timed_out:
                alive = sum(
                    1 for v in self.state.active_nodes.values()
                    if v.get('alive', True)
                )
                total = len(self.state.active_nodes)

                logger.warning(
                    f"[HEARTBEAT] {len(timed_out)} node(s) timed out: "
                    f"{[n[:16] for n in timed_out]} — "
                    f"{alive}/{total} alive"
                )

                if alive == 0 or (total > 0 and alive / total < 0.5):
                    self.abort_requested = True
                    self.abort_reason = (
                        f"Quorum lost: {alive}/{total} alive after "
                        f"{len(timed_out)} timeout(s)"
                    )
                    logger.error(f"[HEARTBEAT] ABORT: {self.abort_reason}")
                    self._persist()
                    return

            self._stop_event.wait(self.heartbeat_interval)

    # -----------------------------------------------------------------
    # REPORT
    # -----------------------------------------------------------------

    def get_final_report(self) -> dict:
        """Generate final training report from current state."""
        cuda_nodes = [
            nid for nid, info in self.state.active_nodes.items()
            if info.get('device_type') == 'cuda'
        ]
        mps_nodes = [
            nid for nid, info in self.state.active_nodes.items()
            if info.get('device_type') == 'mps'
        ]

        return {
            'world_size': self.state.world_size,
            'cuda_nodes': len(cuda_nodes),
            'mps_nodes': len(mps_nodes),
            'cluster_sps': self.state.cluster_sps,
            'scaling_efficiency': self.state.scaling_efficiency,
            'merged_weight_hash': self.state.merged_weight_hash,
            'dataset_hash': self.state.dataset_hash,
            'epoch': self.state.epoch_number,
            'training_active': self.state.training_active,
            'per_node_sps': self.state.per_node_sps,
            'timestamp': self.state.timestamp,
        }
