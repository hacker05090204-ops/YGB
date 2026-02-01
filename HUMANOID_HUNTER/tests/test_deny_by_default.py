"""
Tests for Phase-20 Deny-By-Default.

Tests:
- Unknown response → DENIED
- Missing fields → DENIED
"""
import pytest


class TestDenyByDefault:
    """Test deny-by-default behavior."""

    def test_missing_instruction_id_denied(self):
        """Empty instruction_id is denied."""
        from HUMANOID_HUNTER.interface.executor_adapter import validate_executor_response
        from HUMANOID_HUNTER.interface.executor_context import ExecutorResponseEnvelope
        from HUMANOID_HUNTER.interface.executor_types import ExecutorResponseType

        response = ExecutorResponseEnvelope(
            instruction_id="",  # Empty
            response_type=ExecutorResponseType.SUCCESS,
            evidence_hash="abc123",
            error_message="",
            timestamp="2026-01-25T15:30:00-05:00"
        )

        result = validate_executor_response(response, "INSTR-001")
        assert result.is_safe is False

    def test_enforce_executor_safety_with_mismatch(self):
        """enforce_executor_safety catches mismatch."""
        from HUMANOID_HUNTER.interface.executor_adapter import (
            build_executor_instruction,
            validate_executor_response,
            enforce_executor_safety
        )
        from HUMANOID_HUNTER.interface.executor_context import ExecutorResponseEnvelope
        from HUMANOID_HUNTER.interface.executor_types import ExecutorCommandType, ExecutorResponseType

        instruction = build_executor_instruction(
            execution_id="EXEC-001",
            command_type=ExecutorCommandType.CLICK,
            target_url="",
            target_selector="#btn",
            timestamp="2026-01-25T15:30:00-05:00"
        )

        response = ExecutorResponseEnvelope(
            instruction_id="WRONG-ID",
            response_type=ExecutorResponseType.SUCCESS,
            evidence_hash="abc123",
            error_message="",
            timestamp="2026-01-25T15:31:00-05:00"
        )

        is_safe = enforce_executor_safety(instruction, response)
        assert is_safe is False


class TestSafetyResultFrozen:
    """Test safety result immutability."""

    def test_safety_result_is_frozen(self):
        """ExecutionSafetyResult is frozen."""
        from HUMANOID_HUNTER.interface.executor_context import ExecutionSafetyResult

        result = ExecutionSafetyResult(
            is_safe=True,
            reason_code="OK",
            reason_description="Safe"
        )

        with pytest.raises(Exception):
            result.is_safe = False
