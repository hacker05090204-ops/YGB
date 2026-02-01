"""
Phase-30 Context Tests.

Tests for FROZEN dataclasses:
- ExecutorRawResponse: 6 fields
- NormalizedExecutionResult: 7 fields

Tests enforce:
- Immutability (FrozenInstanceError on mutation)
- Correct field counts
- Valid construction
"""
import pytest
from dataclasses import FrozenInstanceError

from impl_v1.phase30.phase30_types import ExecutorResponseType, ResponseDecision
from impl_v1.phase30.phase30_context import (
    ExecutorRawResponse,
    NormalizedExecutionResult,
)


class TestExecutorRawResponseFrozen:
    """Tests for ExecutorRawResponse frozen dataclass."""

    def test_executor_raw_response_has_6_fields(self) -> None:
        """ExecutorRawResponse must have exactly 6 fields."""
        from dataclasses import fields
        assert len(fields(ExecutorRawResponse)) == 6

    def test_executor_raw_response_can_be_created(self) -> None:
        """ExecutorRawResponse can be created with valid data."""
        response = ExecutorRawResponse(
            response_id="RESPONSE-12345678",
            executor_id="EXECUTOR-001",
            response_type=ExecutorResponseType.SUCCESS,
            raw_data=b"test data",
            timestamp="2026-01-26T12:00:00Z",
            elapsed_ms=100
        )
        assert response.response_id == "RESPONSE-12345678"
        assert response.response_type == ExecutorResponseType.SUCCESS

    def test_executor_raw_response_is_immutable_response_id(self) -> None:
        """ExecutorRawResponse.response_id cannot be mutated."""
        response = ExecutorRawResponse(
            response_id="RESPONSE-12345678",
            executor_id="EXECUTOR-001",
            response_type=ExecutorResponseType.SUCCESS,
            raw_data=b"test data",
            timestamp="2026-01-26T12:00:00Z",
            elapsed_ms=100
        )
        with pytest.raises(FrozenInstanceError):
            response.response_id = "NEW-ID"  # type: ignore

    def test_executor_raw_response_is_immutable_raw_data(self) -> None:
        """ExecutorRawResponse.raw_data cannot be mutated."""
        response = ExecutorRawResponse(
            response_id="RESPONSE-12345678",
            executor_id="EXECUTOR-001",
            response_type=ExecutorResponseType.SUCCESS,
            raw_data=b"test data",
            timestamp="2026-01-26T12:00:00Z",
            elapsed_ms=100
        )
        with pytest.raises(FrozenInstanceError):
            response.raw_data = b"new data"  # type: ignore

    def test_executor_raw_response_is_immutable_elapsed_ms(self) -> None:
        """ExecutorRawResponse.elapsed_ms cannot be mutated."""
        response = ExecutorRawResponse(
            response_id="RESPONSE-12345678",
            executor_id="EXECUTOR-001",
            response_type=ExecutorResponseType.SUCCESS,
            raw_data=b"test data",
            timestamp="2026-01-26T12:00:00Z",
            elapsed_ms=100
        )
        with pytest.raises(FrozenInstanceError):
            response.elapsed_ms = 999  # type: ignore


class TestNormalizedExecutionResultFrozen:
    """Tests for NormalizedExecutionResult frozen dataclass."""

    def test_normalized_execution_result_has_7_fields(self) -> None:
        """NormalizedExecutionResult must have exactly 7 fields."""
        from dataclasses import fields
        assert len(fields(NormalizedExecutionResult)) == 7

    def test_normalized_execution_result_can_be_created(self) -> None:
        """NormalizedExecutionResult can be created with valid data."""
        result = NormalizedExecutionResult(
            result_id="RESULT-12345678",
            response_id="RESPONSE-12345678",
            response_type=ExecutorResponseType.SUCCESS,
            decision=ResponseDecision.ACCEPT,
            confidence=0.85,
            reason="Executor completed successfully",
            requires_human=False
        )
        assert result.result_id == "RESULT-12345678"
        assert result.decision == ResponseDecision.ACCEPT
        assert result.confidence == 0.85

    def test_normalized_execution_result_is_immutable_result_id(self) -> None:
        """NormalizedExecutionResult.result_id cannot be mutated."""
        result = NormalizedExecutionResult(
            result_id="RESULT-12345678",
            response_id="RESPONSE-12345678",
            response_type=ExecutorResponseType.SUCCESS,
            decision=ResponseDecision.ACCEPT,
            confidence=0.85,
            reason="Test",
            requires_human=False
        )
        with pytest.raises(FrozenInstanceError):
            result.result_id = "NEW-ID"  # type: ignore

    def test_normalized_execution_result_is_immutable_decision(self) -> None:
        """NormalizedExecutionResult.decision cannot be mutated."""
        result = NormalizedExecutionResult(
            result_id="RESULT-12345678",
            response_id="RESPONSE-12345678",
            response_type=ExecutorResponseType.SUCCESS,
            decision=ResponseDecision.ACCEPT,
            confidence=0.85,
            reason="Test",
            requires_human=False
        )
        with pytest.raises(FrozenInstanceError):
            result.decision = ResponseDecision.REJECT  # type: ignore

    def test_normalized_execution_result_is_immutable_confidence(self) -> None:
        """NormalizedExecutionResult.confidence cannot be mutated."""
        result = NormalizedExecutionResult(
            result_id="RESULT-12345678",
            response_id="RESPONSE-12345678",
            response_type=ExecutorResponseType.SUCCESS,
            decision=ResponseDecision.ACCEPT,
            confidence=0.85,
            reason="Test",
            requires_human=False
        )
        with pytest.raises(FrozenInstanceError):
            result.confidence = 0.99  # type: ignore

    def test_normalized_execution_result_is_immutable_requires_human(self) -> None:
        """NormalizedExecutionResult.requires_human cannot be mutated."""
        result = NormalizedExecutionResult(
            result_id="RESULT-12345678",
            response_id="RESPONSE-12345678",
            response_type=ExecutorResponseType.SUCCESS,
            decision=ResponseDecision.ACCEPT,
            confidence=0.85,
            reason="Test",
            requires_human=False
        )
        with pytest.raises(FrozenInstanceError):
            result.requires_human = True  # type: ignore
