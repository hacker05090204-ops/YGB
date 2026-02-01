"""
Tests for Phase-26 Deny-By-Default.

Tests:
- Unsealed intent → BLOCK
- Missing inputs → BLOCK
- All clear checks pass
"""
import pytest


class TestDenyByDefault:
    """Test deny-by-default behavior."""

    def test_draft_intent_blocks(self):
        """DRAFT (unsealed) intent is BLOCK."""
        from HUMANOID_HUNTER.readiness.readiness_engine import decide_readiness
        from HUMANOID_HUNTER.readiness.readiness_context import ReadinessContext
        from HUMANOID_HUNTER.readiness.readiness_types import ReadinessDecision
        from HUMANOID_HUNTER.orchestration import (
            OrchestrationIntent, OrchestrationIntentState
        )
        from HUMANOID_HUNTER.planning import ExecutionPlan

        plan = ExecutionPlan(plan_id="PLAN-001", steps=())
        intent = OrchestrationIntent(
            intent_id="INTENT-001",
            execution_plan=plan,
            capability_snapshot=frozenset(),
            evidence_requirements=frozenset({"screenshot"}),
            created_at="2026-01-25T17:47:00-05:00",
            state=OrchestrationIntentState.DRAFT  # NOT sealed!
        )

        context = ReadinessContext(
            orchestration_intent=intent,
            capability_result_accepted=True,
            sandbox_policy_allows=True,
            native_policy_accepts=True,
            evidence_verification_passed=True,
            human_present=True
        )

        result = decide_readiness(context)
        assert result.decision == ReadinessDecision.BLOCK

    def test_rejected_intent_blocks(self):
        """REJECTED intent is BLOCK."""
        from HUMANOID_HUNTER.readiness.readiness_engine import decide_readiness
        from HUMANOID_HUNTER.readiness.readiness_context import ReadinessContext
        from HUMANOID_HUNTER.readiness.readiness_types import ReadinessDecision
        from HUMANOID_HUNTER.orchestration import (
            OrchestrationIntent, OrchestrationIntentState
        )
        from HUMANOID_HUNTER.planning import ExecutionPlan

        plan = ExecutionPlan(plan_id="PLAN-001", steps=())
        intent = OrchestrationIntent(
            intent_id="INTENT-001",
            execution_plan=plan,
            capability_snapshot=frozenset(),
            evidence_requirements=frozenset({"screenshot"}),
            created_at="2026-01-25T17:47:00-05:00",
            state=OrchestrationIntentState.REJECTED  # Rejected!
        )

        context = ReadinessContext(
            orchestration_intent=intent,
            capability_result_accepted=True,
            sandbox_policy_allows=True,
            native_policy_accepts=True,
            evidence_verification_passed=True,
            human_present=True
        )

        result = decide_readiness(context)
        assert result.decision == ReadinessDecision.BLOCK

    def test_none_intent_blocks(self):
        """None intent is BLOCK."""
        from HUMANOID_HUNTER.readiness.readiness_engine import decide_readiness
        from HUMANOID_HUNTER.readiness.readiness_context import ReadinessContext
        from HUMANOID_HUNTER.readiness.readiness_types import ReadinessDecision

        context = ReadinessContext(
            orchestration_intent=None,  # None!
            capability_result_accepted=True,
            sandbox_policy_allows=True,
            native_policy_accepts=True,
            evidence_verification_passed=True,
            human_present=True
        )

        result = decide_readiness(context)
        assert result.decision == ReadinessDecision.BLOCK

    def test_missing_capability_blocks(self):
        """Missing capability result is BLOCK."""
        from HUMANOID_HUNTER.readiness.readiness_engine import decide_readiness
        from HUMANOID_HUNTER.readiness.readiness_context import ReadinessContext
        from HUMANOID_HUNTER.readiness.readiness_types import ReadinessDecision
        from HUMANOID_HUNTER.orchestration import (
            OrchestrationIntent, OrchestrationIntentState
        )
        from HUMANOID_HUNTER.planning import ExecutionPlan

        plan = ExecutionPlan(plan_id="PLAN-001", steps=())
        intent = OrchestrationIntent(
            intent_id="INTENT-001",
            execution_plan=plan,
            capability_snapshot=frozenset(),
            evidence_requirements=frozenset({"screenshot"}),
            created_at="2026-01-25T17:47:00-05:00",
            state=OrchestrationIntentState.SEALED
        )

        context = ReadinessContext(
            orchestration_intent=intent,
            capability_result_accepted=False,  # NOT accepted!
            sandbox_policy_allows=True,
            native_policy_accepts=True,
            evidence_verification_passed=True,
            human_present=True
        )

        result = decide_readiness(context)
        assert result.decision == ReadinessDecision.BLOCK


