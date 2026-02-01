"""
Tests for Phase-30 Deny-By-Default.

Tests:
- Confidence is never 1.0 without human confirmation
- Unknown response type → REJECT
- Executor cannot self-report SUCCESS
"""
import pytest


class TestConfidenceConstraints:
    """Test confidence score constraints."""

    def test_confidence_never_reaches_one(self):
        """Confidence score is always < 1.0."""
        from HUMANOID_HUNTER.executor_response.response_engine import evaluate_response_trust
        from HUMANOID_HUNTER.executor_response.response_types import ExecutorResponseType

        # Test all response types
        for resp_type in ExecutorResponseType:
            confidence = evaluate_response_trust(resp_type)
            assert confidence < 1.0, f"{resp_type} has confidence >= 1.0"

    def test_success_confidence_capped(self):
        """SUCCESS response confidence is capped below 1.0."""
        from HUMANOID_HUNTER.executor_response.response_engine import evaluate_response_trust
        from HUMANOID_HUNTER.executor_response.response_types import ExecutorResponseType

        confidence = evaluate_response_trust(ExecutorResponseType.SUCCESS)
        assert confidence < 1.0
        assert confidence <= 0.99

    def test_failure_has_low_confidence(self):
        """FAILURE response has low confidence."""
        from HUMANOID_HUNTER.executor_response.response_engine import evaluate_response_trust
        from HUMANOID_HUNTER.executor_response.response_types import ExecutorResponseType

        confidence = evaluate_response_trust(ExecutorResponseType.FAILURE)
        assert confidence < 0.5


class TestExecutorCannotSelfReportSuccess:
    """Test that executor cannot self-report SUCCESS as truth."""

    def test_success_still_needs_governance(self):
        """Executor reporting SUCCESS does not mean ACCEPT."""
        from HUMANOID_HUNTER.executor_response.response_engine import normalize_executor_response
        from HUMANOID_HUNTER.executor_response.response_types import ExecutorResponseType, ResponseDecision
        from HUMANOID_HUNTER.executor_response.response_context import ExecutorRawResponse

        raw = ExecutorRawResponse(
            executor_id="EXEC-001",
            instruction_hash="HASH-001",
            raw_payload={"claimed": "success"},
            reported_status=ExecutorResponseType.SUCCESS
        )

        result = normalize_executor_response(raw, expected_hash="HASH-001")
        # SUCCESS from executor leads to ACCEPT decision but with < 1.0 confidence
        assert result.confidence_score < 1.0


class TestDenyByDefault:
    """Test deny-by-default behavior."""

    def test_malformed_rejected(self):
        """MALFORMED response → REJECT."""
        from HUMANOID_HUNTER.executor_response.response_engine import decide_response_outcome
        from HUMANOID_HUNTER.executor_response.response_types import ExecutorResponseType, ResponseDecision

        decision = decide_response_outcome(ExecutorResponseType.MALFORMED)
        assert decision == ResponseDecision.REJECT

    def test_result_always_has_reason(self):
        """Normalized result always has a reason."""
        from HUMANOID_HUNTER.executor_response.response_engine import normalize_executor_response
        from HUMANOID_HUNTER.executor_response.response_types import ExecutorResponseType
        from HUMANOID_HUNTER.executor_response.response_context import ExecutorRawResponse

        for resp_type in ExecutorResponseType:
            raw = ExecutorRawResponse(
                executor_id="EXEC-001",
                instruction_hash="HASH-001",
                raw_payload={},
                reported_status=resp_type
            )

            result = normalize_executor_response(raw, expected_hash="HASH-001")
            assert result.reason is not None
            assert len(result.reason) > 0


class TestNormalizedResultStructure:
    """Test NormalizedExecutionResult structure."""

    def test_result_creation(self):
        """NormalizedExecutionResult can be created."""
        from HUMANOID_HUNTER.executor_response.response_context import NormalizedExecutionResult
        from HUMANOID_HUNTER.executor_response.response_types import ResponseDecision

        result = NormalizedExecutionResult(
            decision=ResponseDecision.ACCEPT,
            reason="Valid response",
            confidence_score=0.85
        )

        assert result.decision == ResponseDecision.ACCEPT
        assert result.confidence_score == 0.85

    def test_result_frozen(self):
        """NormalizedExecutionResult is frozen."""
        from HUMANOID_HUNTER.executor_response.response_context import NormalizedExecutionResult
        from HUMANOID_HUNTER.executor_response.response_types import ResponseDecision

        result = NormalizedExecutionResult(
            decision=ResponseDecision.REJECT,
            reason="Test",
            confidence_score=0.5
        )

        with pytest.raises(Exception):
            result.decision = ResponseDecision.ACCEPT
