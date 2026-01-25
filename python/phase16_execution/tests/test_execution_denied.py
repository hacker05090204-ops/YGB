"""
Tests for Phase-16 Execution Denied.

Tests:
- Various denial conditions
"""
import pytest


class TestExecutionDenied:
    """Test execution denied conditions."""

    def test_not_ready_denied(self):
        """NOT_READY → DENIED."""
        from python.phase16_execution.execution_context import ExecutionContext
        from python.phase16_execution.execution_engine import decide_execution
        from python.phase16_execution.execution_types import ExecutionPermission

        context = ExecutionContext(
            bug_id="BUG-001",
            target_id="TARGET-001",
            handoff_readiness="NOT_READY",
            handoff_can_proceed=False,
            handoff_is_blocked=False,
            handoff_human_presence="OPTIONAL",
            contract_is_valid=True,
            human_present=False,
            decision_timestamp="2026-01-25T06:15:00-05:00",
            human_override=False
        )

        decision = decide_execution(context)
        assert decision.permission == ExecutionPermission.DENIED
        assert decision.reason_code == "EX-001"

    def test_review_required_no_override_denied(self):
        """REVIEW_REQUIRED without override → DENIED."""
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
            human_present=False,
            decision_timestamp="2026-01-25T06:15:00-05:00",
            human_override=False  # No override
        )

        decision = decide_execution(context)
        assert decision.permission == ExecutionPermission.DENIED
        assert decision.reason_code == "EX-002"

    def test_can_proceed_false_denied(self):
        """can_proceed=False → DENIED."""
        from python.phase16_execution.execution_context import ExecutionContext
        from python.phase16_execution.execution_engine import decide_execution
        from python.phase16_execution.execution_types import ExecutionPermission

        context = ExecutionContext(
            bug_id="BUG-001",
            target_id="TARGET-001",
            handoff_readiness="READY_FOR_BROWSER",
            handoff_can_proceed=False,  # Cannot proceed
            handoff_is_blocked=False,
            handoff_human_presence="OPTIONAL",
            contract_is_valid=True,
            human_present=False,
            decision_timestamp="2026-01-25T06:15:00-05:00",
            human_override=False
        )

        decision = decide_execution(context)
        assert decision.permission == ExecutionPermission.DENIED
        assert decision.reason_code == "EX-003"

    def test_is_blocked_true_denied(self):
        """is_blocked=True → DENIED."""
        from python.phase16_execution.execution_context import ExecutionContext
        from python.phase16_execution.execution_engine import decide_execution
        from python.phase16_execution.execution_types import ExecutionPermission

        context = ExecutionContext(
            bug_id="BUG-001",
            target_id="TARGET-001",
            handoff_readiness="READY_FOR_BROWSER",
            handoff_can_proceed=True,
            handoff_is_blocked=True,  # Blocked
            handoff_human_presence="OPTIONAL",
            contract_is_valid=True,
            human_present=False,
            decision_timestamp="2026-01-25T06:15:00-05:00",
            human_override=False
        )

        decision = decide_execution(context)
        assert decision.permission == ExecutionPermission.DENIED
        assert decision.reason_code == "EX-004"

    def test_human_required_absent_denied(self):
        """human_presence=REQUIRED but absent → DENIED."""
        from python.phase16_execution.execution_context import ExecutionContext
        from python.phase16_execution.execution_engine import decide_execution
        from python.phase16_execution.execution_types import ExecutionPermission

        context = ExecutionContext(
            bug_id="BUG-001",
            target_id="TARGET-001",
            handoff_readiness="READY_FOR_BROWSER",
            handoff_can_proceed=True,
            handoff_is_blocked=False,
            handoff_human_presence="REQUIRED",  # Requires human
            contract_is_valid=True,
            human_present=False,  # But absent
            decision_timestamp="2026-01-25T06:15:00-05:00",
            human_override=False
        )

        decision = decide_execution(context)
        assert decision.permission == ExecutionPermission.DENIED
        assert decision.reason_code == "EX-005"

    def test_human_blocking_denied(self):
        """human_presence=BLOCKING → DENIED."""
        from python.phase16_execution.execution_context import ExecutionContext
        from python.phase16_execution.execution_engine import decide_execution
        from python.phase16_execution.execution_types import ExecutionPermission

        context = ExecutionContext(
            bug_id="BUG-001",
            target_id="TARGET-001",
            handoff_readiness="READY_FOR_BROWSER",
            handoff_can_proceed=True,
            handoff_is_blocked=False,
            handoff_human_presence="BLOCKING",  # Blocking
            contract_is_valid=True,
            human_present=True,
            decision_timestamp="2026-01-25T06:15:00-05:00",
            human_override=False
        )

        decision = decide_execution(context)
        assert decision.permission == ExecutionPermission.DENIED
        assert decision.reason_code == "EX-006"

    def test_contract_invalid_denied(self):
        """contract_is_valid=False → DENIED."""
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
            contract_is_valid=False,  # Invalid contract
            human_present=False,
            decision_timestamp="2026-01-25T06:15:00-05:00",
            human_override=False
        )

        decision = decide_execution(context)
        assert decision.permission == ExecutionPermission.DENIED
        assert decision.reason_code == "EX-007"
