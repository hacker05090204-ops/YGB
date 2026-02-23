"""
sub_pattern_validator.py — Sub-Pattern Validation (Phase 2)

Per-field sub-category accuracy tracking.
If any sub-pattern < 85% while global ≥ 95% → PARTIAL_READY.
Do not promote to MODE B.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional

import numpy as np

logger = logging.getLogger(__name__)

SUB_PATTERN_MIN_ACCURACY = 0.85
GLOBAL_THRESHOLD = 0.95


@dataclass
class SubPatternResult:
    """Accuracy for a single sub-pattern."""
    sub_pattern: str
    accuracy: float
    support: int
    passed: bool


@dataclass
class SubPatternReport:
    """Full sub-pattern validation report."""
    field_name: str
    global_accuracy: float
    sub_results: List[SubPatternResult]
    weak_patterns: List[str]
    status: str         # FULL_READY / PARTIAL_READY / NOT_READY
    reason: str
    timestamp: str = ""


class SubPatternValidator:
    """Validates per-sub-category accuracy within a field.

    FULL_READY: global ≥ 95% AND all sub-patterns ≥ 85%
    PARTIAL_READY: global ≥ 95% BUT some sub-patterns < 85%
    NOT_READY: global < 95%
    """

    def __init__(
        self,
        sub_min: float = SUB_PATTERN_MIN_ACCURACY,
        global_min: float = GLOBAL_THRESHOLD,
    ):
        self.sub_min = sub_min
        self.global_min = global_min

    def validate(
        self,
        field_name: str,
        y_true: np.ndarray,
        y_pred: np.ndarray,
        sub_tags: np.ndarray,
    ) -> SubPatternReport:
        """Validate accuracy per sub-pattern.

        Args:
            y_true: Ground truth labels
            y_pred: Predicted labels
            sub_tags: Sub-pattern tag per sample (e.g. ["sqli", "xss", ...])
        """
        global_acc = float((y_true == y_pred).mean())

        unique_tags = np.unique(sub_tags)
        sub_results = []
        weak = []

        for tag in unique_tags:
            mask = (sub_tags == tag)
            if mask.sum() == 0:
                continue
            acc = float((y_true[mask] == y_pred[mask]).mean())
            ok = acc >= self.sub_min
            sub_results.append(SubPatternResult(
                sub_pattern=str(tag),
                accuracy=round(acc, 4),
                support=int(mask.sum()),
                passed=ok,
            ))
            if not ok:
                weak.append(str(tag))

        if global_acc < self.global_min:
            status = "NOT_READY"
            reason = f"Global accuracy {global_acc:.4f} < {self.global_min}"
        elif weak:
            status = "PARTIAL_READY"
            reason = f"Weak sub-patterns: {', '.join(weak)}"
        else:
            status = "FULL_READY"
            reason = "All sub-patterns ≥ threshold"

        report = SubPatternReport(
            field_name=field_name,
            global_accuracy=round(global_acc, 4),
            sub_results=sub_results,
            weak_patterns=weak,
            status=status,
            reason=reason,
            timestamp=datetime.now().isoformat(),
        )

        icon = "★" if status == "FULL_READY" else ("⚠" if status == "PARTIAL_READY" else "✗")
        logger.info(
            f"[SUB_PATTERN] {icon} {field_name}: {status} "
            f"global={global_acc:.4f}"
        )
        for sr in sub_results:
            si = "✓" if sr.passed else "✗"
            logger.info(
                f"  {si} [{sr.sub_pattern}] acc={sr.accuracy:.4f} n={sr.support}"
            )

        return report
