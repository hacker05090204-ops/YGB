"""Tests for accuracy metrics and false-positive tracking."""

from __future__ import annotations

from pathlib import Path

from impl_v1.training.evaluation.accuracy_metrics import (
    AccuracyFeedbackStore,
    EvaluationRecord,
    StrategyFeedbackStore,
)


def test_accuracy_feedback_metrics(tmp_path: Path):
    store = AccuracyFeedbackStore(tmp_path / "verified_findings.jsonl")
    store.add(
        EvaluationRecord(
            fingerprint="fp-1",
            category="SQLI",
            severity="HIGH",
            title="Confirmed finding",
            description="real proof",
            url="https://example.com/a",
            predicted_positive=True,
            actual_positive=True,
            verification_status="CONFIRMED",
            confidence=0.99,
        )
    )
    store.add(
        EvaluationRecord(
            fingerprint="fp-2",
            category="SQLI",
            severity="LOW",
            title="Rejected finding",
            description="not real",
            url="https://example.com/b",
            predicted_positive=True,
            actual_positive=False,
            verification_status="REJECTED_FALSE_POSITIVE",
            confidence=0.2,
            false_positive=True,
        )
    )
    store.add(
        EvaluationRecord(
            fingerprint="fp-3",
            category="XSS",
            severity="MEDIUM",
            title="Duplicate finding",
            description="duplicate",
            url="https://example.com/c",
            predicted_positive=True,
            actual_positive=False,
            verification_status="DUPLICATE",
            confidence=0.1,
            duplicate=True,
            false_positive=True,
        )
    )

    summary = store.summary()
    assert summary["validated_records"] == 3
    assert summary["true_positives"] == 1
    assert summary["false_positives"] == 2
    assert summary["duplicates_rejected"] == 1
    assert summary["precision"] == 0.3333
    assert summary["by_category"]["SQLI"]["validated_records"] == 2


def test_strategy_feedback_scoring():
    feedback = StrategyFeedbackStore()
    feedback.record(
        strategy_name="workflow-orchestrator",
        task_type="workflow",
        verified_findings=3,
        rejected_findings=1,
        duplicate_findings=0,
    )
    feedback.record(
        strategy_name="workflow-orchestrator",
        task_type="workflow",
        verified_findings=1,
        rejected_findings=3,
        duplicate_findings=2,
    )
    snapshot = feedback.get(
        strategy_name="workflow-orchestrator",
        task_type="workflow",
    )
    assert snapshot.runs == 2
    assert snapshot.precision < 0.6
    assert snapshot.score < 0.6
