"""
decay_detector.py — Decay Detection Window (Phase 4)

Rolling 7-cycle window.
If mean accuracy stable BUT precision drops > 3%:
Trigger auto-retrain with harder negatives.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional

logger = logging.getLogger(__name__)

WINDOW_SIZE = 7
PRECISION_DROP_THRESHOLD = 0.03


@dataclass
class CycleMetric:
    """Metrics for one training cycle."""
    cycle: int
    accuracy: float
    precision: float
    recall: float
    timestamp: str


@dataclass
class DecayReport:
    """Decay detection report."""
    decay_detected: bool
    retrain_needed: bool
    accuracy_trend: float   # mean over window
    precision_drop: float
    threshold: float
    window_size: int
    reason: str
    timestamp: str = ""


class DecayDetector:
    """Detects silent performance decay.

    Watches precision over 7-cycle rolling window.
    Triggers retrain if precision drops > 3% while accuracy stable.
    """

    def __init__(
        self,
        window_size: int = WINDOW_SIZE,
        precision_drop: float = PRECISION_DROP_THRESHOLD,
    ):
        self.window_size = window_size
        self.precision_drop_max = precision_drop
        self._history: List[CycleMetric] = []
        self._cycle: int = 0

    def record(
        self,
        accuracy: float,
        precision: float,
        recall: float = 0.0,
    ) -> DecayReport:
        """Record a cycle and check for decay."""
        self._cycle += 1
        self._history.append(CycleMetric(
            cycle=self._cycle,
            accuracy=accuracy,
            precision=precision,
            recall=recall,
            timestamp=datetime.now().isoformat(),
        ))

        # Keep window
        if len(self._history) > self.window_size * 2:
            self._history = self._history[-self.window_size * 2:]

        if len(self._history) < self.window_size:
            return DecayReport(
                decay_detected=False, retrain_needed=False,
                accuracy_trend=accuracy, precision_drop=0.0,
                threshold=self.precision_drop_max,
                window_size=len(self._history),
                reason="Insufficient data",
                timestamp=datetime.now().isoformat(),
            )

        window = self._history[-self.window_size:]
        mean_acc = sum(c.accuracy for c in window) / len(window)

        # Precision trend: compare first half to second half
        half = len(window) // 2
        first_prec = sum(c.precision for c in window[:half]) / max(half, 1)
        second_prec = sum(c.precision for c in window[half:]) / max(len(window) - half, 1)
        prec_drop = max(0, first_prec - second_prec)

        # Accuracy stable? (within 2%)
        acc_std = (
            sum((c.accuracy - mean_acc) ** 2 for c in window) / len(window)
        ) ** 0.5
        acc_stable = acc_std < 0.02

        decay = acc_stable and prec_drop > self.precision_drop_max
        retrain = decay

        report = DecayReport(
            decay_detected=decay,
            retrain_needed=retrain,
            accuracy_trend=round(mean_acc, 4),
            precision_drop=round(prec_drop, 4),
            threshold=self.precision_drop_max,
            window_size=len(window),
            reason=(
                f"DECAY: precision dropped {prec_drop:.4f} > {self.precision_drop_max}" if decay
                else "Stable"
            ),
            timestamp=datetime.now().isoformat(),
        )

        if decay:
            logger.warning(
                f"[DECAY] ⚠ Precision decay: drop={prec_drop:.4f} "
                f"while acc stable at {mean_acc:.4f}"
            )
        else:
            logger.info(f"[DECAY] ✓ Stable: acc={mean_acc:.4f}")

        return report

    @property
    def cycle_count(self) -> int:
        return self._cycle
