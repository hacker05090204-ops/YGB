"""
Tests for Phase-20 Executor Response.

Tests:
- Validate executor response
- Response envelope immutability
"""
import pytest


class TestValidateExecutorResponse:
    """Test executor response validation."""

    def test_success_with_evidence_is_safe(self):
        """SUCCESS with evidence_hash is safe."""
        from HUMANOID_HUNTER.interface.executor_adapter import validate_executor_response
        from HUMANOID_HUNTER.interface.executor_context import ExecutorResponseEnvelope
        from HUMANOID_HUNTER.interface.executor_types import ExecutorResponseType

        response = ExecutorResponseEnvelope(
            instruction_id="INSTR-001",
            response_type=ExecutorResponseType.SUCCESS,
            evidence_hash="abc123def456",
            error_message="",
            timestamp="2026-01-25T15:30:00-05:00"
        )

        result = validate_executor_response(response, "INSTR-001")
        assert result.is_safe is True

    def test_success_without_evidence_is_denied(self):
        """SUCCESS without evidence_hash is denied."""
        from HUMANOID_HUNTER.interface.executor_adapter import validate_executor_response
        from HUMANOID_HUNTER.interface.executor_context import ExecutorResponseEnvelope
        from HUMANOID_HUNTER.interface.executor_types import ExecutorResponseType

        response = ExecutorResponseEnvelope(
            instruction_id="INSTR-001",
            response_type=ExecutorResponseType.SUCCESS,
            evidence_hash="",  # Empty
            error_message="",
            timestamp="2026-01-25T15:30:00-05:00"
        )

        result = validate_executor_response(response, "INSTR-001")
        assert result.is_safe is False
        assert result.reason_code == "EXE-001"

    def test_instruction_id_mismatch_denied(self):
        """instruction_id mismatch is denied."""
        from HUMANOID_HUNTER.interface.executor_adapter import validate_executor_response
        from HUMANOID_HUNTER.interface.executor_context import ExecutorResponseEnvelope
        from HUMANOID_HUNTER.interface.executor_types import ExecutorResponseType

        response = ExecutorResponseEnvelope(
            instruction_id="INSTR-002",  # Different ID
            response_type=ExecutorResponseType.SUCCESS,
            evidence_hash="abc123",
            error_message="",
            timestamp="2026-01-25T15:30:00-05:00"
        )

        result = validate_executor_response(response, "INSTR-001")
        assert result.is_safe is False
        assert result.reason_code == "EXE-002"


class TestResponseEnvelopeFrozen:
    """Test response envelope immutability."""

    def test_response_envelope_is_frozen(self):
        """ExecutorResponseEnvelope is frozen."""
        from HUMANOID_HUNTER.interface.executor_context import ExecutorResponseEnvelope
        from HUMANOID_HUNTER.interface.executor_types import ExecutorResponseType

        response = ExecutorResponseEnvelope(
            instruction_id="INSTR-001",
            response_type=ExecutorResponseType.FAILURE,
            evidence_hash="",
            error_message="Failed",
            timestamp="2026-01-25T15:30:00-05:00"
        )

        with pytest.raises(Exception):
            response.instruction_id = "MODIFIED"
