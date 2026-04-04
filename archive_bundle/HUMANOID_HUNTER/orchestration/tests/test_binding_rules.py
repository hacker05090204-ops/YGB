"""
Tests for Phase-25 Binding Rules.

Tests:
- bind_plan_to_intent accepts valid plans
- bind_plan_to_intent rejects invalid plans
- seal_orchestration_intent seals intent
- sealed intent cannot be modified
"""
import pytest


class TestBindPlanToIntent:
    """Test bind_plan_to_intent function."""

    def test_bind_accepted_plan_succeeds(self):
        """Bind ACCEPTED plan creates DRAFT intent."""
        from HUMANOID_HUNTER.orchestration.orchestration_engine import (
            bind_plan_to_intent
        )
        from HUMANOID_HUNTER.orchestration.orchestration_types import (
            OrchestrationIntentState
        )
        from HUMANOID_HUNTER.planning import (
            ExecutionPlan, ActionPlanStep, PlanValidationResult,
            PlanValidationDecision, PlanRiskLevel, PlannedActionType
        )

        step = ActionPlanStep(
            step_id="STEP-001",
            action_type=PlannedActionType.CLICK,
            parameters={"selector": "#submit"},
            risk_level=PlanRiskLevel.LOW
        )

        plan = ExecutionPlan(
            plan_id="PLAN-001",
            steps=(step,)
        )

        validation_result = PlanValidationResult(
            decision=PlanValidationDecision.ACCEPT,
            max_risk=PlanRiskLevel.LOW,
            reason="Valid"
        )

        intent = bind_plan_to_intent(
            plan=plan,
            validation_result=validation_result,
            capability_snapshot=frozenset({PlannedActionType.CLICK}),
            evidence_requirements=frozenset({"screenshot", "dom_hash"}),
            intent_id="INTENT-001",
            created_at="2026-01-25T17:39:00-05:00"
        )

        assert intent is not None
        assert intent.state == OrchestrationIntentState.DRAFT

    def test_bind_rejected_plan_returns_none(self):
        """Bind REJECTED plan returns None."""
        from HUMANOID_HUNTER.orchestration.orchestration_engine import (
            bind_plan_to_intent
        )
        from HUMANOID_HUNTER.planning import (
            ExecutionPlan, PlanValidationResult,
            PlanValidationDecision, PlanRiskLevel, PlannedActionType
        )

        plan = ExecutionPlan(
            plan_id="PLAN-001",
            steps=()
        )

        validation_result = PlanValidationResult(
            decision=PlanValidationDecision.REJECT,
            max_risk=PlanRiskLevel.LOW,
            reason="Invalid"
        )

        intent = bind_plan_to_intent(
            plan=plan,
            validation_result=validation_result,
            capability_snapshot=frozenset({PlannedActionType.CLICK}),
            evidence_requirements=frozenset(),
            intent_id="INTENT-001",
            created_at="2026-01-25T17:39:00-05:00"
        )

        assert intent is None

    def test_bind_requires_human_plan_returns_none(self):
        """Bind REQUIRES_HUMAN plan returns None."""
        from HUMANOID_HUNTER.orchestration.orchestration_engine import (
            bind_plan_to_intent
        )
        from HUMANOID_HUNTER.planning import (
            ExecutionPlan, PlanValidationResult,
            PlanValidationDecision, PlanRiskLevel, PlannedActionType
        )

        plan = ExecutionPlan(
            plan_id="PLAN-001",
            steps=()
        )

        validation_result = PlanValidationResult(
            decision=PlanValidationDecision.REQUIRES_HUMAN,
            max_risk=PlanRiskLevel.HIGH,
            reason="Needs human"
        )

        intent = bind_plan_to_intent(
            plan=plan,
            validation_result=validation_result,
            capability_snapshot=frozenset({PlannedActionType.CLICK}),
            evidence_requirements=frozenset(),
            intent_id="INTENT-001",
            created_at="2026-01-25T17:39:00-05:00"
        )

        assert intent is None


