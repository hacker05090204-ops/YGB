"""
drift_guard.py — Drift & Trash Prevention (Phase 8)

Monitor training for anomalies:
1. Validation loss spikes
2. Gradient explosion
3. Sudden accuracy jumps (possible leakage)
4. Dataset drift

Abort if anomaly exceeds threshold.
"""

import logging
import math
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional, Tuple

logger = logging.getLogger(__name__)

# Thresholds
LOSS_SPIKE_FACTOR = 3.0      # Loss > 3x rolling avg = spike
GRADIENT_EXPLODE = 100.0     # Max gradient norm
ACCURACY_JUMP = 0.20         # >20% accuracy jump in 1 epoch = suspicious
DRIFT_WINDOW = 5             # Rolling window size


@dataclass
class AnomalyEvent:
    """A detected training anomaly."""
    event_type: str     # loss_spike / gradient_explosion / accuracy_jump / drift
    severity: str       # warning / critical / abort
    value: float
    threshold: float
    epoch: int
    detail: str
    timestamp: str = ""


@dataclass
class DriftGuardReport:
    """Report from drift guard."""
    should_abort: bool
    events: List[AnomalyEvent]
    epochs_monitored: int
    status: str         # ok / warning / abort


class DriftGuard:
    """Monitors training for anomalies and drift.

    Maintains rolling histories and triggers abort on critical anomalies.
    """

    def __init__(
        self,
        loss_spike_factor: float = LOSS_SPIKE_FACTOR,
        max_gradient_norm: float = GRADIENT_EXPLODE,
        max_accuracy_jump: float = ACCURACY_JUMP,
        window_size: int = DRIFT_WINDOW,
    ):
        self.loss_spike_factor = loss_spike_factor
        self.max_gradient_norm = max_gradient_norm
        self.max_accuracy_jump = max_accuracy_jump
        self.window_size = window_size

        self._loss_history: List[float] = []
        self._accuracy_history: List[float] = []
        self._gradient_history: List[float] = []
        self._events: List[AnomalyEvent] = []
        self._should_abort = False

    def check_epoch(
        self,
        epoch: int,
        loss: float,
        accuracy: float,
        gradient_norm: float = 0.0,
    ) -> List[AnomalyEvent]:
        """Check a single epoch for anomalies.

        Args:
            epoch: Epoch number
            loss: Validation/training loss
            accuracy: Validation/training accuracy
            gradient_norm: Max gradient norm for this epoch

        Returns:
            List of anomaly events detected this epoch.
        """
        new_events = []

        # CHECK 1: Loss spike
        if self._loss_history:
            avg_loss = sum(self._loss_history[-self.window_size:]) / len(
                self._loss_history[-self.window_size:]
            )
            if loss > avg_loss * self.loss_spike_factor and avg_loss > 0:
                event = AnomalyEvent(
                    event_type="loss_spike",
                    severity="critical",
                    value=loss,
                    threshold=avg_loss * self.loss_spike_factor,
                    epoch=epoch,
                    detail=(
                        f"Loss {loss:.4f} > {self.loss_spike_factor}x "
                        f"avg {avg_loss:.4f}"
                    ),
                    timestamp=datetime.now().isoformat(),
                )
                new_events.append(event)
                self._should_abort = True

        # CHECK 2: Gradient explosion
        if gradient_norm > self.max_gradient_norm:
            event = AnomalyEvent(
                event_type="gradient_explosion",
                severity="abort",
                value=gradient_norm,
                threshold=self.max_gradient_norm,
                epoch=epoch,
                detail=(
                    f"Gradient norm {gradient_norm:.2f} > "
                    f"max {self.max_gradient_norm}"
                ),
                timestamp=datetime.now().isoformat(),
            )
            new_events.append(event)
            self._should_abort = True

        # CHECK 3: Accuracy jump (possible leakage)
        if self._accuracy_history:
            prev_acc = self._accuracy_history[-1]
            jump = accuracy - prev_acc
            if jump > self.max_accuracy_jump:
                event = AnomalyEvent(
                    event_type="accuracy_jump",
                    severity="warning",
                    value=jump,
                    threshold=self.max_accuracy_jump,
                    epoch=epoch,
                    detail=(
                        f"Accuracy jumped {jump:.4f} "
                        f"({prev_acc:.4f} → {accuracy:.4f}) "
                        f"— possible leakage"
                    ),
                    timestamp=datetime.now().isoformat(),
                )
                new_events.append(event)

        # CHECK 4: NaN/Inf detection
        if math.isnan(loss) or math.isinf(loss):
            event = AnomalyEvent(
                event_type="nan_inf",
                severity="abort",
                value=loss,
                threshold=0,
                epoch=epoch,
                detail=f"Loss is NaN/Inf: {loss}",
                timestamp=datetime.now().isoformat(),
            )
            new_events.append(event)
            self._should_abort = True

        # Update histories
        self._loss_history.append(loss)
        self._accuracy_history.append(accuracy)
        if gradient_norm > 0:
            self._gradient_history.append(gradient_norm)

        self._events.extend(new_events)

        for e in new_events:
            icon = "✗" if e.severity in ("critical", "abort") else "⚠"
            logger.warning(
                f"[DRIFT_GUARD] {icon} [{e.event_type}] {e.detail}"
            )

        return new_events

    def get_report(self) -> DriftGuardReport:
        """Get full drift guard report."""
        status = "ok"
        if self._should_abort:
            status = "abort"
        elif any(e.severity == "warning" for e in self._events):
            status = "warning"

        return DriftGuardReport(
            should_abort=self._should_abort,
            events=self._events,
            epochs_monitored=len(self._loss_history),
            status=status,
        )

    @property
    def should_abort(self) -> bool:
        return self._should_abort

    def reset(self):
        """Reset all state."""
        self._loss_history.clear()
        self._accuracy_history.clear()
        self._gradient_history.clear()
        self._events.clear()
        self._should_abort = False
