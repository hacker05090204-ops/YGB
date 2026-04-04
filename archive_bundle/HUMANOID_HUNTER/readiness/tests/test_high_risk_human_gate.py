"""
Tests for Phase-26 High Risk Human Gate.

Tests:
- HIGH risk requires human_present
- LOW/MEDIUM risk does not require human
"""
import pytest


class TestHighRiskHumanGate:
    """Test HIGH risk human gate."""

    def test_high_risk_no_human_blocks(self):
        """HIGH risk without human is BLOCK."""
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
            action_type=PlannedActionType.UPLOAD,
            parameters={"file": "/path/to/file"},
            risk_level=PlanRiskLevel.HIGH
        )

        plan = ExecutionPlan(plan_id="PLAN-001", steps=(step,))
        intent = OrchestrationIntent(
            intent_id="INTENT-001",
            execution_plan=plan,
            capability_snapshot=frozenset({PlannedActionType.UPLOAD}),
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
            human_present=False  # No human!
        )

        result = decide_readiness(context)
        assert result.decision == ReadinessDecision.BLOCK

    def test_high_risk_with_human_allows(self):
        """HIGH risk with human is ALLOW."""
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
            action_type=PlannedActionType.UPLOAD,
            parameters={"file": "/path/to/file"},
            risk_level=PlanRiskLevel.HIGH
        )

        plan = ExecutionPlan(plan_id="PLAN-001", steps=(step,))
        intent = OrchestrationIntent(
            intent_id="INTENT-001",
            execution_plan=plan,
            capability_snapshot=frozenset({PlannedActionType.UPLOAD}),
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
            human_present=True  # Human present!
        )

        result = decide_readiness(context)
        assert result.decision == ReadinessDecision.ALLOW

    def test_low_risk_no_human_allows(self):
        """LOW risk without human is ALLOW."""
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
            human_present=False  # No human, but LOW risk
        )

        result = decide_readiness(context)
        assert result.decision == ReadinessDecision.ALLOW

    def test_medium_risk_no_human_allows(self):
        """MEDIUM risk without human is ALLOW."""
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
            action_type=PlannedActionType.NAVIGATE,
            parameters={"url": "https://example.com"},
            risk_level=PlanRiskLevel.MEDIUM
        )

        plan = ExecutionPlan(plan_id="PLAN-001", steps=(step,))
        intent = OrchestrationIntent(
            intent_id="INTENT-001",
            execution_plan=plan,
            capability_snapshot=frozenset({PlannedActionType.NAVIGATE}),
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
            human_present=False  # No human, but MEDIUM risk
        )

        result = decide_readiness(context)
        assert result.decision == ReadinessDecision.ALLOW
