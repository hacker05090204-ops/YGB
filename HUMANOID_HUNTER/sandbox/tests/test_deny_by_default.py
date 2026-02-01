"""
Tests for Phase-21 Deny-By-Default.

Tests:
- Immutability
- Fault ≠ success
"""
import pytest


class TestDataclassFrozen:
    """Test dataclass immutability."""

    def test_sandbox_context_frozen(self):
        """SandboxContext is frozen."""
        from HUMANOID_HUNTER.sandbox.sandbox_context import SandboxContext

        context = SandboxContext(
            execution_id="EXEC-001",
            instruction_id="INSTR-001",
            attempt_number=1,
            max_retries=3,
            timeout_ms=30000,
            timestamp="2026-01-25T16:00:00-05:00"
        )

        with pytest.raises(Exception):
            context.attempt_number = 2

    def test_fault_report_frozen(self):
        """FaultReport is frozen."""
        from HUMANOID_HUNTER.sandbox.sandbox_context import FaultReport
        from HUMANOID_HUNTER.sandbox.sandbox_types import ExecutionFaultType

        fault = FaultReport(
            fault_id="FAULT-001",
            execution_id="EXEC-001",
            fault_type=ExecutionFaultType.CRASH,
            fault_message="Crashed",
            occurred_at="2026-01-25T16:00:00-05:00",
            attempt_number=1
        )

        with pytest.raises(Exception):
            fault.fault_type = ExecutionFaultType.TIMEOUT

    def test_decision_result_frozen(self):
        """SandboxDecisionResult is frozen."""
        from HUMANOID_HUNTER.sandbox.sandbox_context import SandboxDecisionResult
        from HUMANOID_HUNTER.sandbox.sandbox_types import SandboxDecision, RetryPolicy

        result = SandboxDecisionResult(
            decision=SandboxDecision.TERMINATE,
            retry_policy=RetryPolicy.NO_RETRY,
            reason_code="OK",
            reason_description="Terminated"
        )

        with pytest.raises(Exception):
            result.decision = SandboxDecision.RETRY


class TestFaultNotSuccess:
    """Test that faults are never treated as success."""

    def test_timeout_within_limit_retries(self):
        """TIMEOUT within limit triggers RETRY (not success)."""
        from HUMANOID_HUNTER.sandbox.sandbox_engine import decide_sandbox_outcome
        from HUMANOID_HUNTER.sandbox.sandbox_context import SandboxContext, FaultReport
        from HUMANOID_HUNTER.sandbox.sandbox_types import ExecutionFaultType, SandboxDecision

        context = SandboxContext(
            execution_id="EXEC-001",
            instruction_id="INSTR-001",
            attempt_number=1,
            max_retries=3,
            timeout_ms=30000,
            timestamp="2026-01-25T16:00:00-05:00"
        )
        fault = FaultReport(
            fault_id="FAULT-001",
            execution_id="EXEC-001",
            fault_type=ExecutionFaultType.TIMEOUT,
            fault_message="Timeout",
            occurred_at="2026-01-25T16:00:00-05:00",
            attempt_number=1
        )

        result = decide_sandbox_outcome(fault, context)
        # Even when retry is allowed, fault is NOT success
        assert result.decision == SandboxDecision.RETRY
        assert "TIMEOUT" in result.reason_description or "fault" in result.reason_description.lower()
