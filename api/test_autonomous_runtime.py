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
    assert trace["task_units"]
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


def test_data_pipeline_builds_incremental_training_plan(tmp_path: Path):
    pipeline = AutonomousDataPipeline(tmp_path)
    for index in range(3):
        pipeline.record_candidate(
            category="SQLI",
            severity="HIGH",
            title=f"Validated SQLi {index}",
            description="Confirmed candidate with proof and replay evidence for incremental learning.",
            url=f"https://example.com/items/{index}",
            evidence={
                "payload_tested": True,
                "response_validated": True,
                "proof_verified": True,
                "reproduction_count": 2,
            },
            verification_status="CONFIRMED",
            duplicate=False,
            confidence=0.97,
        )

    plan = pipeline.build_incremental_training_plan()
    assert plan["retrain_from_scratch"] is False
    assert plan["validated_records"] == 3


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
    assert outcome.classification == "confirmed"
    assert any("Time-based blind signal" in note for note in outcome.notes)


def test_accuracy_engine_uses_oob_and_proof_verification(tmp_path: Path):
    store = AccuracyFeedbackStore(tmp_path / "verified.jsonl")
    engine = AccuracyEngine(store, AutonomousDataPipeline(tmp_path))

    outcome = engine.verify(
        category="SSRF",
        severity="HIGH",
        title="SSRF callback confirmation",
        description="out-of-band callback with reproducible proof",
        url="https://example.com/fetch?url=http://cb",
        evidence={
            "payload_tested": True,
            "oob_confirmed": True,
            "input_vector": "url",
            "response_before": "ok",
            "response_after": "delayed ok",
            "request_data": "GET /fetch",
            "response_data": "200",
            "reproduction_count": 2,
            "video_hash": "abc123",
            "extracted_data": "callback-hit",
        },
        strategy_name="verification-agent",
        task_type="workflow",
    )

    assert outcome.status == "CONFIRMED"
    assert any("Out-of-band callback confirmed" in note for note in outcome.notes)


def test_accuracy_engine_uses_behavioral_validation(tmp_path: Path):
    store = AccuracyFeedbackStore(tmp_path / "verified.jsonl")
    engine = AccuracyEngine(store, AutonomousDataPipeline(tmp_path))

    outcome = engine.verify(
        category="IDOR",
        severity="HIGH",
        title="Unauthorized profile access",
        description="changing identifiers reveals another user's profile",
        url="https://example.com/api/profile/2",
        evidence={
            "payload_tested": True,
            "unauthorized_access": True,
            "state_change_confirmed": True,
            "access_validated": True,
        },
        strategy_name="verification-agent",
        task_type="workflow",
    )

    assert outcome.status == "CONFIRMED"
    assert outcome.classification == "confirmed"
    assert any("Behavioral validation confirmed" in note for note in outcome.notes)


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
    assert plan.reasoning_trace["classification"] in {
        "confirmed",
        "probable",
        "hypothesis",
    }
    assert any("MoE router primary expert" in note for note in plan.strategy.notes)


def test_reasoning_trace_uses_similarity_features(tmp_path: Path):
    coordinator = AutonomousCoordinator(
        AccuracyFeedbackStore(tmp_path / "verified.jsonl"),
        StrategyFeedbackStore(),
        AutonomousDataPipeline(tmp_path),
    )

    trace = coordinator.build_reasoning_trace(
        "workflow",
        {
            "target": "https://example.com/api/user?id=1",
            "query": "repeat possible idor finding",
            "category": "IDOR",
            "severity": "HIGH",
            "evidence": {
                "payload": "user_id=1",
                "response_after": "email=user@example.com",
            },
            "current_findings": [
                {
                    "title": "Possible idor finding",
                    "url": "https://example.com/api/user?id=2",
                    "evidence": {
                        "payload": "user_id=2",
                        "response_after": "email=other@example.com",
                    },
                }
            ],
        },
        _agents(),
    )

    features = trace["duplicate_features"]
    assert features["url_similarity"] > 0
    assert features["payload_similarity"] > 0


def test_related_experiences_merge_verified_memory():
    import asyncio

    async def _run() -> None:
        orchestrator = BackendOrchestrator()
        orchestrator._register_default_agents()
        await orchestrator.remember_experience(
            "crawler-agent",
            "workflow strategy for login testing",
            {"agent_name": "crawler-agent"},
        )
        await orchestrator.remember_finding_outcome(
            workflow_id="wf-1",
            target="https://example.com/login",
            finding={
                "category": "AUTH",
                "title": "Verified auth bypass",
                "severity": "HIGH",
                "verification_status": "CONFIRMED",
                "verification_classification": "confirmed",
                "confidence": 0.98,
            },
            strategy_name="verification-agent",
        )
        related = await orchestrator.retrieve_related_experiences(
            "auth bypass login",
            task_type="workflow",
            limit=6,
        )
        assert related
        agent_names = {
            str((item.get("metadata") or {}).get("agent_name") or "")
            for item in related
        }
        assert "crawler-agent" in agent_names or "verification-agent" in agent_names

    asyncio.run(_run())
