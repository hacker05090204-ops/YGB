"""
sequential_field_master.py — Sequential Field Mastering (Phase 7)

Rules:
- Only one active field at a time
- Next field locked until previous achieves FIELD_MASTERED
- FIELD_MASTERED requires:
    ≥95% accuracy
    <1% FPR
    <0.5% hallucination
    5 stable cycles
    Verified exploit robustness
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


@dataclass
class FieldMasteryState:
    """State of a single field."""
    field_name: str
    status: str          # QUEUED / ACTIVE / MASTERED / FAILED
    accuracy: float = 0.0
    fpr: float = 1.0
    hallucination: float = 1.0
    stable_cycles: int = 0
    exploit_verified: bool = False
    mastered_at: str = ""


MASTERY_THRESHOLDS = {
    "accuracy": 0.95,
    "fpr": 0.01,
    "hallucination": 0.005,
    "stable_cycles": 5,
    "exploit_verified": True,
}


class SequentialFieldMaster:
    """Manages sequential field mastering.

    Only one field trains at a time.
    Must master before moving to next.
    """

    def __init__(self, field_order: Optional[List[str]] = None):
        self._fields: Dict[str, FieldMasteryState] = {}
        self._order: List[str] = field_order or []
        self._active: Optional[str] = None
        self._mastered: List[str] = []

        # Initialize queue
        for f in self._order:
            self._fields[f] = FieldMasteryState(f, "QUEUED")

        if self._order:
            self._active = self._order[0]
            self._fields[self._active].status = "ACTIVE"

    def get_active_field(self) -> Optional[str]:
        """Get currently active field."""
        return self._active

    def update_metrics(
        self,
        field_name: str,
        accuracy: float,
        fpr: float,
        hallucination: float,
        stable_cycles: int,
        exploit_verified: bool,
    ) -> FieldMasteryState:
        """Update field metrics and check mastery."""
        if field_name not in self._fields:
            self._fields[field_name] = FieldMasteryState(field_name, "ACTIVE")

        state = self._fields[field_name]
        state.accuracy = accuracy
        state.fpr = fpr
        state.hallucination = hallucination
        state.stable_cycles = stable_cycles
        state.exploit_verified = exploit_verified

        # Check mastery
        if self._check_mastery(state):
            state.status = "MASTERED"
            state.mastered_at = datetime.now().isoformat()
            if field_name not in self._mastered:
                self._mastered.append(field_name)
            logger.info(f"[FIELD_MASTER] ★ {field_name}: FIELD_MASTERED")

            # Advance to next field
            self._advance_to_next()

        return state

    def _check_mastery(self, state: FieldMasteryState) -> bool:
        """Check if field meets mastery thresholds."""
        return (
            state.accuracy >= MASTERY_THRESHOLDS["accuracy"]
            and state.fpr <= MASTERY_THRESHOLDS["fpr"]
            and state.hallucination <= MASTERY_THRESHOLDS["hallucination"]
            and state.stable_cycles >= MASTERY_THRESHOLDS["stable_cycles"]
            and state.exploit_verified
        )

    def _advance_to_next(self):
        """Advance to next unmastered field."""
        for f in self._order:
            if f not in self._mastered:
                self._active = f
                self._fields[f].status = "ACTIVE"
                logger.info(f"[FIELD_MASTER] → Next field: {f}")
                return
        self._active = None
        logger.info("[FIELD_MASTER] ★ ALL FIELDS MASTERED")

    def is_mastered(self, field_name: str) -> bool:
        """Check if a field is mastered."""
        return field_name in self._mastered

    def get_mastery_report(self) -> Dict:
        """Get full mastery report."""
        return {
            "active_field": self._active,
            "mastered": list(self._mastered),
            "queued": [f for f in self._order if f not in self._mastered and f != self._active],
            "total_fields": len(self._order),
            "mastered_count": len(self._mastered),
            "all_mastered": self._active is None and len(self._mastered) == len(self._order),
        }

    @property
    def mastered_count(self) -> int:
        return len(self._mastered)
