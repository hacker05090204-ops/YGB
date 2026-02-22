"""
early_convergence.py — Early Convergence Optimization (Phase 6)

If validation plateaus:
- Stop early
- Move to next field
- Log convergence speed
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional

logger = logging.getLogger(__name__)

DEFAULT_PATIENCE = 5
DEFAULT_MIN_DELTA = 0.001


@dataclass
class ConvergenceEvent:
    """Record of a convergence detection."""
    field_name: str
    stopped_at_epoch: int
    best_epoch: int
    best_metric: float
    convergence_speed: float  # epochs to best
    reason: str


class EarlyConvergenceDetector:
    """Detects validation plateau and triggers early stop.

    Monitors validation metric (accuracy or loss). If no improvement
    for `patience` epochs, stop training and move to next field.
    """

    def __init__(
        self,
        patience: int = DEFAULT_PATIENCE,
        min_delta: float = DEFAULT_MIN_DELTA,
        mode: str = "max",   # max (accuracy) or min (loss)
    ):
        self.patience = patience
        self.min_delta = min_delta
        self.mode = mode
        self._best: Optional[float] = None
        self._best_epoch: int = 0
        self._wait: int = 0
        self._history: List[float] = []
        self._should_stop = False

    def check(self, epoch: int, metric: float) -> bool:
        """Check if training should stop.

        Args:
            epoch: Current epoch
            metric: Validation metric (accuracy or loss)

        Returns:
            True if should stop early
        """
        self._history.append(metric)

        if self._best is None:
            self._best = metric
            self._best_epoch = epoch
            return False

        improved = False
        if self.mode == "max":
            improved = metric > (self._best + self.min_delta)
        else:
            improved = metric < (self._best - self.min_delta)

        if improved:
            self._best = metric
            self._best_epoch = epoch
            self._wait = 0
        else:
            self._wait += 1

        if self._wait >= self.patience:
            self._should_stop = True
            logger.info(
                f"[CONVERGENCE] Plateau: no improvement for "
                f"{self.patience} epochs. Best={self._best:.4f} "
                f"at epoch {self._best_epoch}"
            )
            return True

        return False

    def get_event(self, field_name: str, current_epoch: int) -> ConvergenceEvent:
        """Get convergence event details."""
        speed = self._best_epoch + 1 if self._best_epoch >= 0 else current_epoch
        return ConvergenceEvent(
            field_name=field_name,
            stopped_at_epoch=current_epoch,
            best_epoch=self._best_epoch,
            best_metric=self._best or 0.0,
            convergence_speed=speed,
            reason=(
                f"Plateau after {self._wait} epochs. "
                f"Best={self._best:.4f} at epoch {self._best_epoch}"
            ),
        )

    def reset(self):
        """Reset for next field."""
        self._best = None
        self._best_epoch = 0
        self._wait = 0
        self._history.clear()
        self._should_stop = False

    @property
    def should_stop(self) -> bool:
        return self._should_stop

    @property
    def best_metric(self) -> Optional[float]:
        return self._best
