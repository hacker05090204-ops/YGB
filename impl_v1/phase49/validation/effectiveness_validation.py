"""Verified effectiveness validation for the accuracy-first pipeline.

This module now evaluates real validated outcomes, but it also preserves the
older operational-validation helpers so existing tests and tooling continue to
work.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Optional, Tuple

from impl_v1.training.evaluation.accuracy_metrics import (
    AccuracyFeedbackStore,
    MetricsSnapshot,
)


class VulnerabilityType(Enum):
    """Known vulnerability types for compatibility tests."""

    SQL_INJECTION = "sql_injection"
    XSS = "xss"
    PATH_TRAVERSAL = "path_traversal"
    COMMAND_INJECTION = "cmd_injection"
    SSRF = "ssrf"
    XXE = "xxe"
    DESERIALIZATION = "deserialization"
    AUTH_BYPASS = "auth_bypass"
    IDOR = "idor"
    OPEN_REDIRECT = "open_redirect"


@dataclass(slots=True)
class TestCase:
    """Compatibility test case definition."""

    id: str
    name: str
    is_vulnerable: bool
    vulnerability_type: VulnerabilityType | None
    payload: str
    expected_detection: bool


@dataclass(slots=True)
class ScanResult:
    """Compatibility scan result definition."""

    test_id: str
    detected: bool
    confidence: float
    detection_type: str | None


@dataclass(slots=True)
class EffectivenessMetrics:
    """Compatibility wrapper around confusion-matrix metrics."""

    true_positives: int
    true_negatives: int
    false_positives: int
    false_negatives: int
    duplicates_rejected: int = 0
    validated_records: int = 0

    @property
    def accuracy(self) -> float:
        total = self.validated_records or (
            self.true_positives
            + self.true_negatives
            + self.false_positives
            + self.false_negatives
            or 1
        )
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


def generate_vulnerable_cases(count: int = 100) -> list[TestCase]:
    """Generate compatibility vulnerable cases."""
    vulnerability_types = list(VulnerabilityType)
    return [
        TestCase(
            id=f"VULN_{index:03d}",
            name=f"Vulnerable App {index}",
            is_vulnerable=True,
            vulnerability_type=vulnerability_types[index % len(vulnerability_types)],
            payload=f"payload-{index}",
            expected_detection=True,
        )
        for index in range(count)
    ]


def generate_clean_cases(count: int = 100) -> list[TestCase]:
    """Generate compatibility clean cases."""
    return [
        TestCase(
            id=f"CLEAN_{index:03d}",
            name=f"Clean App {index}",
            is_vulnerable=False,
            vulnerability_type=None,
            payload=f"safe-{index}",
            expected_detection=False,
        )
        for index in range(count)
    ]


def mock_scan(case: TestCase) -> ScanResult:
    """Compatibility scanner used by legacy operational tests.

    The behavior is deterministic and intentionally conservative.
    """
    detected = case.is_vulnerable
    confidence = 0.95 if detected else 0.05
    detection_type = (
        case.vulnerability_type.value if detected and case.vulnerability_type else None
    )
    return ScanResult(
        test_id=case.id,
        detected=detected,
        confidence=confidence,
        detection_type=detection_type,
    )


def calculate_metrics(
    cases: list[TestCase],
    results: list[ScanResult],
) -> EffectivenessMetrics:
    """Calculate confusion-matrix metrics for compatibility callers."""
    result_map = {result.test_id: result for result in results}
    tp = tn = fp = fn = 0
    for case in cases:
        result = result_map.get(case.id)
        if result is None:
            continue
        if case.is_vulnerable:
            if result.detected:
                tp += 1
            else:
                fn += 1
        else:
            if result.detected:
                fp += 1
            else:
                tn += 1
    return EffectivenessMetrics(
        true_positives=tp,
        true_negatives=tn,
        false_positives=fp,
        false_negatives=fn,
        validated_records=tp + tn + fp + fn,
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
