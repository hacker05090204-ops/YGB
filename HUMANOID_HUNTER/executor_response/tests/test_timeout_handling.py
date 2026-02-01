"""
Tests for Phase-30 Timeout Handling.

Tests:
- TIMEOUT response → FAILURE decision
- PARTIAL response → ESCALATE decision
"""
import pytest


class TestTimeoutHandling:
    """Test timeout response handling."""

    def test_timeout_becomes_failure(self):
        """TIMEOUT response → decide as FAILURE path."""
        from HUMANOID_HUNTER.executor_response.response_engine import decide_response_outcome
        from HUMANOID_HUNTER.executor_response.response_types import ExecutorResponseType, ResponseDecision

        decision = decide_response_outcome(ExecutorResponseType.TIMEOUT)
        assert decision == ResponseDecision.REJECT

    def test_timeout_reason_documented(self):
        """TIMEOUT includes reason in result."""
        from HUMANOID_HUNTER.executor_response.response_engine import normalize_executor_response
        from HUMANOID_HUNTER.executor_response.response_types import ExecutorResponseType
        from HUMANOID_HUNTER.executor_response.response_context import ExecutorRawResponse

        raw = ExecutorRawResponse(
            executor_id="EXEC-001",
            instruction_hash="HASH-001",
            raw_payload={},
            reported_status=ExecutorResponseType.TIMEOUT
        )

        result = normalize_executor_response(raw, expected_hash="HASH-001")
        assert result.reason is not None
        assert len(result.reason) > 0


class TestPartialHandling:
    """Test partial response handling."""

    def test_partial_becomes_escalate(self):
        """PARTIAL response → ESCALATE decision."""
        from HUMANOID_HUNTER.executor_response.response_engine import decide_response_outcome
        from HUMANOID_HUNTER.executor_response.response_types import ExecutorResponseType, ResponseDecision

        decision = decide_response_outcome(ExecutorResponseType.PARTIAL)
        assert decision == ResponseDecision.ESCALATE

    def test_partial_response_normalized(self):
        """PARTIAL response is normalized to ESCALATE."""
        from HUMANOID_HUNTER.executor_response.response_engine import normalize_executor_response
        from HUMANOID_HUNTER.executor_response.response_types import ExecutorResponseType, ResponseDecision
        from HUMANOID_HUNTER.executor_response.response_context import ExecutorRawResponse

        raw = ExecutorRawResponse(
            executor_id="EXEC-001",
            instruction_hash="HASH-001",
            raw_payload={"partial": True},
            reported_status=ExecutorResponseType.PARTIAL
        )

        result = normalize_executor_response(raw, expected_hash="HASH-001")
        assert result.decision == ResponseDecision.ESCALATE


class TestFailureHandling:
    """Test failure response handling."""

    def test_failure_becomes_reject(self):
        """FAILURE response → REJECT decision."""
        from HUMANOID_HUNTER.executor_response.response_engine import decide_response_outcome
        from HUMANOID_HUNTER.executor_response.response_types import ExecutorResponseType, ResponseDecision

        decision = decide_response_outcome(ExecutorResponseType.FAILURE)
        assert decision == ResponseDecision.REJECT

    def test_failure_response_normalized(self):
        """FAILURE response is normalized correctly."""
        from HUMANOID_HUNTER.executor_response.response_engine import normalize_executor_response
        from HUMANOID_HUNTER.executor_response.response_types import ExecutorResponseType, ResponseDecision
        from HUMANOID_HUNTER.executor_response.response_context import ExecutorRawResponse

        raw = ExecutorRawResponse(
            executor_id="EXEC-001",
            instruction_hash="HASH-001",
            raw_payload=None,
            reported_status=ExecutorResponseType.FAILURE
        )

        result = normalize_executor_response(raw, expected_hash="HASH-001")
        assert result.decision == ResponseDecision.REJECT
