"""
Tests for Phase-16 Contract Dependency.

Tests:
- Correct handling of Phase-15 signals
"""
import pytest


class TestContractDependency:
    """Test Phase-15 contract dependency."""

    def test_check_contract_signals_pass(self):
        """Valid contract passes."""
        from python.phase16_execution.execution_context import ExecutionContext
        from python.phase16_execution.execution_engine import check_contract_signals

        context = ExecutionContext(
            bug_id="BUG-001",
            target_id="TARGET-001",
            handoff_readiness="READY_FOR_BROWSER",
            handoff_can_proceed=True,
            handoff_is_blocked=False,
            handoff_human_presence="OPTIONAL",
            contract_is_valid=True,  # Valid
            human_present=False,
            decision_timestamp="2026-01-25T06:15:00-05:00",
            human_override=False
        )

        assert check_contract_signals(context) is True

    def test_check_contract_signals_fail(self):
        """Invalid contract fails."""
        from python.phase16_execution.execution_context import ExecutionContext
        from python.phase16_execution.execution_engine import check_contract_signals

        context = ExecutionContext(
            bug_id="BUG-001",
            target_id="TARGET-001",
            handoff_readiness="READY_FOR_BROWSER",
            handoff_can_proceed=True,
            handoff_is_blocked=False,
            handoff_human_presence="OPTIONAL",
            contract_is_valid=False,  # Invalid
            human_present=False,
            decision_timestamp="2026-01-25T06:15:00-05:00",
            human_override=False
        )

        assert check_contract_signals(context) is False
