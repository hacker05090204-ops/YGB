"""
Tests for Phase-20 Safety Harness.

Tests:
- enforce_executor_safety
- Non-SUCCESS responses
"""
import pytest


class TestEnforceExecutorSafety:
    """Test executor safety enforcement."""

    def test_failure_response_is_safe(self):
        """FAILURE response is safe (executor reporting failure)."""
        from HUMANOID_HUNTER.interface.executor_adapter import validate_executor_response
        from HUMANOID_HUNTER.interface.executor_context import ExecutorResponseEnvelope
        from HUMANOID_HUNTER.interface.executor_types import ExecutorResponseType

        response = ExecutorResponseEnvelope(
            instruction_id="INSTR-001",
            response_type=ExecutorResponseType.FAILURE,
            evidence_hash="",
            error_message="Element not found",
            timestamp="2026-01-25T15:30:00-05:00"
        )

        result = validate_executor_response(response, "INSTR-001")
        assert result.is_safe is True

    def test_timeout_response_is_safe(self):
        """TIMEOUT response is safe."""
        from HUMANOID_HUNTER.interface.executor_adapter import validate_executor_response
        from HUMANOID_HUNTER.interface.executor_context import ExecutorResponseEnvelope
        from HUMANOID_HUNTER.interface.executor_types import ExecutorResponseType

        response = ExecutorResponseEnvelope(
            instruction_id="INSTR-001",
            response_type=ExecutorResponseType.TIMEOUT,
            evidence_hash="",
            error_message="Timeout after 30s",
            timestamp="2026-01-25T15:30:00-05:00"
        )

        result = validate_executor_response(response, "INSTR-001")
        assert result.is_safe is True

    def test_error_response_is_safe(self):
        """ERROR response is safe."""
        from HUMANOID_HUNTER.interface.executor_adapter import validate_executor_response
        from HUMANOID_HUNTER.interface.executor_context import ExecutorResponseEnvelope
        from HUMANOID_HUNTER.interface.executor_types import ExecutorResponseType

        response = ExecutorResponseEnvelope(
            instruction_id="INSTR-001",
            response_type=ExecutorResponseType.ERROR,
            evidence_hash="",
            error_message="Executor error",
            timestamp="2026-01-25T15:30:00-05:00"
        )

        result = validate_executor_response(response, "INSTR-001")
        assert result.is_safe is True

    def test_refused_response_is_safe(self):
        """REFUSED response is safe."""
        from HUMANOID_HUNTER.interface.executor_adapter import validate_executor_response
        from HUMANOID_HUNTER.interface.executor_context import ExecutorResponseEnvelope
        from HUMANOID_HUNTER.interface.executor_types import ExecutorResponseType

        response = ExecutorResponseEnvelope(
            instruction_id="INSTR-001",
            response_type=ExecutorResponseType.REFUSED,
            evidence_hash="",
            error_message="Action refused",
            timestamp="2026-01-25T15:30:00-05:00"
        )

        result = validate_executor_response(response, "INSTR-001")
        assert result.is_safe is True
