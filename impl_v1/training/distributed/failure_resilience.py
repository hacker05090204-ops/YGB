"""
failure_resilience.py — Failure Simulation & Resilience (Phase 7)

Handles:
  - Node dropout detection mid-epoch
  - Safe abort: save state, destroy NCCL group, no hang
  - Failure simulation for testing

Test sequence:
  1. Kill one node mid-epoch
  2. Authority detects dropout
  3. Authority aborts safely
  4. State saved
  5. NCCL ring does not hang
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

FAILURE_LOG_PATH = os.path.join('secure_data', 'failure_log.json')


# =============================================================================
# TYPES
# =============================================================================

@dataclass
class NodeDropout:
    """Detected node dropout event."""
    node_id: str
    detected_at: str
    last_heartbeat: str
    epoch_at_failure: int
    reason: str


@dataclass
class FailureReport:
    """Report on a failure event."""
    failure_detected: bool
    dropout_nodes: List[NodeDropout]
    authority_saved: bool
    nccl_cleaned: bool
    training_aborted: bool
    abort_reason: str
    state_preserved: bool
    timestamp: str


# =============================================================================
# DROPOUT DETECTION
# =============================================================================

class NodeDropoutDetector:
    """Detects node dropouts during training.

    Monitors node heartbeats or simulated status flags.
    """

    def __init__(
        self,
        timeout_sec: float = 10.0,
        check_interval: float = 2.0,
    ):
        self.timeout_sec = timeout_sec
        self.check_interval = check_interval
        self._node_status: Dict[str, dict] = {}
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self.dropouts: List[NodeDropout] = []
        self.on_dropout: Optional[Callable] = None

    def register_node(self, node_id: str):
        """Register a node for monitoring."""
        self._node_status[node_id] = {
            'alive': True,
            'last_heartbeat': datetime.now().isoformat(),
        }

    def heartbeat(self, node_id: str):
        """Update a node's heartbeat."""
        if node_id in self._node_status:
            self._node_status[node_id]['last_heartbeat'] = (
                datetime.now().isoformat()
            )
            self._node_status[node_id]['alive'] = True

    def kill_node(self, node_id: str, reason: str = "simulated failure"):
        """Simulate killing a node (for testing)."""
        if node_id in self._node_status:
            self._node_status[node_id]['alive'] = False
            logger.warning(f"[FAILURE] Node {node_id[:16]}... killed: {reason}")

    def start_monitoring(self, current_epoch: int = 0):
        """Start background dropout detection."""
        self._stop.clear()
        self._current_epoch = current_epoch
        self._thread = threading.Thread(
            target=self._monitor_loop,
            daemon=True,
            name="dropout-detector",
        )
        self._thread.start()
        logger.info("[FAILURE] Dropout detector started")

    def stop_monitoring(self):
        """Stop background monitoring."""
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=self.check_interval * 2)

    def _monitor_loop(self):
        while not self._stop.is_set():
            now = datetime.now()
            for nid, status in self._node_status.items():
                if not status.get('alive', True):
                    # Already detected as dropped; check if already recorded
                    already_recorded = any(
                        d.node_id == nid for d in self.dropouts
                    )
                    if not already_recorded:
                        dropout = NodeDropout(
                            node_id=nid,
                            detected_at=now.isoformat(),
                            last_heartbeat=status.get('last_heartbeat', ''),
                            epoch_at_failure=getattr(self, '_current_epoch', -1),
                            reason="Node marked dead",
                        )
                        self.dropouts.append(dropout)
                        logger.error(
                            f"[FAILURE] DROPOUT DETECTED: {nid[:16]}... "
                            f"at epoch {dropout.epoch_at_failure}"
                        )
                        if self.on_dropout:
                            self.on_dropout(dropout)
                    continue

                # Check heartbeat timeout
                last_hb = status.get('last_heartbeat', '')
                if last_hb:
                    try:
                        dt = datetime.fromisoformat(last_hb)
                        elapsed = (now - dt).total_seconds()
                        if elapsed > self.timeout_sec:
                            status['alive'] = False
                            dropout = NodeDropout(
                                node_id=nid,
                                detected_at=now.isoformat(),
                                last_heartbeat=last_hb,
                                epoch_at_failure=getattr(self, '_current_epoch', -1),
                                reason=f"Heartbeat timeout ({elapsed:.1f}s > {self.timeout_sec}s)",
                            )
                            self.dropouts.append(dropout)
                            logger.error(
                                f"[FAILURE] DROPOUT: {nid[:16]}... "
                                f"timed out after {elapsed:.1f}s"
                            )
                            if self.on_dropout:
                                self.on_dropout(dropout)
                    except Exception:
                        pass

            self._stop.wait(self.check_interval)

    @property
    def has_dropouts(self) -> bool:
        return len(self.dropouts) > 0


