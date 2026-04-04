"""
Tests for Phase-25 Deny-By-Default.

Tests:
- decide_orchestration rejects unclear inputs
- decide_orchestration rejects missing human
- decide_orchestration rejects missing evidence requirements
"""
import pytest


class TestDecideOrchestration:
    """Test decide_orchestration function."""

    def test_valid_intent_accepts(self):
        """Valid sealed intent with human is ACCEPT."""
        from HUMANOID_HUNTER.orchestration.orchestration_engine import (
            bind_plan_to_intent, seal_orchestration_intent, decide_orchestration
        )
        from HUMANOID_HUNTER.orchestration.orchestration_context import (
            OrchestrationContext
        )
        from HUMANOID_HUNTER.orchestration.orchestration_types import (
            OrchestrationDecision
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

        context = OrchestrationContext(
            plan_validation_result=validation_result,
            human_present=True,
            prior_decisions=()
        )

        result = decide_orchestration(sealed, context)
        assert result.decision == OrchestrationDecision.ACCEPT

    def test_draft_intent_rejects(self):
        """Unsealed (DRAFT) intent is REJECT."""
        from HUMANOID_HUNTER.orchestration.orchestration_engine import (
            bind_plan_to_intent, decide_orchestration
        )
        from HUMANOID_HUNTER.orchestration.orchestration_context import (
            OrchestrationContext
        )
        from HUMANOID_HUNTER.orchestration.orchestration_types import (
            OrchestrationDecision
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

        context = OrchestrationContext(
            plan_validation_result=validation_result,
            human_present=True,
            prior_decisions=()
        )

        # NOT sealed - should reject
        result = decide_orchestration(intent, context)
        assert result.decision == OrchestrationDecision.REJECT

    def test_high_risk_no_human_rejects(self):
        """HIGH risk without human is REJECT."""
        from HUMANOID_HUNTER.orchestration.orchestration_engine import (
            bind_plan_to_intent, seal_orchestration_intent, decide_orchestration
        )
        from HUMANOID_HUNTER.orchestration.orchestration_context import (
            OrchestrationContext
        )
        from HUMANOID_HUNTER.orchestration.orchestration_types import (
            OrchestrationDecision
        )
        from HUMANOID_HUNTER.planning import (
            ExecutionPlan, ActionPlanStep, PlanValidationResult,
            PlanValidationDecision, PlanRiskLevel, PlannedActionType
        )

        step = ActionPlanStep(
            step_id="STEP-001",
            action_type=PlannedActionType.UPLOAD,
            parameters={"file": "/path/to/file"},
            risk_level=PlanRiskLevel.HIGH
        )

        plan = ExecutionPlan(
            plan_id="PLAN-001",
            steps=(step,)
        )

        # Note: This was ACCEPTED with human present in Phase-24
        validation_result = PlanValidationResult(
            decision=PlanValidationDecision.ACCEPT,
            max_risk=PlanRiskLevel.HIGH,
            reason="Valid with human"
        )

        intent = bind_plan_to_intent(
            plan=plan,
            validation_result=validation_result,
            capability_snapshot=frozenset({PlannedActionType.UPLOAD}),
            evidence_requirements=frozenset({"screenshot"}),
            intent_id="INTENT-001",
            created_at="2026-01-25T17:39:00-05:00"
        )

        sealed = seal_orchestration_intent(intent)

        # Now at orchestration time, human is NOT present
        context = OrchestrationContext(
            plan_validation_result=validation_result,
            human_present=False,  # No human!
            prior_decisions=()
        )

        result = decide_orchestration(sealed, context)
        assert result.decision == OrchestrationDecision.REJECT

    def test_empty_evidence_requirements_rejects(self):
        """Empty evidence requirements is REJECT."""
        from HUMANOID_HUNTER.orchestration.orchestration_engine import (
            bind_plan_to_intent, seal_orchestration_intent, decide_orchestration
        )
        from HUMANOID_HUNTER.orchestration.orchestration_context import (
            OrchestrationContext
        )
        from HUMANOID_HUNTER.orchestration.orchestration_types import (
            OrchestrationDecision
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
            evidence_requirements=frozenset(),  # Empty!
            intent_id="INTENT-001",
            created_at="2026-01-25T17:39:00-05:00"
        )

        sealed = seal_orchestration_intent(intent)

        context = OrchestrationContext(
            plan_validation_result=validation_result,
            human_present=True,
            prior_decisions=()
        )

        result = decide_orchestration(sealed, context)
        assert result.decision == OrchestrationDecision.REJECT


class TestRejectionReasons:
    """Test that rejection includes reasons."""

    def test_reject_has_reason(self):
        """REJECT decisions have non-empty reason."""
        from HUMANOID_HUNTER.orchestration.orchestration_engine import (
            bind_plan_to_intent, decide_orchestration
        )
        from HUMANOID_HUNTER.orchestration.orchestration_context import (
            OrchestrationContext
        )
        from HUMANOID_HUNTER.orchestration.orchestration_types import (
            OrchestrationDecision
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

        context = OrchestrationContext(
            plan_validation_result=validation_result,
            human_present=True,
            prior_decisions=()
        )

        # DRAFT intent should be rejected with reason
        result = decide_orchestration(intent, context)
        assert result.decision == OrchestrationDecision.REJECT
        assert len(result.reason) > 0


class TestNoneInputHandling:
    """Test None input handling."""

    def test_none_intent_rejects(self):
        """None intent is REJECT."""
        from HUMANOID_HUNTER.orchestration.orchestration_engine import decide_orchestration
        from HUMANOID_HUNTER.orchestration.orchestration_context import OrchestrationContext
        from HUMANOID_HUNTER.orchestration.orchestration_types import OrchestrationDecision
        from HUMANOID_HUNTER.planning import (
            PlanValidationResult, PlanValidationDecision, PlanRiskLevel
        )

        validation_result = PlanValidationResult(
            decision=PlanValidationDecision.ACCEPT,
            max_risk=PlanRiskLevel.LOW,
            reason="Valid"
        )

        context = OrchestrationContext(
            plan_validation_result=validation_result,
            human_present=True,
            prior_decisions=()
        )

        result = decide_orchestration(None, context)
        assert result.decision == OrchestrationDecision.REJECT
