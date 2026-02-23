"""
reinforcement_scheduler.py — Reinforcement Scheduler (Phase 3)

Every 24h:
- Retrain with new feedback
- Increase weight for high-impact samples
- Decrease weight for false positives
"""

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable, Dict, List, Optional

import numpy as np

logger = logging.getLogger(__name__)

RETRAIN_INTERVAL_SEC = 86400  # 24 hours


@dataclass
class ReinforcementCycle:
    """A single reinforcement cycle."""
    cycle_number: int
    samples_used: int
    tp_weight_boost: float
    fp_weight_reduction: float
    accuracy_before: float
    accuracy_after: float
    timestamp: str


class ReinforcementScheduler:
    """Schedules periodic reinforcement retraining.

    Every 24h: retrain with feedback-weighted samples.
    """

    def __init__(self, interval_sec: float = RETRAIN_INTERVAL_SEC):
        self.interval_sec = interval_sec
        self._last_retrain: float = 0
        self._cycle_count: int = 0
        self._history: List[ReinforcementCycle] = []

    def is_due(self) -> bool:
        """Check if reinforcement retrain is due."""
        if self._last_retrain == 0:
            return True
        return (time.time() - self._last_retrain) >= self.interval_sec

    def compute_weights(
        self,
        outcomes: List[str],
        base_weight: float = 1.0,
        tp_boost: float = 1.5,
        fp_penalty: float = 0.3,
    ) -> np.ndarray:
        """Compute sample weights from feedback outcomes."""
        weights = np.ones(len(outcomes), dtype=np.float32) * base_weight

        for i, outcome in enumerate(outcomes):
            if outcome == "true_positive":
                weights[i] *= tp_boost
            elif outcome == "false_positive":
                weights[i] *= fp_penalty
            elif outcome == "accepted":
                weights[i] *= 1.2
            elif outcome == "rejected":
                weights[i] *= 0.5

        return weights

    def run_cycle(
        self,
        outcomes: List[str],
        accuracy_before: float,
        retrain_fn: Optional[Callable] = None,
    ) -> ReinforcementCycle:
        """Run one reinforcement cycle."""
        self._cycle_count += 1
        weights = self.compute_weights(outcomes)

        tp_boost = float(weights[np.array(outcomes) == "true_positive"].mean()) if "true_positive" in outcomes else 1.0
        fp_weight = float(weights[np.array(outcomes) == "false_positive"].mean()) if "false_positive" in outcomes else 1.0

        accuracy_after = accuracy_before
        if retrain_fn:
            try:
                result = retrain_fn(weights)
                accuracy_after = result.get("accuracy", accuracy_before)
            except Exception:
                pass

        self._last_retrain = time.time()

        cycle = ReinforcementCycle(
            cycle_number=self._cycle_count,
            samples_used=len(outcomes),
            tp_weight_boost=round(tp_boost, 4),
            fp_weight_reduction=round(fp_weight, 4),
            accuracy_before=accuracy_before,
            accuracy_after=accuracy_after,
            timestamp=datetime.now().isoformat(),
        )
        self._history.append(cycle)

        logger.info(
            f"[REINFORCE] Cycle {self._cycle_count}: "
            f"{len(outcomes)} samples, "
            f"acc {accuracy_before:.4f}→{accuracy_after:.4f}"
        )
        return cycle

    @property
    def cycle_count(self) -> int:
        return self._cycle_count
