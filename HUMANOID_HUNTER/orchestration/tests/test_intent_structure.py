"""
Tests for Phase-25 Intent Structure.

Tests:
- OrchestrationIntent frozen
- OrchestrationContext frozen
- OrchestrationResult frozen
- State transitions
"""
import pytest


class TestOrchestrationIntentStructure:
    """Test OrchestrationIntent structure."""

    def test_intent_creation(self):
        """OrchestrationIntent can be created."""
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

        intent = OrchestrationIntent(
            intent_id="INTENT-001",
            execution_plan=plan,
            capability_snapshot=frozenset(),
            evidence_requirements=frozenset(),
            created_at="2026-01-25T17:39:00-05:00",
            state=OrchestrationIntentState.DRAFT
        )

        assert intent.intent_id == "INTENT-001"
        assert intent.state == OrchestrationIntentState.DRAFT

    def test_intent_frozen(self):
        """OrchestrationIntent is frozen."""
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

        intent = OrchestrationIntent(
            intent_id="INTENT-001",
            execution_plan=plan,
            capability_snapshot=frozenset(),
            evidence_requirements=frozenset(),
            created_at="2026-01-25T17:39:00-05:00",
            state=OrchestrationIntentState.DRAFT
        )

        with pytest.raises(Exception):
            intent.state = OrchestrationIntentState.SEALED


class TestOrchestrationContextStructure:
    """Test OrchestrationContext structure."""

    def test_context_creation(self):
        """OrchestrationContext can be created."""
        from HUMANOID_HUNTER.orchestration.orchestration_context import (
            OrchestrationContext
        )
        from HUMANOID_HUNTER.planning import PlanValidationResult, PlanValidationDecision, PlanRiskLevel

        result = PlanValidationResult(
            decision=PlanValidationDecision.ACCEPT,
            max_risk=PlanRiskLevel.LOW,
            reason="Valid"
        )

        context = OrchestrationContext(
            plan_validation_result=result,
            human_present=True,
            prior_decisions=()
        )

        assert context.human_present is True
        assert context.prior_decisions == ()

    def test_context_frozen(self):
        """OrchestrationContext is frozen."""
        from HUMANOID_HUNTER.orchestration.orchestration_context import (
            OrchestrationContext
        )
        from HUMANOID_HUNTER.planning import PlanValidationResult, PlanValidationDecision, PlanRiskLevel

        result = PlanValidationResult(
            decision=PlanValidationDecision.ACCEPT,
            max_risk=PlanRiskLevel.LOW,
            reason="Valid"
        )

        context = OrchestrationContext(
            plan_validation_result=result,
            human_present=True,
            prior_decisions=()
        )

        with pytest.raises(Exception):
            context.human_present = False


class TestOrchestrationResultStructure:
    """Test OrchestrationResult structure."""

    def test_result_creation(self):
        """OrchestrationResult can be created."""
        from HUMANOID_HUNTER.orchestration.orchestration_context import (
            OrchestrationResult
        )
        from HUMANOID_HUNTER.orchestration.orchestration_types import (
            OrchestrationDecision
        )

        result = OrchestrationResult(
            decision=OrchestrationDecision.ACCEPT,
            reason="Valid orchestration"
        )

        assert result.decision == OrchestrationDecision.ACCEPT

    def test_result_frozen(self):
        """OrchestrationResult is frozen."""
        from HUMANOID_HUNTER.orchestration.orchestration_context import (
            OrchestrationResult
        )
        from HUMANOID_HUNTER.orchestration.orchestration_types import (
            OrchestrationDecision
        )

        result = OrchestrationResult(
            decision=OrchestrationDecision.ACCEPT,
            reason="Valid orchestration"
        )

        with pytest.raises(Exception):
            result.decision = OrchestrationDecision.REJECT


class TestEnumClosure:
    """Test enum closure."""

    def test_intent_state_has_three_members(self):
        """OrchestrationIntentState has exactly 3 members."""
        from HUMANOID_HUNTER.orchestration.orchestration_types import (
            OrchestrationIntentState
        )
        assert len(OrchestrationIntentState) == 3

    def test_decision_has_two_members(self):
        """OrchestrationDecision has exactly 2 members."""
        from HUMANOID_HUNTER.orchestration.orchestration_types import (
            OrchestrationDecision
        )
        assert len(OrchestrationDecision) == 2
