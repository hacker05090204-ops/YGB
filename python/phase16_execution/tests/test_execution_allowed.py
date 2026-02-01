"""
Tests for Phase-16 Execution Allowed.

Tests:
- Execution allowed when all conditions pass
- Human override for REVIEW_REQUIRED
"""
import pytest


class TestExecutionAllowed:
    """Test execution allowed conditions."""

    def test_all_conditions_pass_allowed(self):
        """All conditions pass → ALLOWED."""
        from python.phase16_execution.execution_context import ExecutionContext
        from python.phase16_execution.execution_engine import decide_execution
        from python.phase16_execution.execution_types import ExecutionPermission

        context = ExecutionContext(
            bug_id="BUG-001",
            target_id="TARGET-001",
            handoff_readiness="READY_FOR_BROWSER",
            handoff_can_proceed=True,
            handoff_is_blocked=False,
            handoff_human_presence="OPTIONAL",
            contract_is_valid=True,
            human_present=False,
            decision_timestamp="2026-01-25T06:15:00-05:00",
            human_override=False
        )

        decision = decide_execution(context)
        assert decision.permission == ExecutionPermission.ALLOWED
        assert decision.is_allowed is True

    def test_ready_with_human_present_allowed(self):
        """READY with human present → ALLOWED."""
        from python.phase16_execution.execution_context import ExecutionContext
        from python.phase16_execution.execution_engine import decide_execution
        from python.phase16_execution.execution_types import ExecutionPermission

        context = ExecutionContext(
            bug_id="BUG-001",
            target_id="TARGET-001",
            handoff_readiness="READY_FOR_BROWSER",
            handoff_can_proceed=True,
            handoff_is_blocked=False,
            handoff_human_presence="REQUIRED",
            contract_is_valid=True,
            human_present=True,  # Human is present
            decision_timestamp="2026-01-25T06:15:00-05:00",
            human_override=False
        )

        decision = decide_execution(context)
        assert decision.permission == ExecutionPermission.ALLOWED

    def test_review_required_with_override_allowed(self):
        """REVIEW_REQUIRED with human_override=True → ALLOWED."""
        from python.phase16_execution.execution_context import ExecutionContext
        from python.phase16_execution.execution_engine import decide_execution
        from python.phase16_execution.execution_types import ExecutionPermission

        context = ExecutionContext(
            bug_id="BUG-001",
            target_id="TARGET-001",
            handoff_readiness="REVIEW_REQUIRED",
            handoff_can_proceed=True,
            handoff_is_blocked=False,
            handoff_human_presence="OPTIONAL",
            contract_is_valid=True,
            human_present=True,
            decision_timestamp="2026-01-25T06:15:00-05:00",
            human_override=True  # Human override
        )

        decision = decide_execution(context)
        assert decision.permission == ExecutionPermission.ALLOWED
