"""
Phase-30 Engine Tests.

Tests for VALIDATION-ONLY functions:
- validate_executor_response
- normalize_response
- evaluate_response_trust
- decide_response_outcome

Tests enforce:
- Deny-by-default (None, empty, malformed)
- Negative paths > positive paths
- Decision table correctness
- Confidence never reaches 1.0 without human
"""
import pytest

from impl_v1.phase30.phase30_types import (
    ExecutorResponseType,
    ResponseDecision,
)
from impl_v1.phase30.phase30_context import (
    ExecutorRawResponse,
    NormalizedExecutionResult,
)
from impl_v1.phase30.phase30_engine import (
    validate_executor_response,
    normalize_response,
    evaluate_response_trust,
    decide_response_outcome,
)


# --- Helpers ---

def _make_valid_response(
    response_id: str = "RESPONSE-12345678",
    executor_id: str = "EXECUTOR-001",
    response_type: ExecutorResponseType = ExecutorResponseType.SUCCESS,
    raw_data: bytes = b"test data",
    timestamp: str = "2026-01-26T12:00:00Z",
    elapsed_ms: int = 100
) -> ExecutorRawResponse:
    return ExecutorRawResponse(
        response_id=response_id,
        executor_id=executor_id,
        response_type=response_type,
        raw_data=raw_data,
        timestamp=timestamp,
        elapsed_ms=elapsed_ms
    )


def _make_valid_result(
    result_id: str = "RESULT-12345678",
    response_id: str = "RESPONSE-12345678",
    response_type: ExecutorResponseType = ExecutorResponseType.SUCCESS,
    decision: ResponseDecision = ResponseDecision.ACCEPT,
    confidence: float = 0.85,
    reason: str = "Test reason",
    requires_human: bool = False
) -> NormalizedExecutionResult:
    return NormalizedExecutionResult(
        result_id=result_id,
        response_id=response_id,
        response_type=response_type,
        decision=decision,
        confidence=confidence,
        reason=reason,
        requires_human=requires_human
    )


# ============================================================================
# validate_executor_response TESTS
# ============================================================================

class TestValidateExecutorResponseDenyByDefault:
    """Deny-by-default tests for validate_executor_response."""

    def test_none_returns_false(self) -> None:
        """None → False."""
        assert validate_executor_response(None) is False

    def test_empty_response_id_returns_false(self) -> None:
        """Empty response_id → False."""
        response = _make_valid_response(response_id="")
        assert validate_executor_response(response) is False

    def test_invalid_response_id_format_returns_false(self) -> None:
        """Invalid response_id format → False."""
        response = _make_valid_response(response_id="INVALID-123")
        assert validate_executor_response(response) is False

    def test_empty_executor_id_returns_false(self) -> None:
        """Empty executor_id → False."""
        response = _make_valid_response(executor_id="")
        assert validate_executor_response(response) is False

    def test_invalid_executor_id_format_returns_false(self) -> None:
        """Invalid executor_id format → False."""
        response = _make_valid_response(executor_id="INVALID")
        assert validate_executor_response(response) is False

    def test_non_response_type_returns_false(self) -> None:
        """Non-ExecutorResponseType → False."""
        response = ExecutorRawResponse(
            response_id="RESPONSE-12345678",
            executor_id="EXECUTOR-001",
            response_type="SUCCESS",  # type: ignore
            raw_data=b"test",
            timestamp="2026-01-26T12:00:00Z",
            elapsed_ms=100
        )
        assert validate_executor_response(response) is False

    def test_non_bytes_raw_data_returns_false(self) -> None:
        """Non-bytes raw_data → False."""
        response = ExecutorRawResponse(
            response_id="RESPONSE-12345678",
            executor_id="EXECUTOR-001",
            response_type=ExecutorResponseType.SUCCESS,
            raw_data="not bytes",  # type: ignore
            timestamp="2026-01-26T12:00:00Z",
            elapsed_ms=100
        )
        assert validate_executor_response(response) is False

    def test_empty_timestamp_returns_false(self) -> None:
        """Empty timestamp → False."""
        response = _make_valid_response(timestamp="")
        assert validate_executor_response(response) is False

    def test_whitespace_timestamp_returns_false(self) -> None:
        """Whitespace timestamp → False."""
        response = _make_valid_response(timestamp="   ")
        assert validate_executor_response(response) is False

    def test_negative_elapsed_ms_returns_false(self) -> None:
        """Negative elapsed_ms → False."""
        response = _make_valid_response(elapsed_ms=-1)
        assert validate_executor_response(response) is False

    def test_non_int_elapsed_ms_returns_false(self) -> None:
        """Non-int elapsed_ms → False."""
        response = ExecutorRawResponse(
            response_id="RESPONSE-12345678",
            executor_id="EXECUTOR-001",
            response_type=ExecutorResponseType.SUCCESS,
            raw_data=b"test",
            timestamp="2026-01-26T12:00:00Z",
            elapsed_ms="100"  # type: ignore
        )
        assert validate_executor_response(response) is False


