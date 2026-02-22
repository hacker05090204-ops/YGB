"""
promotion_controller.py — MODE A → MODE B Promotion (Phase 2)

7-gate promotion:
1. validation_accuracy ≥ 95%
2. consecutive_passes ≥ 3
3. regression_check_passed
4. semantic_gate_passed
5. cross_field_fpr ≤ 10%
6. drift_monitor_stable
7. determinism_match true

If any fail → reset consecutive_passes.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional

logger = logging.getLogger(__name__)

ACCURACY_THRESHOLD = 0.95
CONSECUTIVE_REQUIRED = 3
CROSS_FIELD_FPR_MAX = 0.10


@dataclass
class PromotionCheck:
    """A single promotion gate check."""
    gate_name: str
    passed: bool
    value: float
    threshold: float
    detail: str


@dataclass
class PromotionResult:
    """Result of promotion attempt."""
    promoted: bool
    gates: List[PromotionCheck]
    failed_gates: List[str]
    reason: str
    timestamp: str = ""


class PromotionController:
    """Controls MODE A → MODE B promotion.

    All 7 gates must pass. Any failure resets consecutive passes.
    """

    def __init__(
        self,
        accuracy_threshold: float = ACCURACY_THRESHOLD,
        consecutive_required: int = CONSECUTIVE_REQUIRED,
        cross_field_max: float = CROSS_FIELD_FPR_MAX,
    ):
        self.accuracy_threshold = accuracy_threshold
        self.consecutive_required = consecutive_required
        self.cross_field_max = cross_field_max

    def evaluate(
        self,
        accuracy: float,
        consecutive_passes: int,
        regression_passed: bool = True,
        semantic_passed: bool = True,
        cross_field_fpr: float = 0.0,
        drift_stable: bool = True,
        determinism_match: bool = True,
    ) -> PromotionResult:
        """Evaluate all 7 promotion gates."""
        gates = []

        # Gate 1: Accuracy ≥ 95%
        acc_ok = accuracy >= self.accuracy_threshold
        gates.append(PromotionCheck(
            "accuracy", acc_ok, accuracy, self.accuracy_threshold,
            f"acc={accuracy:.4f} {'≥' if acc_ok else '<'} {self.accuracy_threshold}",
        ))

        # Gate 2: Consecutive passes ≥ 3
        passes_ok = consecutive_passes >= self.consecutive_required
        gates.append(PromotionCheck(
            "consecutive_passes", passes_ok,
            float(consecutive_passes), float(self.consecutive_required),
            f"passes={consecutive_passes} {'≥' if passes_ok else '<'} {self.consecutive_required}",
        ))

        # Gate 3: Regression
        gates.append(PromotionCheck(
            "regression", regression_passed, 1.0 if regression_passed else 0.0, 1.0,
            "No regression" if regression_passed else "Regression detected",
        ))

        # Gate 4: Semantic
        gates.append(PromotionCheck(
            "semantic_quality", semantic_passed, 1.0 if semantic_passed else 0.0, 1.0,
            "Semantic OK" if semantic_passed else "Semantic failed",
        ))

        # Gate 5: Cross-field FPR
        cf_ok = cross_field_fpr <= self.cross_field_max
        gates.append(PromotionCheck(
            "cross_field_fpr", cf_ok, cross_field_fpr, self.cross_field_max,
            f"FPR={cross_field_fpr:.4f} {'≤' if cf_ok else '>'} {self.cross_field_max}",
        ))

        # Gate 6: Drift
        gates.append(PromotionCheck(
            "drift_stable", drift_stable, 1.0 if drift_stable else 0.0, 1.0,
            "Drift stable" if drift_stable else "Drift detected",
        ))

        # Gate 7: Determinism
        gates.append(PromotionCheck(
            "determinism", determinism_match, 1.0 if determinism_match else 0.0, 1.0,
            "Determinism OK" if determinism_match else "Determinism mismatch",
        ))

        all_passed = all(g.passed for g in gates)
        failed = [g.gate_name for g in gates if not g.passed]

        result = PromotionResult(
            promoted=all_passed,
            gates=gates,
            failed_gates=failed,
            reason=(
                "PROMOTED: all 7 gates passed" if all_passed
                else f"BLOCKED: failed = {', '.join(failed)}"
            ),
            timestamp=datetime.now().isoformat(),
        )

        icon = "✓" if all_passed else "✗"
        logger.info(f"[PROMOTION] {icon} {result.reason}")
        for g in gates:
            gi = "✓" if g.passed else "✗"
            logger.info(f"  {gi} [{g.gate_name}] {g.detail}")

        return result
