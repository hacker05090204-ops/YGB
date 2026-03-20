from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from impl_v1.training.distributed.advanced_checkpointing import (
    AsyncDistributedCheckpointManager,
    LoadedCheckpoint,
)
from impl_v1.training.distributed.failure_resilience import (
    NodeDropoutDetector,
    safe_abort_training,
)

logger = logging.getLogger(__name__)


@dataclass
class ResumeDecision:
    checkpoint: Optional[LoadedCheckpoint]
    source: str
    corrupted: List[Dict[str, str]] = field(default_factory=list)


class FaultTolerantResumeManager:
    def __init__(self, checkpoint_manager: AsyncDistributedCheckpointManager):
        self.checkpoint_manager = checkpoint_manager

    def recover(self, rank: int = 0) -> ResumeDecision:
        corrupted: List[Dict[str, str]] = []
        checkpoint = self.checkpoint_manager.load_latest_valid(rank=rank)
        if checkpoint is not None:
            return ResumeDecision(checkpoint=checkpoint, source="latest_valid", corrupted=corrupted)
        return ResumeDecision(checkpoint=None, source="none", corrupted=corrupted)


class ClusterFaultMonitor:
    def __init__(self, timeout_sec: float = 15.0, check_interval: float = 3.0):
        self.detector = NodeDropoutDetector(timeout_sec=timeout_sec, check_interval=check_interval)
        self.last_report: Optional[Dict[str, Any]] = None

    def register_nodes(self, node_ids: List[str]) -> None:
        for node_id in node_ids:
            self.detector.register_node(node_id)

    def start(self, current_epoch: int = 0) -> None:
        self.detector.start_monitoring(current_epoch=current_epoch)

    def heartbeat(self, node_id: str) -> None:
        self.detector.heartbeat(node_id)

    def stop(self) -> None:
        self.detector.stop_monitoring()

    def abort_if_needed(self, authority: Any = None, reason: str = "node failure detected") -> Optional[Dict[str, Any]]:
        if not self.detector.has_dropouts:
            return None
        report = safe_abort_training(authority=authority, detector=self.detector, reason=reason)
        self.last_report = {
            "failure_detected": report.failure_detected,
            "dropouts": [drop.node_id for drop in report.dropout_nodes],
            "abort_reason": report.abort_reason,
            "timestamp": report.timestamp,
        }
        logger.error("[FAULT] abort report: %s", self.last_report)
        return self.last_report
