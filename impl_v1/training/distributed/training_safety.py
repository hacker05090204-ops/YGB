"""
training_safety.py — Safety Guards (Phase 8)

Abort only if:
- Dataset corruption
- Determinism mismatch
- Regression failure
- Repeated crash (3+)

Auto-heal allowed only for:
- Crash resume
- Shard repair
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

MAX_CRASH_RETRIES = 3


@dataclass
class SafetyEvent:
    """A safety event."""
    event_type: str     # crash / dataset / determinism / regression / shard
    severity: str       # warning / abort / healed
    detail: str
    action_taken: str   # resume / repair / abort / none
    timestamp: str = ""


@dataclass
class SafetyReport:
    """Safety status report."""
    training_safe: bool
    crash_count: int
    events: List[SafetyEvent]
    abort_reason: Optional[str]


class TrainingSafetyGuard:
    """Unified safety guard for continuous training.

    Hard aborts:
    - Dataset corruption
    - Determinism mismatch
    - Regression failure
    - 3+ consecutive crashes

    Soft heals:
    - Single crash → checkpoint resume
    - Shard corruption → peer repair
    """

    def __init__(self, max_crashes: int = MAX_CRASH_RETRIES):
        self.max_crashes = max_crashes
        self._crash_count = 0
        self._events: List[SafetyEvent] = []
        self._aborted = False
        self._abort_reason: Optional[str] = None

    def report_crash(self) -> SafetyEvent:
        """Report a training crash."""
        self._crash_count += 1

        if self._crash_count >= self.max_crashes:
            event = SafetyEvent(
                event_type="crash",
                severity="abort",
                detail=f"Crash #{self._crash_count} — max {self.max_crashes} exceeded",
                action_taken="abort",
                timestamp=datetime.now().isoformat(),
            )
            self._aborted = True
            self._abort_reason = f"Repeated crash ({self._crash_count}x)"
            logger.error(f"[SAFETY] ✗ ABORT: {event.detail}")
        else:
            event = SafetyEvent(
                event_type="crash",
                severity="healed",
                detail=f"Crash #{self._crash_count}/{self.max_crashes} — resuming",
                action_taken="resume",
                timestamp=datetime.now().isoformat(),
            )
            logger.warning(f"[SAFETY] ⚠ {event.detail}")

        self._events.append(event)
        return event

    def report_dataset_corruption(self, detail: str = "") -> SafetyEvent:
        """Report dataset corruption — always abort."""
        event = SafetyEvent(
            event_type="dataset",
            severity="abort",
            detail=detail or "Dataset corruption detected",
            action_taken="abort",
            timestamp=datetime.now().isoformat(),
        )
        self._aborted = True
        self._abort_reason = "Dataset corruption"
        self._events.append(event)
        logger.error(f"[SAFETY] ✗ ABORT: {event.detail}")
        return event

    def report_determinism_failure(self, detail: str = "") -> SafetyEvent:
        """Report determinism mismatch — always abort."""
        event = SafetyEvent(
            event_type="determinism",
            severity="abort",
            detail=detail or "Determinism mismatch",
            action_taken="abort",
            timestamp=datetime.now().isoformat(),
        )
        self._aborted = True
        self._abort_reason = "Determinism mismatch"
        self._events.append(event)
        logger.error(f"[SAFETY] ✗ ABORT: {event.detail}")
        return event

    def report_regression_failure(self, detail: str = "") -> SafetyEvent:
        """Report regression failure — always abort."""
        event = SafetyEvent(
            event_type="regression",
            severity="abort",
            detail=detail or "Model regression detected",
            action_taken="abort",
            timestamp=datetime.now().isoformat(),
        )
        self._aborted = True
        self._abort_reason = "Regression failure"
        self._events.append(event)
        logger.error(f"[SAFETY] ✗ ABORT: {event.detail}")
        return event

    def report_shard_repair(self, shard_id: str) -> SafetyEvent:
        """Report shard repair — auto-heal allowed."""
        event = SafetyEvent(
            event_type="shard",
            severity="healed",
            detail=f"Shard {shard_id[:16]}... repaired from peer",
            action_taken="repair",
            timestamp=datetime.now().isoformat(),
        )
        self._events.append(event)
        logger.info(f"[SAFETY] ✓ {event.detail}")
        return event

    def reset_crash_counter(self):
        """Reset crash counter after successful epoch."""
        self._crash_count = 0

    def get_report(self) -> SafetyReport:
        return SafetyReport(
            training_safe=not self._aborted,
            crash_count=self._crash_count,
            events=self._events,
            abort_reason=self._abort_reason,
        )

    @property
    def is_safe(self) -> bool:
        return not self._aborted

    @property
    def crash_count(self) -> int:
        return self._crash_count
