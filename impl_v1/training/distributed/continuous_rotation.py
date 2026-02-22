"""
continuous_rotation.py — Continuous Field Rotation (Phase 4)

Train field → Freeze → Regression → Backup → Next field.
Repeat until all 23 fields trained.
Loop again for refinement.
"""

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class FieldRotationEntry:
    """A field in the rotation."""
    field_name: str
    rounds_completed: int = 0
    best_accuracy: float = 0.0
    last_trained: str = ""
    frozen: bool = False


@dataclass
class RotationCycleReport:
    """Report for one full rotation cycle."""
    cycle_number: int
    fields_trained: int
    fields_skipped: int
    total_fields: int
    avg_accuracy: float
    duration_sec: float


class ContinuousRotation:
    """Continuously rotate through all fields.

    Cycle: train → freeze → regression → backup → next.
    After all 23 fields, loop for refinement.
    """

    def __init__(self):
        self._fields: List[FieldRotationEntry] = []
        self._current_idx: int = 0
        self._cycle_count: int = 0
        self._results: List[RotationCycleReport] = []

    def register_fields(self, field_names: List[str]):
        """Register all fields for rotation."""
        for name in field_names:
            exists = any(f.field_name == name for f in self._fields)
            if not exists:
                self._fields.append(FieldRotationEntry(field_name=name))
        logger.info(
            f"[ROTATION] Registered {len(self._fields)} fields"
        )

    def next_field(self) -> Optional[FieldRotationEntry]:
        """Get next field in rotation."""
        if not self._fields:
            return None

        entry = self._fields[self._current_idx % len(self._fields)]
        self._current_idx += 1

        # Check if new cycle
        if self._current_idx % len(self._fields) == 0:
            self._cycle_count += 1

        return entry

    def complete_field(
        self,
        field_name: str,
        accuracy: float,
        frozen: bool = True,
    ):
        """Mark field as complete for this round."""
        for f in self._fields:
            if f.field_name == field_name:
                f.rounds_completed += 1
                f.best_accuracy = max(f.best_accuracy, accuracy)
                f.last_trained = datetime.now().isoformat()
                f.frozen = frozen
                break

        logger.info(
            f"[ROTATION] ✓ {field_name}: "
            f"acc={accuracy:.4f} round={self._get_rounds(field_name)}"
        )

    def run_cycle(
        self,
        train_fn: Callable,
        regression_fn: Optional[Callable] = None,
        backup_fn: Optional[Callable] = None,
    ) -> RotationCycleReport:
        """Run one full rotation cycle through all fields."""
        t0 = time.perf_counter()
        trained = 0
        skipped = 0
        accuracies = []

        for _ in range(len(self._fields)):
            entry = self.next_field()
            if entry is None:
                break

            try:
                result = train_fn(entry.field_name)
                acc = result.get('accuracy', 0.0)
                accuracies.append(acc)

                # Regression check
                reg_ok = True
                if regression_fn:
                    try:
                        reg_ok = regression_fn(entry.field_name, acc)
                    except Exception:
                        pass

                # Backup
                if backup_fn:
                    try:
                        backup_fn(entry.field_name)
                    except Exception:
                        pass

                self.complete_field(entry.field_name, acc, frozen=reg_ok)
                trained += 1

            except Exception as e:
                logger.warning(
                    f"[ROTATION] Skip {entry.field_name}: {e}"
                )
                skipped += 1

        elapsed = time.perf_counter() - t0
        avg_acc = sum(accuracies) / max(len(accuracies), 1)

        report = RotationCycleReport(
            cycle_number=self._cycle_count,
            fields_trained=trained,
            fields_skipped=skipped,
            total_fields=len(self._fields),
            avg_accuracy=round(avg_acc, 4),
            duration_sec=round(elapsed, 2),
        )

        self._results.append(report)
        logger.info(
            f"[ROTATION] Cycle {self._cycle_count}: "
            f"{trained}/{len(self._fields)} trained, "
            f"avg_acc={avg_acc:.4f}"
        )

        return report

    def _get_rounds(self, field_name: str) -> int:
        for f in self._fields:
            if f.field_name == field_name:
                return f.rounds_completed
        return 0

    @property
    def cycle_count(self) -> int:
        return self._cycle_count

    @property
    def total_fields(self) -> int:
        return len(self._fields)
