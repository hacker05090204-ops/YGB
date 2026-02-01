"""
Tests for Phase-21 Fault Classification.

Tests:
- classify_fault for each fault type
- Retry policy assignments
"""
import pytest


class TestClassifyFault:
    """Test fault classification."""

    def test_crash_is_retryable(self):
        """CRASH is retryable."""
        from HUMANOID_HUNTER.sandbox.sandbox_engine import classify_fault
        from HUMANOID_HUNTER.sandbox.sandbox_types import ExecutionFaultType, RetryPolicy

        policy = classify_fault(ExecutionFaultType.CRASH)
        assert policy == RetryPolicy.RETRY_LIMITED

    def test_timeout_is_retryable(self):
        """TIMEOUT is retryable."""
        from HUMANOID_HUNTER.sandbox.sandbox_engine import classify_fault
        from HUMANOID_HUNTER.sandbox.sandbox_types import ExecutionFaultType, RetryPolicy

        policy = classify_fault(ExecutionFaultType.TIMEOUT)
        assert policy == RetryPolicy.RETRY_LIMITED

    def test_partial_is_not_retryable(self):
        """PARTIAL is not retryable."""
        from HUMANOID_HUNTER.sandbox.sandbox_engine import classify_fault
        from HUMANOID_HUNTER.sandbox.sandbox_types import ExecutionFaultType, RetryPolicy

        policy = classify_fault(ExecutionFaultType.PARTIAL)
        assert policy == RetryPolicy.NO_RETRY

    def test_invalid_response_is_not_retryable(self):
        """INVALID_RESPONSE is not retryable."""
        from HUMANOID_HUNTER.sandbox.sandbox_engine import classify_fault
        from HUMANOID_HUNTER.sandbox.sandbox_types import ExecutionFaultType, RetryPolicy

        policy = classify_fault(ExecutionFaultType.INVALID_RESPONSE)
        assert policy == RetryPolicy.NO_RETRY

    def test_resource_exhausted_needs_human(self):
        """RESOURCE_EXHAUSTED needs human decision."""
        from HUMANOID_HUNTER.sandbox.sandbox_engine import classify_fault
        from HUMANOID_HUNTER.sandbox.sandbox_types import ExecutionFaultType, RetryPolicy

        policy = classify_fault(ExecutionFaultType.RESOURCE_EXHAUSTED)
        assert policy == RetryPolicy.HUMAN_DECISION

    def test_security_violation_is_not_retryable(self):
        """SECURITY_VIOLATION is not retryable."""
        from HUMANOID_HUNTER.sandbox.sandbox_engine import classify_fault
        from HUMANOID_HUNTER.sandbox.sandbox_types import ExecutionFaultType, RetryPolicy

        policy = classify_fault(ExecutionFaultType.SECURITY_VIOLATION)
        assert policy == RetryPolicy.NO_RETRY
