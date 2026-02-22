"""
cross_field_validator.py — Cross-Field Validation (Phase 3)

Ensure Field A model does not wrongly classify
Field B samples as positive > threshold.

Prevents pattern leakage between fields.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)

LEAKAGE_THRESHOLD = 0.10   # Max 10% cross-field false positives


@dataclass
class CrossFieldCheck:
    """Result of testing model_A on field_B data."""
    source_field: str
    target_field: str
    false_positive_rate: float
    threshold: float
    passed: bool
    detail: str


@dataclass
class CrossFieldReport:
    """Full cross-field validation report."""
    passed: bool
    checks: List[CrossFieldCheck]
    leakage_detected: List[str]
    timestamp: str = ""


class CrossFieldValidator:
    """Validates no pattern leakage between fields.

    For each pair (A, B): run model_A predictions on field_B data.
    If FPR > threshold → leakage detected.
    """

    def __init__(self, threshold: float = LEAKAGE_THRESHOLD):
        self.threshold = threshold

    def validate_pair(
        self,
        source_field: str,
        target_field: str,
        model_predict_fn,
        target_X: np.ndarray,
        target_y: np.ndarray,
    ) -> CrossFieldCheck:
        """Check if source model leaks into target field.

        Args:
            model_predict_fn: callable(X) → predictions
            target_X: data from target field
            target_y: true labels (should be class 0 / negative for this field)
        """
        preds = model_predict_fn(target_X)

        # FPR: how many target samples does source model wrongly classify as positive
        neg_mask = (target_y == 0)
        if neg_mask.sum() == 0:
            fpr = 0.0
        else:
            fp = ((preds == 1) & neg_mask).sum()
            fpr = float(fp / neg_mask.sum())

        passed = fpr <= self.threshold

        check = CrossFieldCheck(
            source_field=source_field,
            target_field=target_field,
            false_positive_rate=round(fpr, 4),
            threshold=self.threshold,
            passed=passed,
            detail=(
                f"{source_field}→{target_field}: "
                f"FPR={fpr:.4f} {'≤' if passed else '>'} "
                f"{self.threshold}"
            ),
        )

        icon = "✓" if passed else "✗"
        logger.info(f"[CROSS_FIELD] {icon} {check.detail}")

        return check

    def validate_all(
        self,
        field_models: Dict[str, object],
        field_data: Dict[str, Tuple[np.ndarray, np.ndarray]],
        predict_fn,
    ) -> CrossFieldReport:
        """Validate all field pairs.

        Args:
            field_models: {field_name: model}
            field_data: {field_name: (X, y)}
            predict_fn: callable(model, X) → predictions
        """
        checks = []
        leakage = []

        field_names = list(field_models.keys())

        for source in field_names:
            model = field_models[source]
            for target in field_names:
                if source == target:
                    continue
                if target not in field_data:
                    continue

                X_target, y_target = field_data[target]
                check = self.validate_pair(
                    source, target,
                    lambda x: predict_fn(model, x),
                    X_target, y_target,
                )
                checks.append(check)
                if not check.passed:
                    leakage.append(f"{source}→{target}")

        all_passed = len(leakage) == 0

        report = CrossFieldReport(
            passed=all_passed,
            checks=checks,
            leakage_detected=leakage,
            timestamp=datetime.now().isoformat(),
        )

        if all_passed:
            logger.info(
                f"[CROSS_FIELD] ✓ No leakage: "
                f"{len(checks)} pairs checked"
            )
        else:
            logger.error(
                f"[CROSS_FIELD] ✗ Leakage detected: "
                f"{', '.join(leakage)}"
            )

        return report
