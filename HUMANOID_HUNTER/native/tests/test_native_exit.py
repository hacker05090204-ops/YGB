"""
Tests for Phase-22 Native Exit Classification.

Tests:
- classify_native_exit for each state/code
"""
import pytest


class TestClassifyNativeExit:
    """Test native exit classification."""

    def test_exit_code_zero_is_normal(self):
        """Exit code 0 with EXITED state is NORMAL."""
        from HUMANOID_HUNTER.native.native_engine import classify_native_exit
        from HUMANOID_HUNTER.native.native_types import NativeProcessState, NativeExitReason

        reason = classify_native_exit(0, NativeProcessState.EXITED)
        assert reason == NativeExitReason.NORMAL

    def test_exit_code_nonzero_is_error(self):
        """Exit code non-zero with EXITED state is ERROR."""
        from HUMANOID_HUNTER.native.native_engine import classify_native_exit
        from HUMANOID_HUNTER.native.native_types import NativeProcessState, NativeExitReason

        reason = classify_native_exit(1, NativeProcessState.EXITED)
        assert reason == NativeExitReason.ERROR

    def test_crashed_state_is_crash(self):
        """CRASHED state is CRASH reason."""
        from HUMANOID_HUNTER.native.native_engine import classify_native_exit
        from HUMANOID_HUNTER.native.native_types import NativeProcessState, NativeExitReason

        reason = classify_native_exit(-11, NativeProcessState.CRASHED)
        assert reason == NativeExitReason.CRASH

    def test_timed_out_state_is_timeout(self):
        """TIMED_OUT state is TIMEOUT reason."""
        from HUMANOID_HUNTER.native.native_engine import classify_native_exit
        from HUMANOID_HUNTER.native.native_types import NativeProcessState, NativeExitReason

        reason = classify_native_exit(-1, NativeProcessState.TIMED_OUT)
        assert reason == NativeExitReason.TIMEOUT

    def test_killed_state_is_killed(self):
        """KILLED state is KILLED reason."""
        from HUMANOID_HUNTER.native.native_engine import classify_native_exit
        from HUMANOID_HUNTER.native.native_types import NativeProcessState, NativeExitReason

        reason = classify_native_exit(-9, NativeProcessState.KILLED)
        assert reason == NativeExitReason.KILLED

    def test_pending_state_is_unknown(self):
        """PENDING state is UNKNOWN reason."""
        from HUMANOID_HUNTER.native.native_engine import classify_native_exit
        from HUMANOID_HUNTER.native.native_types import NativeProcessState, NativeExitReason

        reason = classify_native_exit(0, NativeProcessState.PENDING)
        assert reason == NativeExitReason.UNKNOWN

    def test_running_state_is_unknown(self):
        """RUNNING state is UNKNOWN reason."""
        from HUMANOID_HUNTER.native.native_engine import classify_native_exit
        from HUMANOID_HUNTER.native.native_types import NativeProcessState, NativeExitReason

        reason = classify_native_exit(0, NativeProcessState.RUNNING)
        assert reason == NativeExitReason.UNKNOWN
