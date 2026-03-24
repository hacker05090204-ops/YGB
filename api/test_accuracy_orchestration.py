"""Tests for accuracy-first verification and reasoning layers."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from orchestrator import (
    AccuracyEngine,
    AgentProfile,
    AgentRegistry,
    TaskReasoner,
)
from impl_v1.training.evaluation.accuracy_metrics import (
    AccuracyFeedbackStore,
    StrategyFeedbackStore,
)


def _registry() -> AgentRegistry:
    registry = AgentRegistry()
    registry.register(
        AgentProfile(
            "workflow-orchestrator",
            ("workflow", "request"),
            "Routes workflows",
            4,
        )
    )
    registry.register(
        AgentProfile(
            "crawler-agent",
            ("crawl", "bounty"),
            "Crawler",
            4,
        )
    )
    return registry


def test_accuracy_engine_rejects_false_positive(tmp_path: Path):
    store = AccuracyFeedbackStore(tmp_path / "verified_findings.jsonl")
    engine = AccuracyEngine(store)

    outcome = engine.verify(
        category="SQLI",
        severity="LOW",
        title="Potential SQL parameter",
        description="candidate without proof",
        url="https://example.com/items?id=1",
        evidence={"payload_tested": True, "verification_failed": True},
    )

    assert outcome.status == "REJECTED_FALSE_POSITIVE"
    summary = store.summary()
    assert summary["false_positives"] == 1
    assert summary["validated_records"] == 1


def test_accuracy_engine_suppresses_semantic_duplicates(tmp_path: Path):
    store = AccuracyFeedbackStore(tmp_path / "verified_findings.jsonl")
    engine = AccuracyEngine(store)

    outcome = engine.verify(
        category="XSS",
        severity="MEDIUM",
        title="Reflected search parameter",
        description="reflected search parameter in response",
        url="https://example.com/search?q=test",
        evidence={"payload_tested": True, "response_validated": True},
        prior_findings=[
            {
                "category": "XSS",
                "title": "Reflected search parameter",
                "url": "https://example.com/search?q=abc",
            }
        ],
    )

    assert outcome.status == "DUPLICATE"
    assert store.summary()["duplicates_rejected"] == 1


def test_task_reasoner_tightens_strategy_after_bad_history(tmp_path: Path):
    accuracy_feedback = AccuracyFeedbackStore(tmp_path / "verified_findings.jsonl")
    strategy_feedback = StrategyFeedbackStore()
    strategy_feedback.record(
        strategy_name="workflow-orchestrator",
        task_type="workflow",
        verified_findings=1,
        rejected_findings=8,
        duplicate_findings=2,
    )
    strategy_feedback.record(
        strategy_name="workflow-orchestrator",
        task_type="workflow",
        verified_findings=1,
        rejected_findings=6,
        duplicate_findings=1,
    )
    strategy_feedback.record(
        strategy_name="workflow-orchestrator",
        task_type="workflow",
        verified_findings=0,
        rejected_findings=4,
        duplicate_findings=1,
    )

    reasoner = TaskReasoner(_registry(), strategy_feedback, accuracy_feedback)
    plan = reasoner.plan(
        "workflow", {"target": "https://example.com", "mode": "READ_ONLY"}
    )

    assert plan.strategy.verification_level == "strict"
    assert plan.strategy.payload_profile == "passive-verified"
    assert any("Historical precision" in note for note in plan.strategy.notes)
