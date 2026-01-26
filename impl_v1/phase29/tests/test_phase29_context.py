"""
Phase-29 Context Tests.

Tests for FROZEN dataclasses:
- ExecutionLoopContext: 6 fields
- LoopTransitionResult: 5 fields

Tests enforce:
- Immutability (FrozenInstanceError on mutation)
- Correct field counts
- Valid construction
"""
import pytest
from dataclasses import FrozenInstanceError

from impl_v1.phase29.phase29_types import ExecutionLoopState, LoopTransition
from impl_v1.phase29.phase29_context import (
    ExecutionLoopContext,
    LoopTransitionResult,
)


class TestExecutionLoopContextFrozen:
    """Tests for ExecutionLoopContext frozen dataclass."""

    def test_execution_loop_context_has_6_fields(self) -> None:
        """ExecutionLoopContext must have exactly 6 fields."""
        from dataclasses import fields
        assert len(fields(ExecutionLoopContext)) == 6

    def test_execution_loop_context_can_be_created(self) -> None:
        """ExecutionLoopContext can be created with valid data."""
        context = ExecutionLoopContext(
            loop_id="LOOP-12345678",
            current_state=ExecutionLoopState.INITIALIZED,
            executor_id="EXECUTOR-001",
            envelope_hash="hash123",
            created_at="2026-01-26T12:00:00Z",
            iteration_count=0
        )
        assert context.loop_id == "LOOP-12345678"
        assert context.current_state == ExecutionLoopState.INITIALIZED

    def test_execution_loop_context_is_immutable_loop_id(self) -> None:
        """ExecutionLoopContext.loop_id cannot be mutated."""
        context = ExecutionLoopContext(
            loop_id="LOOP-12345678",
            current_state=ExecutionLoopState.INITIALIZED,
            executor_id="EXECUTOR-001",
            envelope_hash="hash123",
            created_at="2026-01-26T12:00:00Z",
            iteration_count=0
        )
        with pytest.raises(FrozenInstanceError):
            context.loop_id = "NEW-ID"  # type: ignore

    def test_execution_loop_context_is_immutable_current_state(self) -> None:
        """ExecutionLoopContext.current_state cannot be mutated."""
        context = ExecutionLoopContext(
            loop_id="LOOP-12345678",
            current_state=ExecutionLoopState.INITIALIZED,
            executor_id="EXECUTOR-001",
            envelope_hash="hash123",
            created_at="2026-01-26T12:00:00Z",
            iteration_count=0
        )
        with pytest.raises(FrozenInstanceError):
            context.current_state = ExecutionLoopState.HALTED  # type: ignore

    def test_execution_loop_context_is_immutable_iteration_count(self) -> None:
        """ExecutionLoopContext.iteration_count cannot be mutated."""
        context = ExecutionLoopContext(
            loop_id="LOOP-12345678",
            current_state=ExecutionLoopState.INITIALIZED,
            executor_id="EXECUTOR-001",
            envelope_hash="hash123",
            created_at="2026-01-26T12:00:00Z",
            iteration_count=0
        )
        with pytest.raises(FrozenInstanceError):
            context.iteration_count = 99  # type: ignore


class TestLoopTransitionResultFrozen:
    """Tests for LoopTransitionResult frozen dataclass."""

    def test_loop_transition_result_has_5_fields(self) -> None:
        """LoopTransitionResult must have exactly 5 fields."""
        from dataclasses import fields
        assert len(fields(LoopTransitionResult)) == 5

    def test_loop_transition_result_can_be_created(self) -> None:
        """LoopTransitionResult can be created with valid data."""
        result = LoopTransitionResult(
            transition=LoopTransition.INIT,
            from_state=ExecutionLoopState.INITIALIZED,
            to_state=ExecutionLoopState.READY,
            is_valid=True,
            reason="Valid transition"
        )
        assert result.transition == LoopTransition.INIT
        assert result.is_valid is True

    def test_loop_transition_result_is_immutable_transition(self) -> None:
        """LoopTransitionResult.transition cannot be mutated."""
        result = LoopTransitionResult(
            transition=LoopTransition.INIT,
            from_state=ExecutionLoopState.INITIALIZED,
            to_state=ExecutionLoopState.READY,
            is_valid=True,
            reason="Test"
        )
        with pytest.raises(FrozenInstanceError):
            result.transition = LoopTransition.HALT  # type: ignore

    def test_loop_transition_result_is_immutable_is_valid(self) -> None:
        """LoopTransitionResult.is_valid cannot be mutated."""
        result = LoopTransitionResult(
            transition=LoopTransition.INIT,
            from_state=ExecutionLoopState.INITIALIZED,
            to_state=ExecutionLoopState.READY,
            is_valid=True,
            reason="Test"
        )
        with pytest.raises(FrozenInstanceError):
            result.is_valid = False  # type: ignore

    def test_loop_transition_result_is_immutable_to_state(self) -> None:
        """LoopTransitionResult.to_state cannot be mutated."""
        result = LoopTransitionResult(
            transition=LoopTransition.INIT,
            from_state=ExecutionLoopState.INITIALIZED,
            to_state=ExecutionLoopState.READY,
            is_valid=True,
            reason="Test"
        )
        with pytest.raises(FrozenInstanceError):
            result.to_state = ExecutionLoopState.HALTED  # type: ignore
