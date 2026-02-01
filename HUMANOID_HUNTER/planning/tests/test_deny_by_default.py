"""
Tests for Phase-24 Deny-By-Default.

Tests:
- Unknown input → REJECT
- Invalid structure → REJECT
- Missing capabilities → REJECT
- Default behavior is REJECT
"""
import pytest


class TestDenyByDefault:
    """Test deny-by-default behavior."""

    def test_empty_plan_rejected(self):
        """Empty plan is rejected."""
        from HUMANOID_HUNTER.planning.planning_engine import decide_plan_acceptance
        from HUMANOID_HUNTER.planning.planning_context import (
            ExecutionPlan, PlanValidationContext
        )
        from HUMANOID_HUNTER.planning.planning_types import (
            PlannedActionType, PlanValidationDecision
        )

        plan = ExecutionPlan(
            plan_id="PLAN-001",
            steps=()  # Empty!
        )

        context = PlanValidationContext(
            plan=plan,
            allowed_capabilities=frozenset({PlannedActionType.CLICK}),
            human_present=True
        )

        result = decide_plan_acceptance(context)
        assert result.decision == PlanValidationDecision.REJECT

    def test_empty_plan_id_rejected(self):
        """Empty plan_id is rejected."""
        from HUMANOID_HUNTER.planning.planning_engine import decide_plan_acceptance
        from HUMANOID_HUNTER.planning.planning_context import (
            ActionPlanStep, ExecutionPlan, PlanValidationContext
        )
        from HUMANOID_HUNTER.planning.planning_types import (
            PlannedActionType, PlanRiskLevel, PlanValidationDecision
        )

        step = ActionPlanStep(
            step_id="STEP-001",
            action_type=PlannedActionType.CLICK,
            parameters={"selector": "#submit"},
            risk_level=PlanRiskLevel.LOW
        )

        plan = ExecutionPlan(
            plan_id="",  # Empty!
            steps=(step,)
        )

        context = PlanValidationContext(
            plan=plan,
            allowed_capabilities=frozenset({PlannedActionType.CLICK}),
            human_present=True
        )

        result = decide_plan_acceptance(context)
        assert result.decision == PlanValidationDecision.REJECT

    def test_duplicate_step_ids_rejected(self):
        """Duplicate step IDs rejected."""
        from HUMANOID_HUNTER.planning.planning_engine import decide_plan_acceptance
        from HUMANOID_HUNTER.planning.planning_context import (
            ActionPlanStep, ExecutionPlan, PlanValidationContext
        )
        from HUMANOID_HUNTER.planning.planning_types import (
            PlannedActionType, PlanRiskLevel, PlanValidationDecision
        )

        step1 = ActionPlanStep(
            step_id="STEP-001",  # Duplicate!
            action_type=PlannedActionType.CLICK,
            parameters={"selector": "#submit"},
            risk_level=PlanRiskLevel.LOW
        )
        step2 = ActionPlanStep(
            step_id="STEP-001",  # Duplicate!
            action_type=PlannedActionType.TYPE,
            parameters={"selector": "#input", "text": "hello"},
            risk_level=PlanRiskLevel.LOW
        )

        plan = ExecutionPlan(
            plan_id="PLAN-001",
            steps=(step1, step2)
        )

        context = PlanValidationContext(
            plan=plan,
            allowed_capabilities=frozenset({PlannedActionType.CLICK, PlannedActionType.TYPE}),
            human_present=True
        )

        result = decide_plan_acceptance(context)
        assert result.decision == PlanValidationDecision.REJECT

    def test_forbidden_action_rejected(self):
        """Action not in allowed capabilities rejected."""
        from HUMANOID_HUNTER.planning.planning_engine import decide_plan_acceptance
        from HUMANOID_HUNTER.planning.planning_context import (
            ActionPlanStep, ExecutionPlan, PlanValidationContext
        )
        from HUMANOID_HUNTER.planning.planning_types import (
            PlannedActionType, PlanRiskLevel, PlanValidationDecision
        )

        step = ActionPlanStep(
            step_id="STEP-001",
            action_type=PlannedActionType.UPLOAD,  # Not allowed!
            parameters={"file": "/path/to/file"},
            risk_level=PlanRiskLevel.HIGH
        )

        plan = ExecutionPlan(
            plan_id="PLAN-001",
            steps=(step,)
        )

        context = PlanValidationContext(
            plan=plan,
            allowed_capabilities=frozenset({PlannedActionType.CLICK}),  # No UPLOAD!
            human_present=True
        )

        result = decide_plan_acceptance(context)
        assert result.decision == PlanValidationDecision.REJECT

    def test_critical_risk_rejected(self):
        """CRITICAL risk always rejected."""
        from HUMANOID_HUNTER.planning.planning_engine import decide_plan_acceptance
        from HUMANOID_HUNTER.planning.planning_context import (
            ActionPlanStep, ExecutionPlan, PlanValidationContext
        )
        from HUMANOID_HUNTER.planning.planning_types import (
            PlannedActionType, PlanRiskLevel, PlanValidationDecision
        )

        step = ActionPlanStep(
            step_id="STEP-001",
            action_type=PlannedActionType.UPLOAD,
            parameters={"file": "/path/to/critical"},
            risk_level=PlanRiskLevel.CRITICAL
        )

        plan = ExecutionPlan(
            plan_id="PLAN-001",
            steps=(step,)
        )

        context = PlanValidationContext(
            plan=plan,
            allowed_capabilities=frozenset({PlannedActionType.UPLOAD}),
            human_present=True  # Even with human!
        )

        result = decide_plan_acceptance(context)
        assert result.decision == PlanValidationDecision.REJECT


class TestEnumClosure:
    """Test enum closure."""

    def test_planned_action_type_has_seven_members(self):
        """PlannedActionType has exactly 7 members."""
        from HUMANOID_HUNTER.planning.planning_types import PlannedActionType
        assert len(PlannedActionType) == 7

    def test_plan_risk_level_has_four_members(self):
        """PlanRiskLevel has exactly 4 members."""
        from HUMANOID_HUNTER.planning.planning_types import PlanRiskLevel
        assert len(PlanRiskLevel) == 4

    def test_plan_validation_decision_has_three_members(self):
        """PlanValidationDecision has exactly 3 members."""
        from HUMANOID_HUNTER.planning.planning_types import PlanValidationDecision
        assert len(PlanValidationDecision) == 3


class TestRejectHasReason:
    """Test that REJECT decisions include reason."""

    def test_reject_has_non_empty_reason(self):
        """REJECT decisions have non-empty reason."""
        from HUMANOID_HUNTER.planning.planning_engine import decide_plan_acceptance
        from HUMANOID_HUNTER.planning.planning_context import (
            ExecutionPlan, PlanValidationContext
        )
        from HUMANOID_HUNTER.planning.planning_types import (
            PlannedActionType, PlanValidationDecision
        )

        plan = ExecutionPlan(
            plan_id="PLAN-001",
            steps=()  # Empty → REJECT
        )

        context = PlanValidationContext(
            plan=plan,
            allowed_capabilities=frozenset({PlannedActionType.CLICK}),
            human_present=True
        )

        result = decide_plan_acceptance(context)
        assert result.decision == PlanValidationDecision.REJECT
        assert result.reason != ""
        assert len(result.reason) > 0
