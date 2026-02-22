"""
regression_validator.py — Regression Validation (Phase 5)

Before freezing new model:
1. Load previous frozen model
2. Run same validation dataset
3. Compare: accuracy, precision, recall, F1
4. Reject if new model worse beyond threshold

Update model_registry.json.
"""

import hashlib
import json
import logging
import os
from dataclasses import dataclass, asdict, field
from datetime import datetime
from typing import Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)

REGRESSION_THRESHOLD = 0.02  # Reject if worse by >2%
REGISTRY_PATH = os.path.join('secure_data', 'model_registry.json')


@dataclass
class ModelMetrics:
    """Metrics for a model evaluation."""
    accuracy: float
    precision: float
    recall: float
    f1: float
    support: int


@dataclass
class RegressionResult:
    """Result of regression comparison."""
    passed: bool
    new_model_version: str
    previous_model_version: str
    new_metrics: ModelMetrics
    previous_metrics: Optional[ModelMetrics]
    deltas: Dict[str, float]
    threshold: float
    reason: str
    timestamp: str = ""


def compute_metrics(
    y_true: np.ndarray,
    y_pred: np.ndarray,
) -> ModelMetrics:
    """Compute accuracy, precision, recall, F1."""
    classes = np.unique(np.concatenate([y_true, y_pred]))
    correct = (y_true == y_pred).sum()
    accuracy = correct / max(len(y_true), 1)

    # Per-class then macro average
    precisions, recalls, f1s = [], [], []
    for c in classes:
        tp = ((y_pred == c) & (y_true == c)).sum()
        fp = ((y_pred == c) & (y_true != c)).sum()
        fn = ((y_pred != c) & (y_true == c)).sum()

        prec = tp / max(tp + fp, 1)
        rec = tp / max(tp + fn, 1)
        f1 = 2 * prec * rec / max(prec + rec, 1e-12)

        precisions.append(prec)
        recalls.append(rec)
        f1s.append(f1)

    return ModelMetrics(
        accuracy=round(float(accuracy), 4),
        precision=round(float(np.mean(precisions)), 4),
        recall=round(float(np.mean(recalls)), 4),
        f1=round(float(np.mean(f1s)), 4),
        support=len(y_true),
    )


class RegressionValidator:
    """Validates new model doesn't regress from previous."""

    def __init__(
        self,
        threshold: float = REGRESSION_THRESHOLD,
        registry_path: str = REGISTRY_PATH,
    ):
        self.threshold = threshold
        self.registry_path = registry_path
        self._registry: List[dict] = []
        self._load_registry()

    def _load_registry(self):
        if os.path.exists(self.registry_path):
            try:
                with open(self.registry_path) as f:
                    self._registry = json.load(f)
            except (json.JSONDecodeError, IOError):
                self._registry = []

    def _save_registry(self):
        os.makedirs(os.path.dirname(self.registry_path), exist_ok=True)
        with open(self.registry_path, 'w') as f:
            json.dump(self._registry, f, indent=2)

    def validate(
        self,
        new_version: str,
        new_y_true: np.ndarray,
        new_y_pred: np.ndarray,
        previous_metrics: Optional[ModelMetrics] = None,
    ) -> RegressionResult:
        """Validate new model against previous.

        Reject if accuracy/F1 drops > threshold.
        """
        new_metrics = compute_metrics(new_y_true, new_y_pred)

        # If no previous, auto-pass
        if previous_metrics is None:
            prev_entry = self._get_latest_registry()
            if prev_entry:
                previous_metrics = ModelMetrics(**prev_entry['metrics'])

        if previous_metrics is None:
            result = RegressionResult(
                passed=True,
                new_model_version=new_version,
                previous_model_version="none",
                new_metrics=new_metrics,
                previous_metrics=None,
                deltas={},
                threshold=self.threshold,
                reason="No previous model — auto-pass",
                timestamp=datetime.now().isoformat(),
            )
            self._update_registry(new_version, new_metrics, True)

            logger.info(
                f"[REGRESSION] ✓ No previous model — pass "
                f"acc={new_metrics.accuracy:.4f} F1={new_metrics.f1:.4f}"
            )
            return result

        # Compare
        deltas = {
            'accuracy': round(new_metrics.accuracy - previous_metrics.accuracy, 4),
            'precision': round(new_metrics.precision - previous_metrics.precision, 4),
            'recall': round(new_metrics.recall - previous_metrics.recall, 4),
            'f1': round(new_metrics.f1 - previous_metrics.f1, 4),
        }

        # Fail if key metrics drop beyond threshold
        acc_drop = -deltas['accuracy']
        f1_drop = -deltas['f1']
        worst_drop = max(acc_drop, f1_drop)

        passed = worst_drop <= self.threshold

        if passed:
            reason = (
                f"OK: worst regression {worst_drop:.4f} "
                f"≤ threshold {self.threshold}"
            )
            logger.info(
                f"[REGRESSION] ✓ Passed: Δacc={deltas['accuracy']:+.4f} "
                f"ΔF1={deltas['f1']:+.4f}"
            )
        else:
            reason = (
                f"REJECTED: worst regression {worst_drop:.4f} "
                f"> threshold {self.threshold}"
            )
            logger.error(
                f"[REGRESSION] ✗ REJECTED: Δacc={deltas['accuracy']:+.4f} "
                f"ΔF1={deltas['f1']:+.4f} — exceeds {self.threshold}"
            )

        prev_version = self._get_latest_registry()
        result = RegressionResult(
            passed=passed,
            new_model_version=new_version,
            previous_model_version=prev_version.get('version', 'unknown') if prev_version else 'none',
            new_metrics=new_metrics,
            previous_metrics=previous_metrics,
            deltas=deltas,
            threshold=self.threshold,
            reason=reason,
            timestamp=datetime.now().isoformat(),
        )

        self._update_registry(new_version, new_metrics, passed)

        return result

    def _get_latest_registry(self) -> Optional[dict]:
        return self._registry[-1] if self._registry else None

    def _update_registry(
        self,
        version: str,
        metrics: ModelMetrics,
        passed: bool,
    ):
        self._registry.append({
            'version': version,
            'metrics': asdict(metrics),
            'passed': passed,
            'timestamp': datetime.now().isoformat(),
        })
        self._save_registry()
