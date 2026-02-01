"""
Tests for Phase-22 Isolation Decision.

Tests:
- decide_native_outcome for various states
"""
import pytest


class TestDecideNativeOutcome:
    """Test native outcome decisions."""

    def test_normal_exit_with_evidence_accepted(self):
        """Normal exit with evidence is ACCEPT."""
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
            process_state=NativeProcessState.EXITED,
            exit_reason=NativeExitReason.NORMAL,
            exit_code=0,
            evidence_hash="evidence123",
            output_hash="output456",
            duration_ms=1500
        )

        decision = decide_native_outcome(result, context)
        assert decision.decision == IsolationDecision.ACCEPT

    def test_normal_exit_without_evidence_rejected(self):
        """Normal exit without evidence is REJECT."""
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
            process_state=NativeProcessState.EXITED,
            exit_reason=NativeExitReason.NORMAL,
            exit_code=0,
            evidence_hash="",  # Missing!
            output_hash="output456",
            duration_ms=1500
        )

        decision = decide_native_outcome(result, context)
        assert decision.decision == IsolationDecision.REJECT

    def test_crashed_state_rejected(self):
        """CRASHED state is REJECT."""
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
            process_state=NativeProcessState.CRASHED,
            exit_reason=NativeExitReason.CRASH,
            exit_code=-11,
            evidence_hash="evidence123",
            output_hash="output456",
            duration_ms=500
        )

        decision = decide_native_outcome(result, context)
        assert decision.decision == IsolationDecision.REJECT

    def test_timed_out_rejected(self):
        """TIMED_OUT is REJECT."""
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
            process_state=NativeProcessState.TIMED_OUT,
            exit_reason=NativeExitReason.TIMEOUT,
            exit_code=-1,
            evidence_hash="evidence123",
            output_hash="",
            duration_ms=30001
        )

        decision = decide_native_outcome(result, context)
        assert decision.decision == IsolationDecision.REJECT

    def test_killed_quarantined(self):
        """KILLED is QUARANTINE."""
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
            process_state=NativeProcessState.KILLED,
            exit_reason=NativeExitReason.KILLED,
            exit_code=-9,
            evidence_hash="evidence123",
            output_hash="",
            duration_ms=5000
        )

        decision = decide_native_outcome(result, context)
        assert decision.decision == IsolationDecision.QUARANTINE

    def test_error_exit_rejected(self):
        """ERROR exit is REJECT."""
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
            process_state=NativeProcessState.EXITED,
            exit_reason=NativeExitReason.ERROR,
            exit_code=1,
            evidence_hash="evidence123",
            output_hash="output456",
            duration_ms=1500
        )

        decision = decide_native_outcome(result, context)
        assert decision.decision == IsolationDecision.REJECT
        assert "ERROR" in decision.reason_description
