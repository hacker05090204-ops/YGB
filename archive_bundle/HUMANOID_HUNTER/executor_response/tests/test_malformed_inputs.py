"""
Tests for Phase-30 Malformed Inputs.

Tests:
- Empty executor_id
- Empty instruction_hash
- None raw_payload handling
"""
import pytest


class TestMalformedInputs:
    """Test malformed input handling."""

    def test_empty_executor_id_malformed(self):
        """Empty executor_id is MALFORMED."""
        from HUMANOID_HUNTER.executor_response.response_engine import normalize_executor_response
        from HUMANOID_HUNTER.executor_response.response_types import ExecutorResponseType, ResponseDecision
        from HUMANOID_HUNTER.executor_response.response_context import ExecutorRawResponse

        raw = ExecutorRawResponse(
            executor_id="",
            instruction_hash="HASH-001",
            raw_payload={},
            reported_status=ExecutorResponseType.SUCCESS
        )

        result = normalize_executor_response(raw, expected_hash="HASH-001")
        assert result.decision == ResponseDecision.REJECT

    def test_whitespace_executor_id_malformed(self):
        """Whitespace-only executor_id is MALFORMED."""
        from HUMANOID_HUNTER.executor_response.response_engine import normalize_executor_response
        from HUMANOID_HUNTER.executor_response.response_types import ExecutorResponseType, ResponseDecision
        from HUMANOID_HUNTER.executor_response.response_context import ExecutorRawResponse

        raw = ExecutorRawResponse(
            executor_id="   ",  # Whitespace only
            instruction_hash="HASH-001",
            raw_payload={},
            reported_status=ExecutorResponseType.SUCCESS
        )

        result = normalize_executor_response(raw, expected_hash="HASH-001")
        assert result.decision == ResponseDecision.REJECT

    def test_empty_instruction_hash_malformed(self):
        """Empty instruction_hash is MALFORMED."""
        from HUMANOID_HUNTER.executor_response.response_engine import normalize_executor_response
        from HUMANOID_HUNTER.executor_response.response_types import ExecutorResponseType, ResponseDecision
        from HUMANOID_HUNTER.executor_response.response_context import ExecutorRawResponse

        raw = ExecutorRawResponse(
            executor_id="EXEC-001",
            instruction_hash="",
            raw_payload={},
            reported_status=ExecutorResponseType.SUCCESS
        )

        result = normalize_executor_response(raw, expected_hash="HASH-001")
        assert result.decision == ResponseDecision.REJECT

    def test_none_payload_accepted(self):
        """None payload is allowed (opaque data)."""
        from HUMANOID_HUNTER.executor_response.response_engine import normalize_executor_response
        from HUMANOID_HUNTER.executor_response.response_types import ExecutorResponseType
        from HUMANOID_HUNTER.executor_response.response_context import ExecutorRawResponse

        raw = ExecutorRawResponse(
            executor_id="EXEC-001",
            instruction_hash="HASH-001",
            raw_payload=None,  # None is allowed
            reported_status=ExecutorResponseType.FAILURE
        )

        result = normalize_executor_response(raw, expected_hash="HASH-001")
        # Should not be rejected for None payload
        assert "MALFORMED" not in result.reason or "payload" not in result.reason.lower()

    def test_malformed_response_type_handled(self):
        """MALFORMED response type is handled."""
        from HUMANOID_HUNTER.executor_response.response_engine import normalize_executor_response
        from HUMANOID_HUNTER.executor_response.response_types import ExecutorResponseType, ResponseDecision
        from HUMANOID_HUNTER.executor_response.response_context import ExecutorRawResponse

        raw = ExecutorRawResponse(
            executor_id="EXEC-001",
            instruction_hash="HASH-001",
            raw_payload={},
            reported_status=ExecutorResponseType.MALFORMED
        )

        result = normalize_executor_response(raw, expected_hash="HASH-001")
        assert result.decision == ResponseDecision.REJECT
