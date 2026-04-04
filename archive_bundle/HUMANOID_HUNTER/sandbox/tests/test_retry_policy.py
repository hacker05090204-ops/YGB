"""
Tests for Phase-21 Retry Policy.

Tests:
- is_retry_allowed
- enforce_retry_limit
"""
import pytest


class TestIsRetryAllowed:
    """Test is_retry_allowed function."""

    def test_retry_allowed_within_limit(self):
        """Retry allowed within limit."""
        from HUMANOID_HUNTER.sandbox.sandbox_engine import is_retry_allowed
        from HUMANOID_HUNTER.sandbox.sandbox_context import SandboxContext

        context = SandboxContext(
            execution_id="EXEC-001",
            instruction_id="INSTR-001",
            attempt_number=1,
            max_retries=3,
            timeout_ms=30000,
            timestamp="2026-01-25T16:00:00-05:00"
        )

        assert is_retry_allowed(context) is True

    def test_retry_denied_at_limit(self):
        """Retry denied at limit."""
        from HUMANOID_HUNTER.sandbox.sandbox_engine import is_retry_allowed
        from HUMANOID_HUNTER.sandbox.sandbox_context import SandboxContext

        context = SandboxContext(
            execution_id="EXEC-001",
            instruction_id="INSTR-001",
            attempt_number=3,
            max_retries=3,
            timeout_ms=30000,
            timestamp="2026-01-25T16:00:00-05:00"
        )

        assert is_retry_allowed(context) is False

    def test_retry_denied_over_limit(self):
        """Retry denied over limit."""
        from HUMANOID_HUNTER.sandbox.sandbox_engine import is_retry_allowed
        from HUMANOID_HUNTER.sandbox.sandbox_context import SandboxContext

        context = SandboxContext(
            execution_id="EXEC-001",
            instruction_id="INSTR-001",
            attempt_number=5,
            max_retries=3,
            timeout_ms=30000,
            timestamp="2026-01-25T16:00:00-05:00"
        )

        assert is_retry_allowed(context) is False


class TestEnforceRetryLimit:
    """Test enforce_retry_limit function."""

    def test_enforce_limit_passes_within(self):
        """Enforce limit passes within limit."""
        from HUMANOID_HUNTER.sandbox.sandbox_engine import enforce_retry_limit
        from HUMANOID_HUNTER.sandbox.sandbox_context import SandboxContext

        context = SandboxContext(
            execution_id="EXEC-001",
            instruction_id="INSTR-001",
            attempt_number=2,
            max_retries=3,
            timeout_ms=30000,
            timestamp="2026-01-25T16:00:00-05:00"
        )

        assert enforce_retry_limit(context) is True

    def test_enforce_limit_fails_at_limit(self):
        """Enforce limit fails at limit."""
        from HUMANOID_HUNTER.sandbox.sandbox_engine import enforce_retry_limit
        from HUMANOID_HUNTER.sandbox.sandbox_context import SandboxContext

        context = SandboxContext(
            execution_id="EXEC-001",
            instruction_id="INSTR-001",
            attempt_number=3,
            max_retries=3,
            timeout_ms=30000,
            timestamp="2026-01-25T16:00:00-05:00"
        )

        assert enforce_retry_limit(context) is False