class TestValidateExecutorResponsePositive:
    """Positive tests for validate_executor_response."""

    def test_valid_response_returns_true(self) -> None:
        """Valid response → True."""
        response = _make_valid_response()
        assert validate_executor_response(response) is True

    def test_zero_elapsed_ms_is_valid(self) -> None:
        """Zero elapsed_ms is valid."""
        response = _make_valid_response(elapsed_ms=0)
        assert validate_executor_response(response) is True

    def test_all_response_types_valid(self) -> None:
        """All ExecutorResponseType values are valid."""
        for rt in ExecutorResponseType:
            response = _make_valid_response(response_type=rt)
            assert validate_executor_response(response) is True


# ============================================================================
# normalize_response TESTS
# ============================================================================

class TestNormalizeResponseDenyByDefault:
    """Deny-by-default tests for normalize_response."""

    def test_none_response_returns_none(self) -> None:
        """None response → None."""
        assert normalize_response(None, "RESULT-12345678") is None

    def test_invalid_response_returns_none(self) -> None:
        """Invalid response → None."""
        response = _make_valid_response(response_id="INVALID")
        assert normalize_response(response, "RESULT-12345678") is None

    def test_empty_result_id_returns_none(self) -> None:
        """Empty result_id → None."""
        response = _make_valid_response()
        assert normalize_response(response, "") is None

    def test_invalid_result_id_returns_none(self) -> None:
        """Invalid result_id format → None."""
        response = _make_valid_response()
        assert normalize_response(response, "INVALID-123") is None


class TestNormalizeResponsePositive:
    """Positive tests for normalize_response - decision table."""

    def test_success_returns_accept(self) -> None:
        """SUCCESS → ACCEPT with confidence 0.85."""
        response = _make_valid_response(response_type=ExecutorResponseType.SUCCESS)
        result = normalize_response(response, "RESULT-12345678")
        assert result is not None
        assert result.decision == ResponseDecision.ACCEPT
        assert result.confidence == 0.85
        assert result.requires_human is False

    def test_failure_returns_reject(self) -> None:
        """FAILURE → REJECT with confidence 0.30."""
        response = _make_valid_response(response_type=ExecutorResponseType.FAILURE)
        result = normalize_response(response, "RESULT-12345678")
        assert result is not None
        assert result.decision == ResponseDecision.REJECT
        assert result.confidence == 0.30
        assert result.requires_human is False

    def test_timeout_returns_reject(self) -> None:
        """TIMEOUT → REJECT with confidence 0.20."""
        response = _make_valid_response(response_type=ExecutorResponseType.TIMEOUT)
        result = normalize_response(response, "RESULT-12345678")
        assert result is not None
        assert result.decision == ResponseDecision.REJECT
        assert result.confidence == 0.20
        assert result.requires_human is False

    def test_partial_returns_escalate(self) -> None:
        """PARTIAL → ESCALATE with confidence 0.50."""
        response = _make_valid_response(response_type=ExecutorResponseType.PARTIAL)
        result = normalize_response(response, "RESULT-12345678")
        assert result is not None
        assert result.decision == ResponseDecision.ESCALATE
        assert result.confidence == 0.50
        assert result.requires_human is True

    def test_malformed_returns_reject(self) -> None:
        """MALFORMED → REJECT with confidence 0.10."""
        response = _make_valid_response(response_type=ExecutorResponseType.MALFORMED)
        result = normalize_response(response, "RESULT-12345678")
        assert result is not None
        assert result.decision == ResponseDecision.REJECT
        assert result.confidence == 0.10
        assert result.requires_human is False


# ============================================================================
# evaluate_response_trust TESTS
# ============================================================================

