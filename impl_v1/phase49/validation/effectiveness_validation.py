"""Verified effectiveness validation for the accuracy-first pipeline."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Optional, Tuple

from impl_v1.training.evaluation.accuracy_metrics import (
    AccuracyFeedbackStore,
    MetricsSnapshot,
)


@dataclass(slots=True)
class EffectivenessMetrics:
    """Compatibility wrapper around confusion-matrix metrics."""

    true_positives: int
    true_negatives: int
    false_positives: int
    false_negatives: int
    duplicates_rejected: int
    validated_records: int

    @property
    def accuracy(self) -> float:
        total = self.validated_records or 1
        return (self.true_positives + self.true_negatives) / total

    @property
    def tpr(self) -> float:
        total_positives = self.true_positives + self.false_negatives
        return self.true_positives / total_positives if total_positives else 0.0

    @property
    def recall(self) -> float:
        return self.tpr

    @property
    def fpr(self) -> float:
        total_negatives = self.true_negatives + self.false_positives
        return self.false_positives / total_negatives if total_negatives else 0.0

    @property
    def fnr(self) -> float:
        total_positives = self.true_positives + self.false_negatives
        return self.false_negatives / total_positives if total_positives else 0.0

    @property
    def precision(self) -> float:
        predicted_positive = self.true_positives + self.false_positives
        return self.true_positives / predicted_positive if predicted_positive else 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "true_positives": self.true_positives,
            "true_negatives": self.true_negatives,
            "false_positives": self.false_positives,
            "false_negatives": self.false_negatives,
            "duplicates_rejected": self.duplicates_rejected,
            "validated_records": self.validated_records,
            "accuracy": round(self.accuracy, 4),
            "precision": round(self.precision, 4),
            "recall": round(self.recall, 4),
            "false_positive_rate": round(self.fpr, 4),
            "false_negative_rate": round(self.fnr, 4),
        }


def _convert(snapshot: MetricsSnapshot) -> EffectivenessMetrics:
    return EffectivenessMetrics(
        true_positives=snapshot.true_positives,
        true_negatives=snapshot.true_negatives,
        false_positives=snapshot.false_positives,
        false_negatives=snapshot.false_negatives,
        duplicates_rejected=snapshot.duplicates_rejected,
        validated_records=snapshot.validated_records,
    )


def run_effectiveness_validation(
    records_path: Optional[str | Path] = None,
) -> Tuple[EffectivenessMetrics, dict[str, Any]]:
    """Evaluate the real pipeline using validated prediction outcomes only."""
    store = AccuracyFeedbackStore(Path(records_path) if records_path else None)
    snapshot = store.metrics()
    metrics = _convert(snapshot)
    report = metrics.to_dict()
    report["by_category"] = store.metrics_by_category()
    report["records_path"] = str(store.records_path)
    return metrics, report
