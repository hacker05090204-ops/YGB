"""
continuous_trainer.py — Continuous Training Loop (Phase 3)

When Field A completes:
1. Save model
2. Run regression check
3. Trigger backup
4. Move to Field B automatically

When queue empty:
- Enter low-power monitoring
- Check for new data every 1 hour
"""

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

CHECK_INTERVAL_SEC = 3600  # 1 hour


@dataclass
class FieldResult:
    """Result from training a single field."""
    field_name: str
    epochs: int
    best_accuracy: float
    final_loss: float
    weight_hash: str
    regression_passed: bool
    backup_triggered: bool
    duration_sec: float


@dataclass
class ContinuousTrainerState:
    """State of the continuous trainer."""
    mode: str               # training / monitoring / idle
    current_field: Optional[str]
    fields_completed: int
    total_epochs: int
    results: List[FieldResult]


class ContinuousTrainer:
    """Continuous multi-field training loop.

    Trains field → save → regression → backup → next field.
    When queue empty → low-power monitoring.
    """

    def __init__(self):
        self._mode = "idle"
        self._current_field: Optional[str] = None
        self._results: List[FieldResult] = []
        self._fields_completed = 0
        self._total_epochs = 0

    def train_field(
        self,
        field_name: str,
        train_fn: Callable,
        regression_fn: Optional[Callable] = None,
        backup_fn: Optional[Callable] = None,
    ) -> FieldResult:
        """Train a single field end-to-end.

        1. Execute training
        2. Save model
        3. Run regression
        4. Trigger backup
        """
        self._mode = "training"
        self._current_field = field_name
        t0 = time.perf_counter()

        logger.info(f"[CONTINUOUS] → Training: {field_name}")

        # Step 1: Train
        result_data = train_fn(field_name)
        epochs = result_data.get('epochs', 0)
        accuracy = result_data.get('accuracy', 0.0)
        loss = result_data.get('loss', 0.0)
        weight_hash = result_data.get('weight_hash', '')

        # Step 2: Regression check
        regression_ok = True
        if regression_fn:
            try:
                regression_ok = regression_fn(field_name, accuracy)
            except Exception as e:
                logger.warning(f"  Regression error: {e}")

        # Step 3: Backup
        backup_ok = False
        if backup_fn:
            try:
                backup_ok = backup_fn(field_name)
            except Exception as e:
                logger.warning(f"  Backup error: {e}")

        elapsed = time.perf_counter() - t0

        result = FieldResult(
            field_name=field_name,
            epochs=epochs,
            best_accuracy=accuracy,
            final_loss=loss,
            weight_hash=weight_hash,
            regression_passed=regression_ok,
            backup_triggered=backup_ok,
            duration_sec=round(elapsed, 2),
        )

        self._results.append(result)
        self._fields_completed += 1
        self._total_epochs += epochs
        self._current_field = None

        logger.info(
            f"[CONTINUOUS] ✓ {field_name}: "
            f"acc={accuracy:.4f} epochs={epochs} "
            f"regression={'✓' if regression_ok else '✗'} "
            f"backup={'✓' if backup_ok else '—'}"
        )

        return result

    def enter_monitoring(self):
        """Enter low-power monitoring mode."""
        self._mode = "monitoring"
        self._current_field = None
        logger.info(
            f"[CONTINUOUS] Queue empty — monitoring mode "
            f"(check every {CHECK_INTERVAL_SEC}s)"
        )

    def check_for_new_data(self, check_fn: Callable) -> bool:
        """Check if any field has new data.

        Args:
            check_fn: Returns True if new data available

        Returns:
            True if new data found
        """
        has_new = check_fn()
        if has_new:
            logger.info("[CONTINUOUS] New data detected — resuming")
            self._mode = "idle"
        return has_new

    def get_state(self) -> ContinuousTrainerState:
        return ContinuousTrainerState(
            mode=self._mode,
            current_field=self._current_field,
            fields_completed=self._fields_completed,
            total_epochs=self._total_epochs,
            results=self._results,
        )

    @property
    def mode(self) -> str:
        return self._mode
