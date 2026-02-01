"""
Tests for Phase-16 Deny-By-Default.

Tests:
- Unknown → DENIED
- Null context → DENIED
- Determinism
"""
import pytest


class TestDenyByDefault:
    """Test deny-by-default behavior."""

    def test_null_context_denied(self):
        """Null context is denied."""
        from python.phase16_execution.execution_engine import decide_execution
        from python.phase16_execution.execution_types import ExecutionPermission

        decision = decide_execution(None)
        assert decision.permission == ExecutionPermission.DENIED
        assert decision.reason_code == "EX-000"

    def test_unknown_readiness_denied(self):
        """Unknown readiness value is denied."""
        from python.phase16_execution.execution_context import ExecutionContext
        from python.phase16_execution.execution_engine import decide_execution
        from python.phase16_execution.execution_types import ExecutionPermission

        context = ExecutionContext(
            bug_id="BUG-001",
            target_id="TARGET-001",
            handoff_readiness="UNKNOWN_STATE",  # Unknown
            handoff_can_proceed=True,
            handoff_is_blocked=False,
            handoff_human_presence="OPTIONAL",
            contract_is_valid=True,
            human_present=False,
            decision_timestamp="2026-01-25T06:15:00-05:00",
            human_override=False
        )

        decision = decide_execution(context)
        assert decision.permission == ExecutionPermission.DENIED
        assert decision.reason_code == "EX-009"


class TestDeterminism:
    """Test deterministic behavior."""

    def test_same_context_same_decision(self):
        """Same context produces same decision."""
        from python.phase16_execution.execution_context import ExecutionContext
        from python.phase16_execution.execution_engine import decide_execution

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

        decision1 = decide_execution(context)
        decision2 = decide_execution(context)
        decision3 = decide_execution(context)

        assert decision1.is_allowed == decision2.is_allowed == decision3.is_allowed


class TestDataclassFrozen:
    """Test dataclass immutability."""

    def test_execution_context_is_frozen(self):
        """ExecutionContext is frozen."""
        from python.phase16_execution.execution_context import ExecutionContext

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

        with pytest.raises(Exception):
            context.bug_id = "MODIFIED"

    def test_execution_decision_is_frozen(self):
        """ExecutionDecision is frozen."""
        from python.phase16_execution.execution_context import ExecutionContext
        from python.phase16_execution.execution_engine import decide_execution

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

        with pytest.raises(Exception):
            decision.is_allowed = False
