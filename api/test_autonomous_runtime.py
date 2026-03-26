"""Tests for the reasoning-first autonomous runtime."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from autonomous_runtime import AutonomousCoordinator
from impl_v1.training.data.autonomous_data_pipeline import AutonomousDataPipeline
from impl_v1.training.evaluation.accuracy_metrics import (
    AccuracyFeedbackStore,
    StrategyFeedbackStore,
)
from orchestrator import AccuracyEngine, AgentProfile, BackendOrchestrator


def _agents() -> list[AgentProfile]:
    return [
        AgentProfile("workflow-orchestrator", ("workflow", "request"), "Workflow", 4),
        AgentProfile(
            "verification-agent", ("workflow", "bounty", "verify"), "Verify", 3
        ),
        AgentProfile("learning-agent", ("training", "ml", "learning"), "Learn", 1),
        AgentProfile("reasoning-agent", ("request", "voice", "query"), "Reason", 2),
    ]


def test_reasoning_trace_adds_blind_checks(tmp_path: Path):
    coordinator = AutonomousCoordinator(
        AccuracyFeedbackStore(tmp_path / "verified.jsonl"),
        StrategyFeedbackStore(),
        AutonomousDataPipeline(tmp_path),
    )

    trace = coordinator.build_reasoning_trace(
        "workflow",
        {
            "target": "https://example.com/proxy",
            "query": "verify SSRF with oob callback and time-based confirmation",
            "category": "SSRF",
            "severity": "HIGH",
            "dom_excerpt": "api graphql login endpoint",
            "title": "Potential SSRF",
            "description": "callback based blind verification required",
            "evidence": {"payload_tested": True, "needs_manual_review": True},
        },
        _agents(),
    )

    blueprint = trace["verification_blueprint"]
    assert "oob-callback-check" in blueprint["blind_checks"]
    assert "time-based-blind-check" in blueprint["blind_checks"]
    assert trace["expert_routes"][0]["agent_name"] in {
        "workflow-orchestrator",
        "verification-agent",
    }


def test_reasoned_response_explains_before_acting(tmp_path: Path):
    coordinator = AutonomousCoordinator(
        AccuracyFeedbackStore(tmp_path / "verified.jsonl"),
        StrategyFeedbackStore(),
        AutonomousDataPipeline(tmp_path),
    )

    response = coordinator.build_reasoned_response(
        query="How would you investigate login abuse safely?",
        task_type="request",
        context={
            "target": "https://example.com/login",
            "dom_excerpt": "login password csrf api",
            "severity": "MEDIUM",
            "category": "AUTH",
        },
        agents=_agents(),
        similar_experiences=[{"memory_id": "MEM-1", "content": "prior auth workflow"}],
    )

    assert "before acting" in response.answer
    assert any("verification" in item.lower() for item in response.recommendations)
    assert response.confidence > 0.6


def test_data_pipeline_quarantines_uncertain_candidate(tmp_path: Path):
    pipeline = AutonomousDataPipeline(tmp_path)
    assessment = pipeline.record_candidate(
        category="AUTH",
        severity="MEDIUM",
        title="Possible auth issue",
        description="Candidate needs more proof before execution or training",
        url="https://example.com/login",
        evidence={"payload_tested": True, "needs_manual_review": True},
        verification_status="NEEDS_REVIEW",
        duplicate=False,
        confidence=0.52,
    )

    assert assessment.destination == "quarantine"
    assert pipeline.summary()["quarantine"] == 1


def test_accuracy_engine_confirms_blind_time_based_signal(tmp_path: Path):
    store = AccuracyFeedbackStore(tmp_path / "verified.jsonl")
    engine = AccuracyEngine(store)
    engine.data_pipeline = AutonomousDataPipeline(tmp_path)

    outcome = engine.verify(
        category="SQLI",
        severity="HIGH",
        title="Blind SQL injection candidate",
        description="delay-based blind behavior reproduced twice",
        url="https://example.com/items?id=1",
        evidence={
            "payload_tested": True,
            "baseline_latency_ms": 120.0,
            "probe_latency_ms": 2350.0,
            "blind_reproduction_count": 2,
        },
        strategy_name="verification-agent",
        task_type="workflow",
    )

    assert outcome.status == "CONFIRMED"
    assert any("Time-based blind signal" in note for note in outcome.notes)


def test_plan_task_enriches_reasoning_trace():
    orchestrator = BackendOrchestrator()
    orchestrator._register_default_agents()
    plan = orchestrator.plan_task(
        "workflow",
        {
            "target": "https://example.com/api/login",
            "mode": "READ_ONLY",
            "query": "explain how to verify auth and duplicate findings safely",
            "dom_excerpt": "login api graphql csrf",
        },
    )

    assert plan.reasoning_trace
    assert plan.expert_routes
    assert plan.reasoning_trace["selected_tests"]["enabled_tests"]
    assert any("MoE router primary expert" in note for note in plan.strategy.notes)
