"""
Tests for Phase-24 Plan Structure Validation.

Tests:
- validate_plan_structure for valid/invalid plans
- Empty steps rejection
- Duplicate step IDs rejection
- Unknown action rejection
"""
import pytest


class TestValidatePlanStructure:
    """Test plan structure validation."""

    def test_valid_structure_returns_true(self):
        """Valid structure returns True."""
        from HUMANOID_HUNTER.planning.planning_engine import validate_plan_structure
        from HUMANOID_HUNTER.planning.planning_context import ActionPlanStep, ExecutionPlan
        from HUMANOID_HUNTER.planning.planning_types import PlannedActionType, PlanRiskLevel

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

        assert validate_plan_structure(plan) is True

    def test_empty_steps_returns_false(self):
        """Empty steps returns False (REJECT)."""
        from HUMANOID_HUNTER.planning.planning_engine import validate_plan_structure
        from HUMANOID_HUNTER.planning.planning_context import ExecutionPlan

        plan = ExecutionPlan(
            plan_id="PLAN-001",
            steps=()  # Empty!
        )

        assert validate_plan_structure(plan) is False

    def test_empty_plan_id_returns_false(self):
        """Empty plan_id returns False (REJECT)."""
        from HUMANOID_HUNTER.planning.planning_engine import validate_plan_structure
        from HUMANOID_HUNTER.planning.planning_context import ActionPlanStep, ExecutionPlan
        from HUMANOID_HUNTER.planning.planning_types import PlannedActionType, PlanRiskLevel

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

        assert validate_plan_structure(plan) is False

    def test_duplicate_step_ids_returns_false(self):
        """Duplicate step IDs returns False (REJECT)."""
        from HUMANOID_HUNTER.planning.planning_engine import validate_plan_structure
        from HUMANOID_HUNTER.planning.planning_context import ActionPlanStep, ExecutionPlan
        from HUMANOID_HUNTER.planning.planning_types import PlannedActionType, PlanRiskLevel

        step1 = ActionPlanStep(
            step_id="STEP-001",  # Duplicate ID!
            action_type=PlannedActionType.CLICK,
            parameters={"selector": "#submit"},
            risk_level=PlanRiskLevel.LOW
        )
        step2 = ActionPlanStep(
            step_id="STEP-001",  # Duplicate ID!
            action_type=PlannedActionType.TYPE,
            parameters={"selector": "#input", "text": "hello"},
            risk_level=PlanRiskLevel.LOW
        )

        plan = ExecutionPlan(
            plan_id="PLAN-001",
            steps=(step1, step2)
        )

        assert validate_plan_structure(plan) is False

    def test_valid_multiple_steps_returns_true(self):
        """Valid plan with multiple steps returns True."""
        from HUMANOID_HUNTER.planning.planning_engine import validate_plan_structure
        from HUMANOID_HUNTER.planning.planning_context import ActionPlanStep, ExecutionPlan
        from HUMANOID_HUNTER.planning.planning_types import PlannedActionType, PlanRiskLevel

        step1 = ActionPlanStep(
            step_id="STEP-001",
            action_type=PlannedActionType.NAVIGATE,
            parameters={"url": "https://example.com"},
            risk_level=PlanRiskLevel.MEDIUM
        )
        step2 = ActionPlanStep(
            step_id="STEP-002",
            action_type=PlannedActionType.CLICK,
            parameters={"selector": "#submit"},
            risk_level=PlanRiskLevel.LOW
        )

        plan = ExecutionPlan(
            plan_id="PLAN-001",
            steps=(step1, step2)
        )

        assert validate_plan_structure(plan) is True