class TestResultReason:
    """Test that results include reasons."""

    def test_block_has_reason(self):
        """BLOCK decisions have non-empty reason."""
        from HUMANOID_HUNTER.readiness.readiness_engine import decide_readiness
        from HUMANOID_HUNTER.readiness.readiness_context import ReadinessContext
        from HUMANOID_HUNTER.readiness.readiness_types import ReadinessDecision

        context = ReadinessContext(
            orchestration_intent=None,
            capability_result_accepted=True,
            sandbox_policy_allows=True,
            native_policy_accepts=True,
            evidence_verification_passed=True,
            human_present=True
        )

        result = decide_readiness(context)
        assert result.decision == ReadinessDecision.BLOCK
        assert len(result.reason) > 0

    def test_allow_has_reason(self):
        """ALLOW decisions have non-empty reason."""
        from HUMANOID_HUNTER.readiness.readiness_engine import decide_readiness
        from HUMANOID_HUNTER.readiness.readiness_context import ReadinessContext
        from HUMANOID_HUNTER.readiness.readiness_types import ReadinessDecision
        from HUMANOID_HUNTER.orchestration import (
            OrchestrationIntent, OrchestrationIntentState
        )
        from HUMANOID_HUNTER.planning import (
            ExecutionPlan, ActionPlanStep, PlannedActionType, PlanRiskLevel
        )

        step = ActionPlanStep(
            step_id="STEP-001",
            action_type=PlannedActionType.CLICK,
            parameters={"selector": "#submit"},
            risk_level=PlanRiskLevel.LOW
        )

        plan = ExecutionPlan(plan_id="PLAN-001", steps=(step,))
        intent = OrchestrationIntent(
            intent_id="INTENT-001",
            execution_plan=plan,
            capability_snapshot=frozenset({PlannedActionType.CLICK}),
            evidence_requirements=frozenset({"screenshot"}),
            created_at="2026-01-25T17:47:00-05:00",
            state=OrchestrationIntentState.SEALED
        )

        context = ReadinessContext(
            orchestration_intent=intent,
            capability_result_accepted=True,
            sandbox_policy_allows=True,
            native_policy_accepts=True,
            evidence_verification_passed=True,
            human_present=True
        )

        result = decide_readiness(context)
        assert result.decision == ReadinessDecision.ALLOW
        assert len(result.reason) > 0


