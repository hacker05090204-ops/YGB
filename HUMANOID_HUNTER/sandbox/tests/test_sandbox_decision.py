"""
Tests for Phase-21 Sandbox Decision.

Tests:
- decide_sandbox_outcome for various faults
"""
import pytest


class TestDecideSandboxOutcome:
    """Test sandbox decision logic."""

    def test_crash_within_limit_retries(self):
        """CRASH within limit triggers RETRY."""
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
            fault_type=ExecutionFaultType.CRASH,
            fault_message="Executor crashed",
            occurred_at="2026-01-25T16:00:00-05:00",
            attempt_number=1
        )

        result = decide_sandbox_outcome(fault, context)
        assert result.decision == SandboxDecision.RETRY

    def test_crash_at_limit_terminates(self):
        """CRASH at limit triggers TERMINATE."""
        from HUMANOID_HUNTER.sandbox.sandbox_engine import decide_sandbox_outcome
        from HUMANOID_HUNTER.sandbox.sandbox_context import SandboxContext, FaultReport
        from HUMANOID_HUNTER.sandbox.sandbox_types import ExecutionFaultType, SandboxDecision

        context = SandboxContext(
            execution_id="EXEC-001",
            instruction_id="INSTR-001",
            attempt_number=3,
            max_retries=3,
            timeout_ms=30000,
            timestamp="2026-01-25T16:00:00-05:00"
        )
        fault = FaultReport(
            fault_id="FAULT-001",
            execution_id="EXEC-001",
            fault_type=ExecutionFaultType.CRASH,
            fault_message="Executor crashed",
            occurred_at="2026-01-25T16:00:00-05:00",
            attempt_number=3
        )

        result = decide_sandbox_outcome(fault, context)
        assert result.decision == SandboxDecision.TERMINATE

    def test_partial_always_terminates(self):
        """PARTIAL always terminates."""
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
            fault_type=ExecutionFaultType.PARTIAL,
            fault_message="Partial output",
            occurred_at="2026-01-25T16:00:00-05:00",
            attempt_number=1
        )

        result = decide_sandbox_outcome(fault, context)
        assert result.decision == SandboxDecision.TERMINATE

    def test_resource_exhausted_escalates(self):
        """RESOURCE_EXHAUSTED escalates."""
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
            fault_type=ExecutionFaultType.RESOURCE_EXHAUSTED,
            fault_message="Out of memory",
            occurred_at="2026-01-25T16:00:00-05:00",
            attempt_number=1
        )

        result = decide_sandbox_outcome(fault, context)
        assert result.decision == SandboxDecision.ESCALATE

    def test_security_violation_terminates(self):
        """SECURITY_VIOLATION always terminates."""
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
            fault_type=ExecutionFaultType.SECURITY_VIOLATION,
            fault_message="Security breach",
            occurred_at="2026-01-25T16:00:00-05:00",
            attempt_number=1
        )

        result = decide_sandbox_outcome(fault, context)
        assert result.decision == SandboxDecision.TERMINATE
