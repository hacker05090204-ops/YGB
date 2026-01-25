"""
Tests for Phase-22 Native Validation.

Tests:
- is_native_result_valid
- evaluate_isolation_result
"""
import pytest


class TestIsNativeResultValid:
    """Test is_native_result_valid function."""

    def test_valid_result_with_exited_and_evidence(self):
        """Valid result with EXITED and evidence."""
        from HUMANOID_HUNTER.native.native_engine import is_native_result_valid
        from HUMANOID_HUNTER.native.native_context import NativeExecutionResult
        from HUMANOID_HUNTER.native.native_types import NativeProcessState, NativeExitReason

        result = NativeExecutionResult(
            execution_id="EXEC-001",
            process_state=NativeProcessState.EXITED,
            exit_reason=NativeExitReason.NORMAL,
            exit_code=0,
            evidence_hash="evidence123",
            output_hash="output456",
            duration_ms=1500
        )

        assert is_native_result_valid(result) is True

    def test_invalid_result_pending(self):
        """PENDING state is invalid."""
        from HUMANOID_HUNTER.native.native_engine import is_native_result_valid
        from HUMANOID_HUNTER.native.native_context import NativeExecutionResult
        from HUMANOID_HUNTER.native.native_types import NativeProcessState, NativeExitReason

        result = NativeExecutionResult(
            execution_id="EXEC-001",
            process_state=NativeProcessState.PENDING,
            exit_reason=NativeExitReason.UNKNOWN,
            exit_code=0,
            evidence_hash="",
            output_hash="",
            duration_ms=0
        )

        assert is_native_result_valid(result) is False

    def test_invalid_result_running(self):
        """RUNNING state is invalid."""
        from HUMANOID_HUNTER.native.native_engine import is_native_result_valid
        from HUMANOID_HUNTER.native.native_context import NativeExecutionResult
        from HUMANOID_HUNTER.native.native_types import NativeProcessState, NativeExitReason

        result = NativeExecutionResult(
            execution_id="EXEC-001",
            process_state=NativeProcessState.RUNNING,
            exit_reason=NativeExitReason.UNKNOWN,
            exit_code=0,
            evidence_hash="",
            output_hash="",
            duration_ms=1000
        )

        assert is_native_result_valid(result) is False


