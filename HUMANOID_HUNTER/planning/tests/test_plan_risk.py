"""
Tests for Phase-24 Plan Risk Validation.

Tests:
- validate_plan_risk returns correct max risk
- CRITICAL → REJECT
- HIGH → REQUIRES_HUMAN (if no human present)
- MEDIUM/LOW → ACCEPT
"""
import pytest


class TestValidatePlanRisk:
    """Test plan risk validation."""

    def test_single_low_risk_returns_low(self):
        """Single LOW risk step returns LOW."""
        from HUMANOID_HUNTER.planning.planning_engine import validate_plan_risk
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

        assert validate_plan_risk(plan) == PlanRiskLevel.LOW

    def test_single_medium_risk_returns_medium(self):
        """Single MEDIUM risk step returns MEDIUM."""
        from HUMANOID_HUNTER.planning.planning_engine import validate_plan_risk
        from HUMANOID_HUNTER.planning.planning_context import ActionPlanStep, ExecutionPlan
        from HUMANOID_HUNTER.planning.planning_types import PlannedActionType, PlanRiskLevel

        step = ActionPlanStep(
            step_id="STEP-001",
            action_type=PlannedActionType.NAVIGATE,
            parameters={"url": "https://example.com"},
            risk_level=PlanRiskLevel.MEDIUM
        )

        plan = ExecutionPlan(
            plan_id="PLAN-001",
            steps=(step,)
        )

        assert validate_plan_risk(plan) == PlanRiskLevel.MEDIUM

    def test_single_high_risk_returns_high(self):
        """Single HIGH risk step returns HIGH."""
        from HUMANOID_HUNTER.planning.planning_engine import validate_plan_risk
        from HUMANOID_HUNTER.planning.planning_context import ActionPlanStep, ExecutionPlan
        from HUMANOID_HUNTER.planning.planning_types import PlannedActionType, PlanRiskLevel

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

        assert validate_plan_risk(plan) == PlanRiskLevel.HIGH

    def test_single_critical_risk_returns_critical(self):
        """Single CRITICAL risk step returns CRITICAL."""
        from HUMANOID_HUNTER.planning.planning_engine import validate_plan_risk
        from HUMANOID_HUNTER.planning.planning_context import ActionPlanStep, ExecutionPlan
        from HUMANOID_HUNTER.planning.planning_types import PlannedActionType, PlanRiskLevel

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

        assert validate_plan_risk(plan) == PlanRiskLevel.CRITICAL

    def test_mixed_risk_returns_highest(self):
        """Mixed risk levels returns highest."""
        from HUMANOID_HUNTER.planning.planning_engine import validate_plan_risk
        from HUMANOID_HUNTER.planning.planning_context import ActionPlanStep, ExecutionPlan
        from HUMANOID_HUNTER.planning.planning_types import PlannedActionType, PlanRiskLevel

        step1 = ActionPlanStep(
            step_id="STEP-001",
            action_type=PlannedActionType.CLICK,
            parameters={"selector": "#submit"},
            risk_level=PlanRiskLevel.LOW
        )
        step2 = ActionPlanStep(
            step_id="STEP-002",
            action_type=PlannedActionType.NAVIGATE,
            parameters={"url": "https://example.com"},
            risk_level=PlanRiskLevel.MEDIUM
        )
        step3 = ActionPlanStep(
            step_id="STEP-003",
            action_type=PlannedActionType.UPLOAD,
            parameters={"file": "/path/to/file"},
            risk_level=PlanRiskLevel.HIGH
        )

        plan = ExecutionPlan(
            plan_id="PLAN-001",
            steps=(step1, step2, step3)
        )

        assert validate_plan_risk(plan) == PlanRiskLevel.HIGH

    def test_empty_plan_risk_returns_low(self):
        """Empty plan returns LOW risk."""
        from HUMANOID_HUNTER.planning.planning_engine import validate_plan_risk
        from HUMANOID_HUNTER.planning.planning_context import ExecutionPlan
        from HUMANOID_HUNTER.planning.planning_types import PlanRiskLevel

        plan = ExecutionPlan(
            plan_id="PLAN-001",
            steps=()  # Empty!
        )

        # Empty plan has no risk
        assert validate_plan_risk(plan) == PlanRiskLevel.LOW


