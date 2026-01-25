"""
Tests for Phase-22 Deny-By-Default.

Tests:
- Immutability
- Unknown states rejected
"""
import pytest


class TestDataclassFrozen:
    """Test dataclass immutability."""

    def test_native_execution_context_frozen(self):
        """NativeExecutionContext is frozen."""
        from HUMANOID_HUNTER.native.native_context import NativeExecutionContext

        context = NativeExecutionContext(
            execution_id="EXEC-001",
            process_id="PID-12345",
            command_hash="abc123",
            timeout_ms=30000,
            timestamp="2026-01-25T16:16:00-05:00"
        )

        with pytest.raises(Exception):
            context.execution_id = "MODIFIED"

    def test_native_execution_result_frozen(self):
        """NativeExecutionResult is frozen."""
        from HUMANOID_HUNTER.native.native_context import NativeExecutionResult
        from HUMANOID_HUNTER.native.native_types import NativeProcessState, NativeExitReason

        result = NativeExecutionResult(
            execution_id="EXEC-001",
            process_state=NativeProcessState.EXITED,
            exit_reason=NativeExitReason.NORMAL,
            exit_code=0,
            evidence_hash="abc",
            output_hash="def",
            duration_ms=1000
        )

        with pytest.raises(Exception):
            result.exit_code = 1

    def test_isolation_decision_result_frozen(self):
        """IsolationDecisionResult is frozen."""
        from HUMANOID_HUNTER.native.native_context import IsolationDecisionResult
        from HUMANOID_HUNTER.native.native_types import IsolationDecision

        result = IsolationDecisionResult(
            decision=IsolationDecision.ACCEPT,
            reason_code="OK",
            reason_description="Accepted"
        )

        with pytest.raises(Exception):
            result.decision = IsolationDecision.REJECT


class TestUnknownStatesRejected:
    """Test unknown states are rejected."""

    def test_pending_state_rejected(self):
        """PENDING state is rejected."""
        from HUMANOID_HUNTER.native.native_engine import decide_native_outcome
        from HUMANOID_HUNTER.native.native_context import NativeExecutionContext, NativeExecutionResult
        from HUMANOID_HUNTER.native.native_types import NativeProcessState, NativeExitReason, IsolationDecision

        context = NativeExecutionContext(
            execution_id="EXEC-001",
            process_id="PID-12345",
            command_hash="abc123",
            timeout_ms=30000,
            timestamp="2026-01-25T16:16:00-05:00"
        )
        result = NativeExecutionResult(
            execution_id="EXEC-001",
            process_state=NativeProcessState.PENDING,
            exit_reason=NativeExitReason.UNKNOWN,
            exit_code=0,
            evidence_hash="evidence123",
            output_hash="output456",
            duration_ms=0
        )

        decision = decide_native_outcome(result, context)
        assert decision.decision == IsolationDecision.REJECT

    def test_running_state_rejected(self):
        """RUNNING state is rejected."""
        from HUMANOID_HUNTER.native.native_engine import decide_native_outcome
        from HUMANOID_HUNTER.native.native_context import NativeExecutionContext, NativeExecutionResult
        from HUMANOID_HUNTER.native.native_types import NativeProcessState, NativeExitReason, IsolationDecision

        context = NativeExecutionContext(
            execution_id="EXEC-001",
            process_id="PID-12345",
            command_hash="abc123",
            timeout_ms=30000,
            timestamp="2026-01-25T16:16:00-05:00"
        )
        result = NativeExecutionResult(
            execution_id="EXEC-001",
            process_state=NativeProcessState.RUNNING,
            exit_reason=NativeExitReason.UNKNOWN,
            exit_code=0,
            evidence_hash="",
            output_hash="",
            duration_ms=1000
        )

        decision = decide_native_outcome(result, context)
        assert decision.decision == IsolationDecision.REJECT
        assert "RUNNING" in decision.reason_description

    def test_unexpected_exit_reason_rejected(self):
        """Unexpected exit reason (e.g., CRASH reason with EXITED state) is rejected."""
        from HUMANOID_HUNTER.native.native_engine import decide_native_outcome
        from HUMANOID_HUNTER.native.native_context import NativeExecutionContext, NativeExecutionResult
        from HUMANOID_HUNTER.native.native_types import NativeProcessState, NativeExitReason, IsolationDecision

        context = NativeExecutionContext(
            execution_id="EXEC-001",
            process_id="PID-12345",
            command_hash="abc123",
            timeout_ms=30000,
            timestamp="2026-01-25T16:16:00-05:00"
        )
        # Malformed: EXITED state with CRASH reason
        result = NativeExecutionResult(
            execution_id="EXEC-001",
            process_state=NativeProcessState.EXITED,
            exit_reason=NativeExitReason.CRASH,  # Invalid for EXITED
            exit_code=0,
            evidence_hash="evidence123",
            output_hash="output456",
            duration_ms=1500
        )

        decision = decide_native_outcome(result, context)
        assert decision.decision == IsolationDecision.REJECT
