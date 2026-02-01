"""
Tests for Phase-26 Readiness Structure.

Tests:
- ReadinessContext frozen
- ReadinessResult frozen
- Enum closures
"""
import pytest


class TestReadinessContextStructure:
    """Test ReadinessContext structure."""

    def test_context_creation(self):
        """ReadinessContext can be created."""
        from HUMANOID_HUNTER.readiness.readiness_context import ReadinessContext
        from HUMANOID_HUNTER.readiness.readiness_types import ExecutionReadinessState
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
            evidence_verification_passed=True,
            human_present=True
        )

        assert context.orchestration_intent == intent
        assert context.human_present is True

    def test_context_frozen(self):
        """ReadinessContext is frozen."""
        from HUMANOID_HUNTER.readiness.readiness_context import ReadinessContext
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
            evidence_verification_passed=True,
            human_present=True
        )

        with pytest.raises(Exception):
            context.human_present = False


class TestReadinessResultStructure:
    """Test ReadinessResult structure."""

    def test_result_creation(self):
        """ReadinessResult can be created."""
        from HUMANOID_HUNTER.readiness.readiness_context import ReadinessResult
        from HUMANOID_HUNTER.readiness.readiness_types import (
            ReadinessDecision, ExecutionReadinessState
        )

        result = ReadinessResult(
            decision=ReadinessDecision.ALLOW,
            state=ExecutionReadinessState.READY,
            reason="All checks passed"
        )

        assert result.decision == ReadinessDecision.ALLOW
        assert result.state == ExecutionReadinessState.READY

    def test_result_frozen(self):
        """ReadinessResult is frozen."""
        from HUMANOID_HUNTER.readiness.readiness_context import ReadinessResult
        from HUMANOID_HUNTER.readiness.readiness_types import (
            ReadinessDecision, ExecutionReadinessState
        )

        result = ReadinessResult(
            decision=ReadinessDecision.ALLOW,
            state=ExecutionReadinessState.READY,
            reason="All checks passed"
        )

        with pytest.raises(Exception):
            result.decision = ReadinessDecision.BLOCK


class TestEnumClosure:
    """Test enum closure."""

    def test_readiness_state_has_two_members(self):
        """ExecutionReadinessState has exactly 2 members."""
        from HUMANOID_HUNTER.readiness.readiness_types import ExecutionReadinessState
        assert len(ExecutionReadinessState) == 2

    def test_decision_has_two_members(self):
        """ReadinessDecision has exactly 2 members."""
        from HUMANOID_HUNTER.readiness.readiness_types import ReadinessDecision
        assert len(ReadinessDecision) == 2
