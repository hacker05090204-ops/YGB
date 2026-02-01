"""
Tests for Phase-26 Dependency Blocking.

Tests:
- validate_readiness_inputs blocks on missing dependencies
- Each missing dependency results in BLOCK
"""
import pytest


class TestValidateReadinessInputs:
    """Test validate_readiness_inputs function."""

    def test_all_valid_inputs_returns_true(self):
        """All valid inputs returns True."""
        from HUMANOID_HUNTER.readiness.readiness_engine import validate_readiness_inputs
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

        assert validate_readiness_inputs(context) is True

    def test_none_intent_returns_false(self):
        """None intent returns False."""
        from HUMANOID_HUNTER.readiness.readiness_engine import validate_readiness_inputs
        from HUMANOID_HUNTER.readiness.readiness_context import ReadinessContext

        context = ReadinessContext(
            orchestration_intent=None,
            capability_result_accepted=True,
            sandbox_policy_allows=True,
            native_policy_accepts=True,
            evidence_verification_passed=True,
            human_present=True
        )

        assert validate_readiness_inputs(context) is False

    def test_capability_not_accepted_returns_false(self):
        """Capability not accepted returns False."""
        from HUMANOID_HUNTER.readiness.readiness_engine import validate_readiness_inputs
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
            capability_result_accepted=False,  # NOT accepted!
            sandbox_policy_allows=True,
            native_policy_accepts=True,
            evidence_verification_passed=True,
            human_present=True
        )

        assert validate_readiness_inputs(context) is False

    def test_sandbox_not_allowed_returns_false(self):
        """Sandbox not allowed returns False."""
        from HUMANOID_HUNTER.readiness.readiness_engine import validate_readiness_inputs
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
            sandbox_policy_allows=False,  # NOT allowed!
            native_policy_accepts=True,
            evidence_verification_passed=True,
            human_present=True
        )

        assert validate_readiness_inputs(context) is False

    def test_native_not_accepted_returns_false(self):
        """Native not accepted returns False."""
        from HUMANOID_HUNTER.readiness.readiness_engine import validate_readiness_inputs
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
            native_policy_accepts=False,  # NOT accepted!
            evidence_verification_passed=True,
            human_present=True
        )

        assert validate_readiness_inputs(context) is False

    def test_evidence_not_verified_returns_false(self):
        """Evidence not verified returns False."""
        from HUMANOID_HUNTER.readiness.readiness_engine import validate_readiness_inputs
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
            evidence_verification_passed=False,  # NOT passed!
            human_present=True
        )

        assert validate_readiness_inputs(context) is False
