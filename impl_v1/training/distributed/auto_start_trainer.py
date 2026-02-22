"""
auto_start_trainer.py — Auto Training Start (Phase 2)

If at least one field has TRAINABLE dataset → start automatically.
If no user interaction for 5 min → auto-run continuous trainer.
No dependency on "new data" flag.
"""

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

IDLE_THRESHOLD_SEC = 300  # 5 minutes


@dataclass
class FieldDataset:
    """A field's dataset state."""
    field_name: str
    sample_count: int
    dataset_hash: str
    status: str         # trainable / locked / error
    priority: int = 50


@dataclass
class AutoStartState:
    """State of the auto-start engine."""
    active: bool
    training_running: bool
    current_field: Optional[str]
    trainable_fields: int
    idle_seconds: float
    auto_triggered: bool
    mode: str           # running / waiting / locked / error


class AutoStartTrainer:
    """Auto-start training when trainable fields available.

    Rules:
    1. If any field has status=TRAINABLE → start
    2. No "new data" flag needed
    3. 5-min idle → auto-continue
    """

    def __init__(self, idle_threshold: float = IDLE_THRESHOLD_SEC):
        self.idle_threshold = idle_threshold
        self._fields: Dict[str, FieldDataset] = {}
        self._training_running = False
        self._current_field: Optional[str] = None
        self._last_interaction: float = time.time()
        self._auto_triggered = False
        self._locked = False

    def register_field(self, dataset: FieldDataset):
        """Register a field dataset."""
        self._fields[dataset.field_name] = dataset
        logger.info(
            f"[AUTO_START] Registered: {dataset.field_name} "
            f"status={dataset.status} samples={dataset.sample_count}"
        )

    def user_interaction(self):
        """Record user interaction (resets idle timer)."""
        self._last_interaction = time.time()

    def check_auto_start(self) -> AutoStartState:
        """Check if training should auto-start.

        Returns state with decision.
        """
        if self._locked:
            return self._state("locked")

        trainable = [
            f for f in self._fields.values()
            if f.status == "trainable"
        ]

        idle_sec = time.time() - self._last_interaction

        if self._training_running:
            return self._state("running")

        if not trainable:
            return self._state("waiting")

        # Auto-start: trainable fields exist
        if len(trainable) > 0:
            # Either immediate or after idle threshold
            if idle_sec >= self.idle_threshold:
                self._auto_triggered = True
                # Pick highest priority
                best = max(trainable, key=lambda f: f.priority)
                self._current_field = best.field_name
                logger.info(
                    f"[AUTO_START] ▶ Auto-starting: {best.field_name} "
                    f"(idle {idle_sec:.0f}s ≥ {self.idle_threshold}s)"
                )
                return self._state("running")
            else:
                return self._state("waiting")

        return self._state("waiting")

    def start_training(self, field_name: str):
        """Mark training as active."""
        self._training_running = True
        self._current_field = field_name

    def stop_training(self):
        """Mark training as complete."""
        self._training_running = False
        self._current_field = None
        self._last_interaction = time.time()

    def lock(self):
        """Lock training (error/abort)."""
        self._locked = True
        self._training_running = False

    def unlock(self):
        """Unlock training."""
        self._locked = False

    @property
    def trainable_count(self) -> int:
        return sum(1 for f in self._fields.values() if f.status == "trainable")

    @property
    def is_running(self) -> bool:
        return self._training_running

    def _state(self, mode: str) -> AutoStartState:
        return AutoStartState(
            active=True,
            training_running=self._training_running,
            current_field=self._current_field,
            trainable_fields=self.trainable_count,
            idle_seconds=time.time() - self._last_interaction,
            auto_triggered=self._auto_triggered,
            mode=mode,
        )