class TestEvaluateResponseTrustDenyByDefault:
    """Deny-by-default tests for evaluate_response_trust."""

    def test_none_returns_zero(self) -> None:
        """None → 0.0."""
        assert evaluate_response_trust(None) == 0.0

    def test_invalid_result_id_returns_zero(self) -> None:
        """Invalid result_id → 0.0."""
        result = _make_valid_result(result_id="INVALID")
        assert evaluate_response_trust(result) == 0.0

    def test_empty_result_id_returns_zero(self) -> None:
        """Empty result_id → 0.0."""
        result = _make_valid_result(result_id="")
        assert evaluate_response_trust(result) == 0.0

    def test_non_response_type_returns_zero(self) -> None:
        """Non-ExecutorResponseType → 0.0."""
        result = NormalizedExecutionResult(
            result_id="RESULT-12345678",
            response_id="RESPONSE-12345678",
            response_type="SUCCESS",  # type: ignore
            decision=ResponseDecision.ACCEPT,
            confidence=0.85,
            reason="Test",
            requires_human=False
        )
        assert evaluate_response_trust(result) == 0.0

    def test_non_decision_type_returns_zero(self) -> None:
        """Non-ResponseDecision → 0.0."""
        result = NormalizedExecutionResult(
            result_id="RESULT-12345678",
            response_id="RESPONSE-12345678",
            response_type=ExecutorResponseType.SUCCESS,
            decision="ACCEPT",  # type: ignore
            confidence=0.85,
            reason="Test",
            requires_human=False
        )
        assert evaluate_response_trust(result) == 0.0

    def test_non_numeric_confidence_returns_zero(self) -> None:
        """Non-numeric confidence → 0.0."""
        result = NormalizedExecutionResult(
            result_id="RESULT-12345678",
            response_id="RESPONSE-12345678",
            response_type=ExecutorResponseType.SUCCESS,
            decision=ResponseDecision.ACCEPT,
            confidence="0.85",  # type: ignore
            reason="Test",
            requires_human=False
        )
        assert evaluate_response_trust(result) == 0.0


class TestEvaluateResponseTrustPositive:
    """Positive tests for evaluate_response_trust."""

    def test_returns_confidence_when_valid(self) -> None:
        """Returns confidence for valid result."""
        result = _make_valid_result(confidence=0.85)
        assert evaluate_response_trust(result) == 0.85

    def test_never_returns_1_0(self) -> None:
        """Confidence NEVER reaches 1.0 without human."""
        result = _make_valid_result(confidence=1.0)
        trust = evaluate_response_trust(result)
        assert trust < 1.0
        assert trust == 0.99

    def test_caps_high_confidence_at_0_99(self) -> None:
        """High confidence is capped at 0.99."""
        result = _make_valid_result(confidence=0.999)
        assert evaluate_response_trust(result) == 0.99

    def test_low_confidence_not_modified(self) -> None:
        """Low confidence is not modified."""
        result = _make_valid_result(confidence=0.10)
        assert evaluate_response_trust(result) == 0.10


# ============================================================================
# decide_response_outcome TESTS
# ============================================================================

class TestDecideResponseOutcomeDenyByDefault:
    """Deny-by-default tests for decide_response_outcome."""

    def test_none_returns_reject(self) -> None:
        """None → REJECT."""
        assert decide_response_outcome(None) == ResponseDecision.REJECT

    def test_invalid_response_returns_reject(self) -> None:
        """Invalid response → REJECT."""
        response = _make_valid_response(response_id="INVALID")
        assert decide_response_outcome(response) == ResponseDecision.REJECT


class TestDecideResponseOutcomePositive:
    """Positive tests for decide_response_outcome - decision table."""

    def test_success_returns_accept(self) -> None:
        """SUCCESS → ACCEPT."""
        response = _make_valid_response(response_type=ExecutorResponseType.SUCCESS)
        assert decide_response_outcome(response) == ResponseDecision.ACCEPT

    def test_failure_returns_reject(self) -> None:
        """FAILURE → REJECT."""
        response = _make_valid_response(response_type=ExecutorResponseType.FAILURE)
        assert decide_response_outcome(response) == ResponseDecision.REJECT

    def test_timeout_returns_reject(self) -> None:
        """TIMEOUT → REJECT."""
        response = _make_valid_response(response_type=ExecutorResponseType.TIMEOUT)
        assert decide_response_outcome(response) == ResponseDecision.REJECT

    def test_partial_returns_escalate(self) -> None:
        """PARTIAL → ESCALATE."""
        response = _make_valid_response(response_type=ExecutorResponseType.PARTIAL)
        assert decide_response_outcome(response) == ResponseDecision.ESCALATE

    def test_malformed_returns_reject(self) -> None:
        """MALFORMED → REJECT."""
        response = _make_valid_response(response_type=ExecutorResponseType.MALFORMED)
        assert decide_response_outcome(response) == ResponseDecision.REJECT