class TestDataclassFrozen:
    """Test dataclass immutability."""

    def test_action_plan_step_frozen(self):
        """ActionPlanStep is frozen."""
        from HUMANOID_HUNTER.planning.planning_context import ActionPlanStep
        from HUMANOID_HUNTER.planning.planning_types import PlannedActionType, PlanRiskLevel

        step = ActionPlanStep(
            step_id="STEP-001",
            action_type=PlannedActionType.CLICK,
            parameters={"selector": "#submit"},
            risk_level=PlanRiskLevel.LOW
        )

        with pytest.raises(Exception):
            step.step_id = "MODIFIED"

    def test_execution_plan_frozen(self):
        """ExecutionPlan is frozen."""
        from HUMANOID_HUNTER.planning.planning_context import ActionPlanStep, ExecutionPlan
        from HUMANOID_HUNTER.planning.planning_types import PlannedActionType, PlanRiskLevel

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

        with pytest.raises(Exception):
            plan.plan_id = "MODIFIED"

    def test_plan_validation_context_frozen(self):
        """PlanValidationContext is frozen."""
        from HUMANOID_HUNTER.planning.planning_context import (
            ActionPlanStep, ExecutionPlan, PlanValidationContext
        )
        from HUMANOID_HUNTER.planning.planning_types import PlannedActionType, PlanRiskLevel

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

        context = PlanValidationContext(
            plan=plan,
            allowed_capabilities=frozenset({PlannedActionType.CLICK}),
            human_present=False
        )

        with pytest.raises(Exception):
            context.human_present = True

    def test_plan_validation_result_frozen(self):
        """PlanValidationResult is frozen."""
        from HUMANOID_HUNTER.planning.planning_context import PlanValidationResult
        from HUMANOID_HUNTER.planning.planning_types import PlanValidationDecision, PlanRiskLevel

        result = PlanValidationResult(
            decision=PlanValidationDecision.ACCEPT,
            max_risk=PlanRiskLevel.LOW,
            reason="Valid plan"
        )

        with pytest.raises(Exception):
            result.decision = PlanValidationDecision.REJECT


class TestActionPlanStepHash:
    """Test ActionPlanStep hashing."""

    def test_action_plan_step_is_hashable(self):
        """ActionPlanStep can be used in sets and as dict keys."""
        from HUMANOID_HUNTER.planning.planning_context import ActionPlanStep
        from HUMANOID_HUNTER.planning.planning_types import PlannedActionType, PlanRiskLevel

        step = ActionPlanStep(
            step_id="STEP-001",
            action_type=PlannedActionType.CLICK,
            parameters={"selector": "#submit"},
            risk_level=PlanRiskLevel.LOW
        )

        # Should be hashable
        step_set = {step}
        assert step in step_set

    def test_action_plan_step_hash_consistency(self):
        """Same ActionPlanStep produces same hash."""
        from HUMANOID_HUNTER.planning.planning_context import ActionPlanStep
        from HUMANOID_HUNTER.planning.planning_types import PlannedActionType, PlanRiskLevel

        step1 = ActionPlanStep(
            step_id="STEP-001",
            action_type=PlannedActionType.CLICK,
            parameters={"selector": "#submit"},
            risk_level=PlanRiskLevel.LOW
        )
        step2 = ActionPlanStep(
            step_id="STEP-001",
            action_type=PlannedActionType.CLICK,
            parameters={"selector": "#submit"},
            risk_level=PlanRiskLevel.LOW
        )

        assert hash(step1) == hash(step2)

    def test_different_steps_different_hash(self):
        """Different ActionPlanSteps produce different hashes."""
        from HUMANOID_HUNTER.planning.planning_context import ActionPlanStep
        from HUMANOID_HUNTER.planning.planning_types import PlannedActionType, PlanRiskLevel

        step1 = ActionPlanStep(
            step_id="STEP-001",
            action_type=PlannedActionType.CLICK,
            parameters={"selector": "#submit"},
            risk_level=PlanRiskLevel.LOW
        )
        step2 = ActionPlanStep(
            step_id="STEP-002",
            action_type=PlannedActionType.TYPE,
            parameters={"selector": "#input", "text": "hello"},
            risk_level=PlanRiskLevel.LOW
        )

        assert hash(step1) != hash(step2)