class TestSealOrchestrationIntent:
    """Test seal_orchestration_intent function."""

    def test_seal_draft_intent_succeeds(self):
        """Sealing DRAFT intent creates SEALED intent."""
        from HUMANOID_HUNTER.orchestration.orchestration_engine import (
            bind_plan_to_intent, seal_orchestration_intent
        )
        from HUMANOID_HUNTER.orchestration.orchestration_types import (
            OrchestrationIntentState
        )
        from HUMANOID_HUNTER.planning import (
            ExecutionPlan, ActionPlanStep, PlanValidationResult,
            PlanValidationDecision, PlanRiskLevel, PlannedActionType
        )

        step = ActionPlanStep(
            step_id="STEP-001",
            action_type=PlannedActionType.CLICK,
            parameters={"selector": "#submit"},
            risk_level=PlanRiskLevel.LOW
        )

        plan = ExecutionPlan(
            plan_id="PLAN-001",
            steps=(step,)
        )

        validation_result = PlanValidationResult(
            decision=PlanValidationDecision.ACCEPT,
            max_risk=PlanRiskLevel.LOW,
            reason="Valid"
        )

        intent = bind_plan_to_intent(
            plan=plan,
            validation_result=validation_result,
            capability_snapshot=frozenset({PlannedActionType.CLICK}),
            evidence_requirements=frozenset({"screenshot"}),
            intent_id="INTENT-001",
            created_at="2026-01-25T17:39:00-05:00"
        )

        sealed = seal_orchestration_intent(intent)
        assert sealed is not None
        assert sealed.state == OrchestrationIntentState.SEALED

    def test_seal_already_sealed_returns_same(self):
        """Sealing already SEALED intent returns same intent."""
        from HUMANOID_HUNTER.orchestration.orchestration_engine import (
            bind_plan_to_intent, seal_orchestration_intent
        )
        from HUMANOID_HUNTER.orchestration.orchestration_types import (
            OrchestrationIntentState
        )
        from HUMANOID_HUNTER.planning import (
            ExecutionPlan, ActionPlanStep, PlanValidationResult,
            PlanValidationDecision, PlanRiskLevel, PlannedActionType
        )

        step = ActionPlanStep(
            step_id="STEP-001",
            action_type=PlannedActionType.CLICK,
            parameters={"selector": "#submit"},
            risk_level=PlanRiskLevel.LOW
        )

        plan = ExecutionPlan(
            plan_id="PLAN-001",
            steps=(step,)
        )

        validation_result = PlanValidationResult(
            decision=PlanValidationDecision.ACCEPT,
            max_risk=PlanRiskLevel.LOW,
            reason="Valid"
        )

        intent = bind_plan_to_intent(
            plan=plan,
            validation_result=validation_result,
            capability_snapshot=frozenset({PlannedActionType.CLICK}),
            evidence_requirements=frozenset({"screenshot"}),
            intent_id="INTENT-001",
            created_at="2026-01-25T17:39:00-05:00"
        )

        sealed1 = seal_orchestration_intent(intent)
        sealed2 = seal_orchestration_intent(sealed1)

        assert sealed2.state == OrchestrationIntentState.SEALED
        assert sealed1.intent_id == sealed2.intent_id

    def test_seal_rejected_intent_returns_none(self):
        """Sealing REJECTED intent returns None."""
        from HUMANOID_HUNTER.orchestration.orchestration_engine import (
            seal_orchestration_intent
        )
        from HUMANOID_HUNTER.orchestration.orchestration_context import (
            OrchestrationIntent
        )
        from HUMANOID_HUNTER.orchestration.orchestration_types import (
            OrchestrationIntentState
        )
        from HUMANOID_HUNTER.planning import ExecutionPlan

        plan = ExecutionPlan(
            plan_id="PLAN-001",
            steps=()
        )

        # Create a rejected intent directly
        intent = OrchestrationIntent(
            intent_id="INTENT-001",
            execution_plan=plan,
            capability_snapshot=frozenset(),
            evidence_requirements=frozenset(),
            created_at="2026-01-25T17:39:00-05:00",
            state=OrchestrationIntentState.REJECTED
        )

        sealed = seal_orchestration_intent(intent)
        assert sealed is None

    def test_seal_none_intent_returns_none(self):
        """Sealing None intent returns None."""
        from HUMANOID_HUNTER.orchestration.orchestration_engine import (
            seal_orchestration_intent
        )

        sealed = seal_orchestration_intent(None)
        assert sealed is None
