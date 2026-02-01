"""
Tests for Phase-24 Plan Capabilities Validation.

Tests:
- validate_plan_capabilities for allowed/forbidden actions
- Actions not in allowed set → REJECT
"""
import pytest


class TestValidatePlanCapabilities:
    """Test plan capabilities validation."""

    def test_all_allowed_actions_returns_true(self):
        """All actions in allowed set returns True."""
        from HUMANOID_HUNTER.planning.planning_engine import validate_plan_capabilities
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

        allowed = frozenset({PlannedActionType.CLICK, PlannedActionType.TYPE})
        assert validate_plan_capabilities(plan, allowed) is True

    def test_forbidden_action_returns_false(self):
        """Action not in allowed set returns False."""
        from HUMANOID_HUNTER.planning.planning_engine import validate_plan_capabilities
        from HUMANOID_HUNTER.planning.planning_context import ActionPlanStep, ExecutionPlan
        from HUMANOID_HUNTER.planning.planning_types import PlannedActionType, PlanRiskLevel

        step = ActionPlanStep(
            step_id="STEP-001",
            action_type=PlannedActionType.UPLOAD,  # Not in allowed!
            parameters={"file": "/path/to/file"},
            risk_level=PlanRiskLevel.HIGH
        )

        plan = ExecutionPlan(
            plan_id="PLAN-001",
            steps=(step,)
        )

        allowed = frozenset({PlannedActionType.CLICK, PlannedActionType.TYPE})  # No UPLOAD!
        assert validate_plan_capabilities(plan, allowed) is False

    def test_empty_allowed_set_returns_false(self):
        """Empty allowed set returns False."""
        from HUMANOID_HUNTER.planning.planning_engine import validate_plan_capabilities
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

        allowed = frozenset()  # Empty!
        assert validate_plan_capabilities(plan, allowed) is False

    def test_partial_actions_forbidden_returns_false(self):
        """Plan with some forbidden actions returns False."""
        from HUMANOID_HUNTER.planning.planning_engine import validate_plan_capabilities
        from HUMANOID_HUNTER.planning.planning_context import ActionPlanStep, ExecutionPlan
        from HUMANOID_HUNTER.planning.planning_types import PlannedActionType, PlanRiskLevel

        step1 = ActionPlanStep(
            step_id="STEP-001",
            action_type=PlannedActionType.CLICK,  # Allowed
            parameters={"selector": "#submit"},
            risk_level=PlanRiskLevel.LOW
        )
        step2 = ActionPlanStep(
            step_id="STEP-002",
            action_type=PlannedActionType.UPLOAD,  # NOT allowed
            parameters={"file": "/path/to/file"},
            risk_level=PlanRiskLevel.HIGH
        )

        plan = ExecutionPlan(
            plan_id="PLAN-001",
            steps=(step1, step2)
        )

        allowed = frozenset({PlannedActionType.CLICK, PlannedActionType.TYPE})
        assert validate_plan_capabilities(plan, allowed) is False

    def test_all_actions_in_allowed_set_returns_true(self):
        """Plan with all actions in allowed set returns True."""
        from HUMANOID_HUNTER.planning.planning_engine import validate_plan_capabilities
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
        step3 = ActionPlanStep(
            step_id="STEP-003",
            action_type=PlannedActionType.TYPE,
            parameters={"selector": "#input", "text": "hello"},
            risk_level=PlanRiskLevel.LOW
        )

        plan = ExecutionPlan(
            plan_id="PLAN-001",
            steps=(step1, step2, step3)
        )

        allowed = frozenset({
            PlannedActionType.NAVIGATE,
            PlannedActionType.CLICK,
            PlannedActionType.TYPE
        })
        assert validate_plan_capabilities(plan, allowed) is True

    def test_empty_plan_capabilities_returns_true(self):
        """Empty plan is trivially valid for capabilities."""
        from HUMANOID_HUNTER.planning.planning_engine import validate_plan_capabilities
        from HUMANOID_HUNTER.planning.planning_context import ExecutionPlan
        from HUMANOID_HUNTER.planning.planning_types import PlannedActionType

        plan = ExecutionPlan(
            plan_id="PLAN-001",
            steps=()  # Empty!
        )

        # Even with allowed set, empty plan is valid for capabilities
        allowed = frozenset({PlannedActionType.CLICK})
        assert validate_plan_capabilities(plan, allowed) is True