class TestDecidePlanAcceptance:
    """Test plan acceptance decisions."""

    def test_low_risk_accepts(self):
        """LOW risk plan is ACCEPT."""
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
            plan_id="PLAN-001",
            steps=(step,)
        )

        context = PlanValidationContext(
            plan=plan,
            allowed_capabilities=frozenset({PlannedActionType.CLICK}),
            human_present=False
        )

        result = decide_plan_acceptance(context)
        assert result.decision == PlanValidationDecision.ACCEPT

    def test_medium_risk_accepts(self):
        """MEDIUM risk plan is ACCEPT."""
        from HUMANOID_HUNTER.planning.planning_engine import decide_plan_acceptance
        from HUMANOID_HUNTER.planning.planning_context import (
            ActionPlanStep, ExecutionPlan, PlanValidationContext
        )
        from HUMANOID_HUNTER.planning.planning_types import (
            PlannedActionType, PlanRiskLevel, PlanValidationDecision
        )

        step = ActionPlanStep(
            step_id="STEP-001",
            action_type=PlannedActionType.NAVIGATE,
            parameters={"url": "https://example.com"},
            risk_level=PlanRiskLevel.MEDIUM
        )

        plan = ExecutionPlan(
            plan_id="PLAN-001",
            steps=(step,)
        )

        context = PlanValidationContext(
            plan=plan,
            allowed_capabilities=frozenset({PlannedActionType.NAVIGATE}),
            human_present=False
        )

        result = decide_plan_acceptance(context)
        assert result.decision == PlanValidationDecision.ACCEPT

    def test_high_risk_no_human_requires_human(self):
        """HIGH risk with no human present is REQUIRES_HUMAN."""
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
            parameters={"file": "/path/to/file"},
            risk_level=PlanRiskLevel.HIGH
        )

        plan = ExecutionPlan(
            plan_id="PLAN-001",
            steps=(step,)
        )

        context = PlanValidationContext(
            plan=plan,
            allowed_capabilities=frozenset({PlannedActionType.UPLOAD}),
            human_present=False  # No human!
        )

        result = decide_plan_acceptance(context)
        assert result.decision == PlanValidationDecision.REQUIRES_HUMAN

    def test_high_risk_with_human_accepts(self):
        """HIGH risk with human present is ACCEPT."""
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
            parameters={"file": "/path/to/file"},
            risk_level=PlanRiskLevel.HIGH
        )

        plan = ExecutionPlan(
            plan_id="PLAN-001",
            steps=(step,)
        )

        context = PlanValidationContext(
            plan=plan,
            allowed_capabilities=frozenset({PlannedActionType.UPLOAD}),
            human_present=True  # Human present!
        )

        result = decide_plan_acceptance(context)
        assert result.decision == PlanValidationDecision.ACCEPT

    def test_critical_risk_rejects_always(self):
        """CRITICAL risk is REJECT regardless of human presence."""
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

        # Even with human present, CRITICAL → REJECT
        context = PlanValidationContext(
            plan=plan,
            allowed_capabilities=frozenset({PlannedActionType.UPLOAD}),
            human_present=True
        )

        result = decide_plan_acceptance(context)
        assert result.decision == PlanValidationDecision.REJECT


class TestRiskLevelOrdering:
    """Test risk level ordering."""

    def test_risk_level_ordering(self):
        """Risk levels are ordered LOW < MEDIUM < HIGH < CRITICAL."""
        from HUMANOID_HUNTER.planning.planning_types import PlanRiskLevel

        # Verify all risk levels exist
        assert PlanRiskLevel.LOW is not None
        assert PlanRiskLevel.MEDIUM is not None
        assert PlanRiskLevel.HIGH is not None
        assert PlanRiskLevel.CRITICAL is not None

        # Verify ordering by value
        assert PlanRiskLevel.LOW.value < PlanRiskLevel.MEDIUM.value
        assert PlanRiskLevel.MEDIUM.value < PlanRiskLevel.HIGH.value
        assert PlanRiskLevel.HIGH.value < PlanRiskLevel.CRITICAL.value