class TestEvaluateIsolationResult:
    """Test evaluate_isolation_result function."""

    def test_exited_normal_with_evidence_is_accept(self):
        """EXITED with NORMAL and evidence is ACCEPT."""
        from HUMANOID_HUNTER.native.native_engine import evaluate_isolation_result
        from HUMANOID_HUNTER.native.native_context import NativeExecutionResult
        from HUMANOID_HUNTER.native.native_types import NativeProcessState, NativeExitReason, IsolationDecision

        result = NativeExecutionResult(
            execution_id="EXEC-001",
            process_state=NativeProcessState.EXITED,
            exit_reason=NativeExitReason.NORMAL,
            exit_code=0,
            evidence_hash="evidence123",
            output_hash="output456",
            duration_ms=1500
        )

        decision = evaluate_isolation_result(result)
        assert decision == IsolationDecision.ACCEPT

    def test_error_exit_is_reject(self):
        """ERROR exit is REJECT."""
        from HUMANOID_HUNTER.native.native_engine import evaluate_isolation_result
        from HUMANOID_HUNTER.native.native_context import NativeExecutionResult
        from HUMANOID_HUNTER.native.native_types import NativeProcessState, NativeExitReason, IsolationDecision

        result = NativeExecutionResult(
            execution_id="EXEC-001",
            process_state=NativeProcessState.EXITED,
            exit_reason=NativeExitReason.ERROR,
            exit_code=1,
            evidence_hash="evidence123",
            output_hash="output456",
            duration_ms=1500
        )

        decision = evaluate_isolation_result(result)
        assert decision == IsolationDecision.REJECT

    def test_crashed_is_reject(self):
        """CRASHED is REJECT in evaluate."""
        from HUMANOID_HUNTER.native.native_engine import evaluate_isolation_result
        from HUMANOID_HUNTER.native.native_context import NativeExecutionResult
        from HUMANOID_HUNTER.native.native_types import NativeProcessState, NativeExitReason, IsolationDecision

        result = NativeExecutionResult(
            execution_id="EXEC-001",
            process_state=NativeProcessState.CRASHED,
            exit_reason=NativeExitReason.CRASH,
            exit_code=-11,
            evidence_hash="evidence123",
            output_hash="output456",
            duration_ms=1500
        )

        decision = evaluate_isolation_result(result)
        assert decision == IsolationDecision.REJECT

    def test_timed_out_is_reject(self):
        """TIMED_OUT is REJECT in evaluate."""
        from HUMANOID_HUNTER.native.native_engine import evaluate_isolation_result
        from HUMANOID_HUNTER.native.native_context import NativeExecutionResult
        from HUMANOID_HUNTER.native.native_types import NativeProcessState, NativeExitReason, IsolationDecision

        result = NativeExecutionResult(
            execution_id="EXEC-001",
            process_state=NativeProcessState.TIMED_OUT,
            exit_reason=NativeExitReason.TIMEOUT,
            exit_code=-1,
            evidence_hash="",
            output_hash="",
            duration_ms=30001
        )

        decision = evaluate_isolation_result(result)
        assert decision == IsolationDecision.REJECT

    def test_killed_is_quarantine(self):
        """KILLED is QUARANTINE in evaluate."""
        from HUMANOID_HUNTER.native.native_engine import evaluate_isolation_result
        from HUMANOID_HUNTER.native.native_context import NativeExecutionResult
        from HUMANOID_HUNTER.native.native_types import NativeProcessState, NativeExitReason, IsolationDecision

        result = NativeExecutionResult(
            execution_id="EXEC-001",
            process_state=NativeProcessState.KILLED,
            exit_reason=NativeExitReason.KILLED,
            exit_code=-9,
            evidence_hash="",
            output_hash="",
            duration_ms=5000
        )

        decision = evaluate_isolation_result(result)
        assert decision == IsolationDecision.QUARANTINE

    def test_pending_is_reject(self):
        """PENDING is REJECT in evaluate."""
        from HUMANOID_HUNTER.native.native_engine import evaluate_isolation_result
        from HUMANOID_HUNTER.native.native_context import NativeExecutionResult
        from HUMANOID_HUNTER.native.native_types import NativeProcessState, NativeExitReason, IsolationDecision

        result = NativeExecutionResult(
            execution_id="EXEC-001",
            process_state=NativeProcessState.PENDING,
            exit_reason=NativeExitReason.UNKNOWN,
            exit_code=0,
            evidence_hash="",
            output_hash="",
            duration_ms=0
        )

        decision = evaluate_isolation_result(result)
        assert decision == IsolationDecision.REJECT

    def test_normal_without_evidence_is_reject(self):
        """NORMAL without evidence is REJECT in evaluate."""
        from HUMANOID_HUNTER.native.native_engine import evaluate_isolation_result
        from HUMANOID_HUNTER.native.native_context import NativeExecutionResult
        from HUMANOID_HUNTER.native.native_types import NativeProcessState, NativeExitReason, IsolationDecision

        result = NativeExecutionResult(
            execution_id="EXEC-001",
            process_state=NativeProcessState.EXITED,
            exit_reason=NativeExitReason.NORMAL,
            exit_code=0,
            evidence_hash="",  # Missing!
            output_hash="output456",
            duration_ms=1500
        )

        decision = evaluate_isolation_result(result)
        assert decision == IsolationDecision.REJECT

    def test_running_is_reject(self):
        """RUNNING is REJECT in evaluate."""
        from HUMANOID_HUNTER.native.native_engine import evaluate_isolation_result
        from HUMANOID_HUNTER.native.native_context import NativeExecutionResult
        from HUMANOID_HUNTER.native.native_types import NativeProcessState, NativeExitReason, IsolationDecision

        result = NativeExecutionResult(
            execution_id="EXEC-001",
            process_state=NativeProcessState.RUNNING,
            exit_reason=NativeExitReason.UNKNOWN,
            exit_code=0,
            evidence_hash="",
            output_hash="",
            duration_ms=1000
        )

        decision = evaluate_isolation_result(result)
        assert decision == IsolationDecision.REJECT

    def test_exited_with_unexpected_reason_is_reject(self):
        """EXITED with unexpected reason (not NORMAL/ERROR) is REJECT."""
        from HUMANOID_HUNTER.native.native_engine import evaluate_isolation_result
        from HUMANOID_HUNTER.native.native_context import NativeExecutionResult
        from HUMANOID_HUNTER.native.native_types import NativeProcessState, NativeExitReason, IsolationDecision

        # EXITED but with CRASH reason (malformed)
        result = NativeExecutionResult(
            execution_id="EXEC-001",
            process_state=NativeProcessState.EXITED,
            exit_reason=NativeExitReason.CRASH,
            exit_code=0,
            evidence_hash="evidence123",
            output_hash="output456",
            duration_ms=1500
        )

        decision = evaluate_isolation_result(result)
        assert decision == IsolationDecision.REJECT
