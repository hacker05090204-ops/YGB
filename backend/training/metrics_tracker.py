"""Per-class validation metrics tracking for incremental training."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from sklearn.metrics import accuracy_score, precision_recall_fscore_support


@dataclass(frozen=True)
class ClassMetrics:
    label: int
    name: str
    precision: float
    recall: float
    f1: float
    support: int

    def to_dict(self) -> dict[str, object]:
        return {
            "label": self.label,
            "name": self.name,
            "precision": self.precision,
            "recall": self.recall,
            "f1": self.f1,
            "support": self.support,
        }


@dataclass(frozen=True)
class MetricsReport:
    accuracy: float
    macro_precision: float
    macro_recall: float
    macro_f1: float
    weighted_precision: float
    weighted_recall: float
    weighted_f1: float
    support_total: int
    per_class: dict[int, ClassMetrics]
    best_class: ClassMetrics
    worst_class: ClassMetrics

    def to_dict(self) -> dict[str, object]:
        return {
            "accuracy": self.accuracy,
            "macro_precision": self.macro_precision,
            "macro_recall": self.macro_recall,
            "macro_f1": self.macro_f1,
            "weighted_precision": self.weighted_precision,
            "weighted_recall": self.weighted_recall,
            "weighted_f1": self.weighted_f1,
            "support_total": self.support_total,
            "per_class": {
                str(label): metrics.to_dict()
                for label, metrics in sorted(self.per_class.items())
            },
            "best_class": self.best_class.to_dict(),
            "worst_class": self.worst_class.to_dict(),
        }


class MetricsTracker:
    """Computes and stores honest validation metrics reports."""

    def __init__(self, *, label_names: dict[int, str] | None = None) -> None:
        self._label_names = {int(label): str(name) for label, name in (label_names or {}).items()}
        self._history: list[MetricsReport] = []

    @property
    def history(self) -> list[MetricsReport]:
        return list(self._history)

    @property
    def last_report(self) -> MetricsReport | None:
        return self._history[-1] if self._history else None

    def reset(self) -> None:
        self._history.clear()

    def update(
        self,
        *,
        labels: Sequence[int],
        predictions: Sequence[int],
    ) -> MetricsReport:
        label_values = [int(value) for value in labels]
        prediction_values = [int(value) for value in predictions]
        discovered_labels = sorted(set(label_values) | set(prediction_values))
        if not discovered_labels:
            raise ValueError("labels and predictions must contain at least one class")

        precision, recall, f1, support = precision_recall_fscore_support(
            label_values,
            prediction_values,
            labels=discovered_labels,
            zero_division=0,
        )
        macro_precision, macro_recall, macro_f1, _ = precision_recall_fscore_support(
            label_values,
            prediction_values,
            average="macro",
            zero_division=0,
        )
        weighted_precision, weighted_recall, weighted_f1, _ = precision_recall_fscore_support(
            label_values,
            prediction_values,
            average="weighted",
            zero_division=0,
        )

        per_class = {
            int(label): ClassMetrics(
                label=int(label),
                name=self._label_names.get(int(label), f"LABEL_{int(label)}"),
                precision=float(precision[index]),
                recall=float(recall[index]),
                f1=float(f1[index]),
                support=int(support[index]),
            )
            for index, label in enumerate(discovered_labels)
        }
        ranked_classes = sorted(
            per_class.values(),
            key=lambda metrics: (metrics.f1, metrics.recall, metrics.support, -metrics.label),
        )
        report = MetricsReport(
            accuracy=float(accuracy_score(label_values, prediction_values)),
            macro_precision=float(macro_precision),
            macro_recall=float(macro_recall),
            macro_f1=float(macro_f1),
            weighted_precision=float(weighted_precision),
            weighted_recall=float(weighted_recall),
            weighted_f1=float(weighted_f1),
            support_total=int(sum(metric.support for metric in per_class.values())),
            per_class=per_class,
            worst_class=ranked_classes[0],
            best_class=ranked_classes[-1],
        )
        self._history.append(report)
        return report