class TestDenialReasons:
    """Test specific denial reasons for each dependency."""

    def test_sandbox_denial_has_correct_reason(self):
        """Sandbox denial has specific reason."""
        from HUMANOID_HUNTER.readiness.readiness_engine import decide_readiness
        from HUMANOID_HUNTER.readiness.readiness_context import ReadinessContext
        from HUMANOID_HUNTER.readiness.readiness_types import ReadinessDecision
        from HUMANOID_HUNTER.orchestration import (
            OrchestrationIntent, OrchestrationIntentState
        )
        from HUMANOID_HUNTER.planning import ExecutionPlan

        plan = ExecutionPlan(plan_id="PLAN-001", steps=())
        intent = OrchestrationIntent(
            intent_id="INTENT-001",
            execution_plan=plan,
            capability_snapshot=frozenset(),
            evidence_requirements=frozenset({"screenshot"}),
            created_at="2026-01-25T17:47:00-05:00",
            state=OrchestrationIntentState.SEALED
        )

        context = ReadinessContext(
            orchestration_intent=intent,
            capability_result_accepted=True,
            sandbox_policy_allows=False,  # Sandbox denies!
            native_policy_accepts=True,
            evidence_verification_passed=True,
            human_present=True
        )

        result = decide_readiness(context)
        assert result.decision == ReadinessDecision.BLOCK
        assert "Sandbox" in result.reason

    def test_native_denial_has_correct_reason(self):
        """Native denial has specific reason."""
        from HUMANOID_HUNTER.readiness.readiness_engine import decide_readiness
        from HUMANOID_HUNTER.readiness.readiness_context import ReadinessContext
        from HUMANOID_HUNTER.readiness.readiness_types import ReadinessDecision
        from HUMANOID_HUNTER.orchestration import (
            OrchestrationIntent, OrchestrationIntentState
        )
        from HUMANOID_HUNTER.planning import ExecutionPlan

        plan = ExecutionPlan(plan_id="PLAN-001", steps=())
        intent = OrchestrationIntent(
            intent_id="INTENT-001",
            execution_plan=plan,
            capability_snapshot=frozenset(),
            evidence_requirements=frozenset({"screenshot"}),
            created_at="2026-01-25T17:47:00-05:00",
            state=OrchestrationIntentState.SEALED
        )

        context = ReadinessContext(
            orchestration_intent=intent,
            capability_result_accepted=True,
            sandbox_policy_allows=True,
            native_policy_accepts=False,  # Native denies!
            evidence_verification_passed=True,
            human_present=True
        )

        result = decide_readiness(context)
        assert result.decision == ReadinessDecision.BLOCK
        assert "Native" in result.reason

    def test_evidence_denial_has_correct_reason(self):
        """Evidence denial has specific reason."""
        from HUMANOID_HUNTER.readiness.readiness_engine import decide_readiness
        from HUMANOID_HUNTER.readiness.readiness_context import ReadinessContext
        from HUMANOID_HUNTER.readiness.readiness_types import ReadinessDecision
        from HUMANOID_HUNTER.orchestration import (
            OrchestrationIntent, OrchestrationIntentState
        )
        from HUMANOID_HUNTER.planning import ExecutionPlan

        plan = ExecutionPlan(plan_id="PLAN-001", steps=())
        intent = OrchestrationIntent(
            intent_id="INTENT-001",
            execution_plan=plan,
            capability_snapshot=frozenset(),
            evidence_requirements=frozenset({"screenshot"}),
            created_at="2026-01-25T17:47:00-05:00",
            state=OrchestrationIntentState.SEALED
        )

        context = ReadinessContext(
            orchestration_intent=intent,
            capability_result_accepted=True,
            sandbox_policy_allows=True,
            native_policy_accepts=True,
            evidence_verification_passed=False,  # Evidence denies!
            human_present=True
        )

        result = decide_readiness(context)
        assert result.decision == ReadinessDecision.BLOCK
        assert "Evidence" in result.reason


class TestEmptyPlanRiskLevel:
    """Test empty plan risk level."""

    def test_empty_plan_allows_without_human(self):
        """Empty plan (LOW risk) allows without human."""
        from HUMANOID_HUNTER.readiness.readiness_engine import decide_readiness
        from HUMANOID_HUNTER.readiness.readiness_context import ReadinessContext
        from HUMANOID_HUNTER.readiness.readiness_types import ReadinessDecision
        from HUMANOID_HUNTER.orchestration import (
            OrchestrationIntent, OrchestrationIntentState
        )
        from HUMANOID_HUNTER.planning import ExecutionPlan

        # Empty plan
        plan = ExecutionPlan(plan_id="PLAN-001", steps=())
        intent = OrchestrationIntent(
            intent_id="INTENT-001",
            execution_plan=plan,
            capability_snapshot=frozenset(),
            evidence_requirements=frozenset({"screenshot"}),
            created_at="2026-01-25T17:47:00-05:00",
            state=OrchestrationIntentState.SEALED
        )

        context = ReadinessContext(
            orchestration_intent=intent,
            capability_result_accepted=True,
            sandbox_policy_allows=True,
            native_policy_accepts=True,
            evidence_verification_passed=True,
            human_present=False  # No human, but empty plan = LOW risk
        )

        result = decide_readiness(context)
        assert result.decision == ReadinessDecision.ALLOW
