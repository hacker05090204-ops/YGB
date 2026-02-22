"""
stability_tracker.py — Long Term Stability (Phase 5)

Require 5 consecutive stable cycles before declaring LIVE_READY.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

LIVE_READY_THRESHOLD = 5


@dataclass
class StabilityCycle:
    """A single stability cycle."""
    cycle_number: int
    field_name: str
    accuracy: float
    stable: bool
    timestamp: str


@dataclass
class FieldStability:
    """Stability tracking for a field."""
    field_name: str
    consecutive_stable: int = 0
    total_cycles: int = 0
    live_ready: bool = False
    best_accuracy: float = 0.0
    cycles: List[StabilityCycle] = field(default_factory=list)


class StabilityTracker:
    """Tracks long-term stability per field.

    5 consecutive stable cycles → LIVE_READY.
    """

    def __init__(self, threshold: int = LIVE_READY_THRESHOLD):
        self.threshold = threshold
        self._fields: Dict[str, FieldStability] = {}

    def record_cycle(
        self,
        field_name: str,
        accuracy: float,
        stable: bool,
    ) -> FieldStability:
        """Record a training cycle result.

        Args:
            field_name: Field trained
            accuracy: Validation accuracy
            stable: Whether cycle was stable (no crashes, no drift)
        """
        if field_name not in self._fields:
            self._fields[field_name] = FieldStability(field_name=field_name)

        fs = self._fields[field_name]
        fs.total_cycles += 1

        cycle = StabilityCycle(
            cycle_number=fs.total_cycles,
            field_name=field_name,
            accuracy=accuracy,
            stable=stable,
            timestamp=datetime.now().isoformat(),
        )
        fs.cycles.append(cycle)

        if stable:
            fs.consecutive_stable += 1
            fs.best_accuracy = max(fs.best_accuracy, accuracy)
        else:
            fs.consecutive_stable = 0

        # Check LIVE_READY
        was_ready = fs.live_ready
        fs.live_ready = fs.consecutive_stable >= self.threshold

        if fs.live_ready and not was_ready:
            logger.info(
                f"[STABILITY] ★ {field_name} → LIVE_READY "
                f"({fs.consecutive_stable} stable cycles, "
                f"best={fs.best_accuracy:.4f})"
            )
        elif stable:
            logger.info(
                f"[STABILITY] ✓ {field_name}: "
                f"stable {fs.consecutive_stable}/{self.threshold}"
            )
        else:
            logger.warning(
                f"[STABILITY] ✗ {field_name}: unstable — reset to 0"
            )

        return fs

    def is_live_ready(self, field_name: str) -> bool:
        if field_name in self._fields:
            return self._fields[field_name].live_ready
        return False

    def live_ready_count(self) -> int:
        return sum(1 for f in self._fields.values() if f.live_ready)

    def get_field(self, field_name: str) -> Optional[FieldStability]:
        return self._fields.get(field_name)

    def get_all_status(self) -> Dict[str, bool]:
        return {name: f.live_ready for name, f in self._fields.items()}
