"""
Tests for Phase-30 Response Normalization.

Tests:
- Valid normalization
- Missing fields → MALFORMED
- Instruction hash mismatch → REJECT
"""
import pytest


class TestNormalizeExecutorResponse:
    """Test normalize_executor_response function."""

    def test_valid_response_normalized(self):
        """Valid response is normalized correctly."""
        from HUMANOID_HUNTER.executor_response.response_engine import normalize_executor_response
        from HUMANOID_HUNTER.executor_response.response_types import ExecutorResponseType
        from HUMANOID_HUNTER.executor_response.response_context import ExecutorRawResponse

        raw = ExecutorRawResponse(
            executor_id="EXEC-001",
            instruction_hash="HASH-001",
            raw_payload={"data": "test"},
            reported_status=ExecutorResponseType.SUCCESS
        )

        result = normalize_executor_response(raw, expected_hash="HASH-001")
        assert result.decision is not None

    def test_missing_executor_id_is_malformed(self):
        """Missing executor_id → MALFORMED."""
        from HUMANOID_HUNTER.executor_response.response_engine import normalize_executor_response
        from HUMANOID_HUNTER.executor_response.response_types import ExecutorResponseType, ResponseDecision
        from HUMANOID_HUNTER.executor_response.response_context import ExecutorRawResponse

        raw = ExecutorRawResponse(
            executor_id="",  # Missing
            instruction_hash="HASH-001",
            raw_payload={"data": "test"},
            reported_status=ExecutorResponseType.SUCCESS
        )

        result = normalize_executor_response(raw, expected_hash="HASH-001")
        assert result.decision == ResponseDecision.REJECT
        assert "MALFORMED" in result.reason

    def test_missing_instruction_hash_is_malformed(self):
        """Missing instruction_hash → MALFORMED."""
        from HUMANOID_HUNTER.executor_response.response_engine import normalize_executor_response
        from HUMANOID_HUNTER.executor_response.response_types import ExecutorResponseType, ResponseDecision
        from HUMANOID_HUNTER.executor_response.response_context import ExecutorRawResponse

        raw = ExecutorRawResponse(
            executor_id="EXEC-001",
            instruction_hash="",  # Missing
            raw_payload={"data": "test"},
            reported_status=ExecutorResponseType.SUCCESS
        )

        result = normalize_executor_response(raw, expected_hash="HASH-001")
        assert result.decision == ResponseDecision.REJECT
        assert "MALFORMED" in result.reason

    def test_instruction_hash_mismatch_is_rejected(self):
        """Instruction hash mismatch → REJECT."""
        from HUMANOID_HUNTER.executor_response.response_engine import normalize_executor_response
        from HUMANOID_HUNTER.executor_response.response_types import ExecutorResponseType, ResponseDecision
        from HUMANOID_HUNTER.executor_response.response_context import ExecutorRawResponse

        raw = ExecutorRawResponse(
            executor_id="EXEC-001",
            instruction_hash="HASH-002",  # Different
            raw_payload={"data": "test"},
            reported_status=ExecutorResponseType.SUCCESS
        )

        result = normalize_executor_response(raw, expected_hash="HASH-001")
        assert result.decision == ResponseDecision.REJECT
        assert "mismatch" in result.reason.lower()


class TestRawResponseStructure:
    """Test ExecutorRawResponse structure."""

    def test_raw_response_creation(self):
        """ExecutorRawResponse can be created."""
        from HUMANOID_HUNTER.executor_response.response_context import ExecutorRawResponse
        from HUMANOID_HUNTER.executor_response.response_types import ExecutorResponseType

        raw = ExecutorRawResponse(
            executor_id="EXEC-001",
            instruction_hash="HASH-001",
            raw_payload=None,
            reported_status=ExecutorResponseType.FAILURE
        )

        assert raw.executor_id == "EXEC-001"

    def test_raw_response_frozen(self):
        """ExecutorRawResponse is frozen."""
        from HUMANOID_HUNTER.executor_response.response_context import ExecutorRawResponse
        from HUMANOID_HUNTER.executor_response.response_types import ExecutorResponseType

        raw = ExecutorRawResponse(
            executor_id="EXEC-001",
            instruction_hash="HASH-001",
            raw_payload=None,
            reported_status=ExecutorResponseType.FAILURE
        )

        with pytest.raises(Exception):
            raw.executor_id = "MODIFIED"
