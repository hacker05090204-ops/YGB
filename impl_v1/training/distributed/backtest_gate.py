"""
backtest_gate.py — Backtest Before Freeze (Phase 6)

Compare with previous model:
- Require ≥2% improvement OR no regression
- Reject freeze if worse
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

IMPROVEMENT_THRESHOLD = 0.02   # 2%
REGRESSION_TOLERANCE = 0.005   # 0.5% tolerance


@dataclass
class BacktestResult:
    """Result of backtest comparison."""
    freeze_allowed: bool
    new_accuracy: float
    previous_accuracy: float
    delta: float
    reason: str
    field_name: str
    timestamp: str = ""


class BacktestGate:
    """Gate: compare new vs previous before freezing.

    Rules:
    - ≥2% improvement → FREEZE
    - Within 0.5% → FREEZE (no regression)
    - Worse by >0.5% → REJECT
    """

    def __init__(
        self,
        improvement: float = IMPROVEMENT_THRESHOLD,
        tolerance: float = REGRESSION_TOLERANCE,
    ):
        self.improvement = improvement
        self.tolerance = tolerance
        self._history: Dict[str, float] = {}  # field → best accuracy

    def check(
        self,
        field_name: str,
        new_accuracy: float,
        previous_accuracy: Optional[float] = None,
    ) -> BacktestResult:
        """Check if model should be frozen.

        Uses stored history if no previous_accuracy provided.
        """
        prev = previous_accuracy
        if prev is None:
            prev = self._history.get(field_name)

        if prev is None:
            # No previous — auto-pass
            self._history[field_name] = new_accuracy
            result = BacktestResult(
                freeze_allowed=True,
                new_accuracy=new_accuracy,
                previous_accuracy=0.0,
                delta=new_accuracy,
                reason="No previous model — auto-freeze",
                field_name=field_name,
                timestamp=datetime.now().isoformat(),
            )
            logger.info(
                f"[BACKTEST] ✓ {field_name}: first model, "
                f"acc={new_accuracy:.4f}"
            )
            return result

        delta = new_accuracy - prev

        if delta >= self.improvement:
            # Clear improvement
            allowed = True
            reason = f"Improved by {delta:.4f} ≥ {self.improvement}"
        elif delta >= -self.tolerance:
            # Within tolerance (no regression)
            allowed = True
            reason = f"Within tolerance: delta={delta:+.4f}"
        else:
            # Regression
            allowed = False
            reason = f"REGRESSION: delta={delta:+.4f} exceeds tolerance"

        if allowed:
            self._history[field_name] = max(
                self._history.get(field_name, 0), new_accuracy,
            )

        result = BacktestResult(
            freeze_allowed=allowed,
            new_accuracy=new_accuracy,
            previous_accuracy=prev,
            delta=round(delta, 4),
            reason=reason,
            field_name=field_name,
            timestamp=datetime.now().isoformat(),
        )

        icon = "✓" if allowed else "✗"
        logger.info(
            f"[BACKTEST] {icon} {field_name}: "
            f"new={new_accuracy:.4f} prev={prev:.4f} "
            f"Δ={delta:+.4f} — {reason}"
        )
        return result
