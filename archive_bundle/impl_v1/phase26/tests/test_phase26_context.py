"""
Phase-26 Context Tests.

Tests for FROZEN dataclasses:
- ExecutionReadinessContext: 5 fields
- ReadinessResult: 3 fields

Tests enforce:
- Immutability (FrozenInstanceError on mutation)
- Correct field counts
- Valid construction
"""
import pytest
from dataclasses import FrozenInstanceError

from impl_v1.phase26.phase26_types import ReadinessStatus, ReadinessBlocker
from impl_v1.phase26.phase26_context import (
    ExecutionReadinessContext,
    ReadinessResult,
)


class TestExecutionReadinessContextFrozen:
    """Tests for ExecutionReadinessContext frozen dataclass."""

    def test_execution_readiness_context_has_5_fields(self) -> None:
        """ExecutionReadinessContext must have exactly 5 fields."""
        from dataclasses import fields
        assert len(fields(ExecutionReadinessContext)) == 5

    def test_execution_readiness_context_can_be_created(self) -> None:
        """ExecutionReadinessContext can be created with valid data."""
        context = ExecutionReadinessContext(
            authorization_ok=True,
            intent_bound=True,
            handshake_valid=True,
            observation_valid=True,
            human_decision_final=True
        )
        assert context.authorization_ok is True
        assert context.intent_bound is True

    def test_execution_readiness_context_is_immutable_authorization(self) -> None:
        """ExecutionReadinessContext.authorization_ok cannot be mutated."""
        context = ExecutionReadinessContext(
            authorization_ok=True,
            intent_bound=True,
            handshake_valid=True,
            observation_valid=True,
            human_decision_final=True
        )
        with pytest.raises(FrozenInstanceError):
            context.authorization_ok = False  # type: ignore

    def test_execution_readiness_context_is_immutable_intent(self) -> None:
        """ExecutionReadinessContext.intent_bound cannot be mutated."""
        context = ExecutionReadinessContext(
            authorization_ok=True,
            intent_bound=True,
            handshake_valid=True,
            observation_valid=True,
            human_decision_final=True
        )
        with pytest.raises(FrozenInstanceError):
            context.intent_bound = False  # type: ignore

    def test_execution_readiness_context_is_immutable_handshake(self) -> None:
        """ExecutionReadinessContext.handshake_valid cannot be mutated."""
        context = ExecutionReadinessContext(
            authorization_ok=True,
            intent_bound=True,
            handshake_valid=True,
            observation_valid=True,
            human_decision_final=True
        )
        with pytest.raises(FrozenInstanceError):
            context.handshake_valid = False  # type: ignore


class TestReadinessResultFrozen:
    """Tests for ReadinessResult frozen dataclass."""

    def test_readiness_result_has_3_fields(self) -> None:
        """ReadinessResult must have exactly 3 fields."""
        from dataclasses import fields
        assert len(fields(ReadinessResult)) == 3

    def test_readiness_result_can_be_created(self) -> None:
        """ReadinessResult can be created with valid data."""
        result = ReadinessResult(
            status=ReadinessStatus.READY,
            blockers=(),
            evaluated_at="2026-01-26T12:00:00Z"
        )
        assert result.status == ReadinessStatus.READY
        assert result.blockers == ()

    def test_readiness_result_is_immutable_status(self) -> None:
        """ReadinessResult.status cannot be mutated."""
        result = ReadinessResult(
            status=ReadinessStatus.READY,
            blockers=(),
            evaluated_at="2026-01-26T12:00:00Z"
        )
        with pytest.raises(FrozenInstanceError):
            result.status = ReadinessStatus.BLOCKED  # type: ignore

    def test_readiness_result_is_immutable_blockers(self) -> None:
        """ReadinessResult.blockers cannot be mutated."""
        result = ReadinessResult(
            status=ReadinessStatus.NOT_READY,
            blockers=(ReadinessBlocker.MISSING_AUTHORIZATION,),
            evaluated_at="2026-01-26T12:00:00Z"
        )
        with pytest.raises(FrozenInstanceError):
            result.blockers = ()  # type: ignore

    def test_readiness_result_is_immutable_evaluated_at(self) -> None:
        """ReadinessResult.evaluated_at cannot be mutated."""
        result = ReadinessResult(
            status=ReadinessStatus.READY,
            blockers=(),
            evaluated_at="2026-01-26T12:00:00Z"
        )
        with pytest.raises(FrozenInstanceError):
            result.evaluated_at = "TAMPERED"  # type: ignore