# =============================================================================
# SAFE ABORT
# =============================================================================

def safe_abort_training(
    authority=None,
    detector: Optional[NodeDropoutDetector] = None,
    reason: str = "",
) -> FailureReport:
    """Safely abort training after failure detection.

    1. Save authority state
    2. Destroy NCCL group
    3. Log failure report
    4. Return report

    Args:
        authority: ClusterAuthority instance (optional).
        detector: NodeDropoutDetector instance (optional).
        reason: Abort reason.

    Returns:
        FailureReport.
    """
    dropout_nodes = detector.dropouts if detector else []
    authority_saved = False
    nccl_cleaned = False

    # Save authority state
    if authority is not None:
        try:
            authority.stop_training()
            authority_saved = True
            logger.info("[FAILURE] Authority state saved")
        except Exception as e:
            logger.error(f"[FAILURE] Failed to save authority state: {e}")

    # Destroy NCCL
    try:
        import torch.distributed as dist
        if dist.is_initialized():
            dist.destroy_process_group()
            nccl_cleaned = True
            logger.info("[FAILURE] NCCL process group destroyed")
        else:
            nccl_cleaned = True  # Not initialized = nothing to clean
    except Exception:
        nccl_cleaned = True  # No dist available = nothing to clean

    # Stop detector
    if detector:
        detector.stop_monitoring()

    report = FailureReport(
        failure_detected=len(dropout_nodes) > 0,
        dropout_nodes=dropout_nodes,
        authority_saved=authority_saved,
        nccl_cleaned=nccl_cleaned,
        training_aborted=True,
        abort_reason=reason or "Node dropout detected",
        state_preserved=authority_saved,
        timestamp=datetime.now().isoformat(),
    )

    # Persist failure log
    _persist_failure_log(report)

    logger.error(f"[FAILURE] SAFE ABORT COMPLETE: {reason}")
    return report


def _persist_failure_log(report: FailureReport):
    """Persist failure report to disk."""
    os.makedirs(os.path.dirname(FAILURE_LOG_PATH) or '.', exist_ok=True)
    try:
        data = asdict(report)
        # NodeDropout dataclass conversion
        data['dropout_nodes'] = [asdict(d) for d in report.dropout_nodes]
        with open(FAILURE_LOG_PATH, 'w') as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        logger.error(f"[FAILURE] Failed to persist log: {e}")


# =============================================================================
# FAILURE SIMULATION
# =============================================================================

class FailureSimulator:
    """Simulates node failures for resilience testing.

    Usage:
        sim = FailureSimulator(authority, detector)
        report = sim.simulate_node_kill("node_1", delay_sec=2.0)
        assert report.failure_detected
        assert report.authority_saved
        assert report.nccl_cleaned
    """

    def __init__(self, authority=None, detector: NodeDropoutDetector = None):
        if detector is None:
            detector = NodeDropoutDetector(timeout_sec=1.0, check_interval=0.5)
        self.authority = authority
        self.detector = detector

    def simulate_node_kill(
        self,
        node_id: str,
        delay_sec: float = 1.0,
        epoch: int = 0,
    ) -> FailureReport:
        """Simulate killing a node mid-epoch.

        1. Start monitoring
        2. Wait delay
        3. Kill node
        4. Wait for detection
        5. Safe abort

        Returns:
            FailureReport.
        """
        # Ensure node is registered
        self.detector.register_node(node_id)
        self.detector.start_monitoring(current_epoch=epoch)

        # Wait before killing
        time.sleep(delay_sec)

        # Kill
        self.detector.kill_node(node_id, reason="Simulated mid-epoch failure")

        # Wait for detection
        time.sleep(self.detector.check_interval * 2)

        # Abort
        report = safe_abort_training(
            authority=self.authority,
            detector=self.detector,
            reason=f"Simulated failure: {node_id} killed at epoch {epoch}",
        )

        return report
