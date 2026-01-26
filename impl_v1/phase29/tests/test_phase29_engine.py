"""
Phase-29 Engine Tests.

Tests for VALIDATION-ONLY functions:
- validate_loop_state
- validate_transition
- get_allowed_transitions
- get_next_state
- is_terminal_state

Tests enforce:
- Deny-by-default (None, empty, malformed)
- Invalid transitions > valid transitions
- State machine correctness
"""
import pytest

from impl_v1.phase29.phase29_types import (
    ExecutionLoopState,
    LoopTransition,
)
from impl_v1.phase29.phase29_context import (
    ExecutionLoopContext,
    LoopTransitionResult,
)
from impl_v1.phase29.phase29_engine import (
    validate_loop_state,
    validate_transition,
    get_allowed_transitions,
    get_next_state,
    is_terminal_state,
)


# --- Helpers ---

def _make_valid_context(
    loop_id: str = "LOOP-12345678",
    current_state: ExecutionLoopState = ExecutionLoopState.INITIALIZED,
    executor_id: str = "EXECUTOR-001",
    envelope_hash: str = "hash123",
    created_at: str = "2026-01-26T12:00:00Z",
    iteration_count: int = 0
) -> ExecutionLoopContext:
    return ExecutionLoopContext(
        loop_id=loop_id,
        current_state=current_state,
        executor_id=executor_id,
        envelope_hash=envelope_hash,
        created_at=created_at,
        iteration_count=iteration_count
    )


# ============================================================================
# validate_loop_state TESTS
# ============================================================================

class TestValidateLoopStateDenyByDefault:
    """Deny-by-default tests for validate_loop_state."""

    def test_none_returns_false(self) -> None:
        """None → False."""
        assert validate_loop_state(None) is False

    def test_empty_loop_id_returns_false(self) -> None:
        """Empty loop_id → False."""
        context = _make_valid_context(loop_id="")
        assert validate_loop_state(context) is False

    def test_invalid_loop_id_format_returns_false(self) -> None:
        """Invalid loop_id format → False."""
        context = _make_valid_context(loop_id="INVALID-123")
        assert validate_loop_state(context) is False

    def test_non_execution_loop_state_returns_false(self) -> None:
        """Non-ExecutionLoopState → False."""
        context = ExecutionLoopContext(
            loop_id="LOOP-12345678",
            current_state="INITIALIZED",  # type: ignore
            executor_id="EXECUTOR-001",
            envelope_hash="hash123",
            created_at="2026-01-26T12:00:00Z",
            iteration_count=0
        )
        assert validate_loop_state(context) is False

    def test_empty_executor_id_returns_false(self) -> None:
        """Empty executor_id → False."""
        context = _make_valid_context(executor_id="")
        assert validate_loop_state(context) is False

    def test_invalid_executor_id_format_returns_false(self) -> None:
        """Invalid executor_id format → False."""
        context = _make_valid_context(executor_id="INVALID")
        assert validate_loop_state(context) is False

    def test_empty_envelope_hash_returns_false(self) -> None:
        """Empty envelope_hash → False."""
        context = _make_valid_context(envelope_hash="")
        assert validate_loop_state(context) is False

    def test_whitespace_envelope_hash_returns_false(self) -> None:
        """Whitespace envelope_hash → False."""
        context = _make_valid_context(envelope_hash="   ")
        assert validate_loop_state(context) is False

    def test_empty_created_at_returns_false(self) -> None:
        """Empty created_at → False."""
        context = _make_valid_context(created_at="")
        assert validate_loop_state(context) is False

    def test_whitespace_created_at_returns_false(self) -> None:
        """Whitespace created_at → False."""
        context = _make_valid_context(created_at="   ")
        assert validate_loop_state(context) is False

    def test_negative_iteration_count_returns_false(self) -> None:
        """Negative iteration_count → False."""
        context = _make_valid_context(iteration_count=-1)
        assert validate_loop_state(context) is False

    def test_non_int_iteration_count_returns_false(self) -> None:
        """Non-int iteration_count → False."""
        context = ExecutionLoopContext(
            loop_id="LOOP-12345678",
            current_state=ExecutionLoopState.INITIALIZED,
            executor_id="EXECUTOR-001",
            envelope_hash="hash123",
            created_at="2026-01-26T12:00:00Z",
            iteration_count="0"  # type: ignore
        )
        assert validate_loop_state(context) is False


class TestValidateLoopStatePositive:
    """Positive tests for validate_loop_state."""

    def test_valid_context_returns_true(self) -> None:
        """Valid context → True."""
        context = _make_valid_context()
        assert validate_loop_state(context) is True

    def test_zero_iteration_count_is_valid(self) -> None:
        """Zero iteration_count is valid."""
        context = _make_valid_context(iteration_count=0)
        assert validate_loop_state(context) is True

    def test_all_states_valid(self) -> None:
        """All ExecutionLoopState values are valid."""
        for state in ExecutionLoopState:
            context = _make_valid_context(current_state=state)
            assert validate_loop_state(context) is True


# ============================================================================
# validate_transition TESTS
# ============================================================================

class TestValidateTransitionDenyByDefault:
    """Deny-by-default tests for validate_transition."""

    def test_none_context_returns_invalid(self) -> None:
        """None context → Invalid result."""
        result = validate_transition(None, LoopTransition.INIT)
        assert result.is_valid is False
        assert result.to_state == ExecutionLoopState.HALTED

    def test_invalid_context_returns_invalid(self) -> None:
        """Invalid context → Invalid result."""
        context = _make_valid_context(loop_id="INVALID")
        result = validate_transition(context, LoopTransition.INIT)
        assert result.is_valid is False
        assert result.to_state == ExecutionLoopState.HALTED

    def test_none_transition_returns_invalid(self) -> None:
        """None transition → Invalid result."""
        context = _make_valid_context()
        result = validate_transition(context, None)
        assert result.is_valid is False
        assert result.to_state == ExecutionLoopState.HALTED

    def test_non_loop_transition_returns_invalid(self) -> None:
        """Non-LoopTransition → Invalid result."""
        context = _make_valid_context()
        result = validate_transition(context, "INIT")  # type: ignore
        assert result.is_valid is False
        assert result.to_state == ExecutionLoopState.HALTED


class TestValidateTransitionInvalidTransitions:
    """Tests for invalid state transitions (must > valid)."""

    def test_initialized_dispatch_invalid(self) -> None:
        """INITIALIZED + DISPATCH → Invalid (must INIT first)."""
        context = _make_valid_context(current_state=ExecutionLoopState.INITIALIZED)
        result = validate_transition(context, LoopTransition.DISPATCH)
        assert result.is_valid is False
        assert result.to_state == ExecutionLoopState.HALTED

    def test_initialized_receive_invalid(self) -> None:
        """INITIALIZED + RECEIVE → Invalid."""
        context = _make_valid_context(current_state=ExecutionLoopState.INITIALIZED)
        result = validate_transition(context, LoopTransition.RECEIVE)
        assert result.is_valid is False
        assert result.to_state == ExecutionLoopState.HALTED

    def test_ready_init_invalid(self) -> None:
        """READY + INIT → Invalid (already initialized)."""
        context = _make_valid_context(current_state=ExecutionLoopState.READY)
        result = validate_transition(context, LoopTransition.INIT)
        assert result.is_valid is False
        assert result.to_state == ExecutionLoopState.HALTED

    def test_ready_receive_invalid(self) -> None:
        """READY + RECEIVE → Invalid (nothing dispatched)."""
        context = _make_valid_context(current_state=ExecutionLoopState.READY)
        result = validate_transition(context, LoopTransition.RECEIVE)
        assert result.is_valid is False
        assert result.to_state == ExecutionLoopState.HALTED

    def test_dispatched_init_invalid(self) -> None:
        """DISPATCHED + INIT → Invalid."""
        context = _make_valid_context(current_state=ExecutionLoopState.DISPATCHED)
        result = validate_transition(context, LoopTransition.INIT)
        assert result.is_valid is False
        assert result.to_state == ExecutionLoopState.HALTED

    def test_dispatched_dispatch_invalid(self) -> None:
        """DISPATCHED + DISPATCH → Invalid (already dispatched)."""
        context = _make_valid_context(current_state=ExecutionLoopState.DISPATCHED)
        result = validate_transition(context, LoopTransition.DISPATCH)
        assert result.is_valid is False
        assert result.to_state == ExecutionLoopState.HALTED

    def test_awaiting_init_invalid(self) -> None:
        """AWAITING_RESPONSE + INIT → Invalid."""
        context = _make_valid_context(current_state=ExecutionLoopState.AWAITING_RESPONSE)
        result = validate_transition(context, LoopTransition.INIT)
        assert result.is_valid is False
        assert result.to_state == ExecutionLoopState.HALTED

    def test_awaiting_receive_invalid(self) -> None:
        """AWAITING_RESPONSE + RECEIVE → Invalid."""
        context = _make_valid_context(current_state=ExecutionLoopState.AWAITING_RESPONSE)
        result = validate_transition(context, LoopTransition.RECEIVE)
        assert result.is_valid is False
        assert result.to_state == ExecutionLoopState.HALTED

    def test_halted_init_invalid(self) -> None:
        """HALTED + INIT → Invalid (terminal state)."""
        context = _make_valid_context(current_state=ExecutionLoopState.HALTED)
        result = validate_transition(context, LoopTransition.INIT)
        assert result.is_valid is False
        assert result.to_state == ExecutionLoopState.HALTED

    def test_halted_dispatch_invalid(self) -> None:
        """HALTED + DISPATCH → Invalid (terminal state)."""
        context = _make_valid_context(current_state=ExecutionLoopState.HALTED)
        result = validate_transition(context, LoopTransition.DISPATCH)
        assert result.is_valid is False
        assert result.to_state == ExecutionLoopState.HALTED

    def test_halted_receive_invalid(self) -> None:
        """HALTED + RECEIVE → Invalid (terminal state)."""
        context = _make_valid_context(current_state=ExecutionLoopState.HALTED)
        result = validate_transition(context, LoopTransition.RECEIVE)
        assert result.is_valid is False
        assert result.to_state == ExecutionLoopState.HALTED


class TestValidateTransitionValidTransitions:
    """Tests for valid state transitions."""

    def test_initialized_init_valid(self) -> None:
        """INITIALIZED + INIT → READY."""
        context = _make_valid_context(current_state=ExecutionLoopState.INITIALIZED)
        result = validate_transition(context, LoopTransition.INIT)
        assert result.is_valid is True
        assert result.to_state == ExecutionLoopState.READY

    def test_initialized_halt_valid(self) -> None:
        """INITIALIZED + HALT → HALTED."""
        context = _make_valid_context(current_state=ExecutionLoopState.INITIALIZED)
        result = validate_transition(context, LoopTransition.HALT)
        assert result.is_valid is True
        assert result.to_state == ExecutionLoopState.HALTED

    def test_ready_dispatch_valid(self) -> None:
        """READY + DISPATCH → DISPATCHED."""
        context = _make_valid_context(current_state=ExecutionLoopState.READY)
        result = validate_transition(context, LoopTransition.DISPATCH)
        assert result.is_valid is True
        assert result.to_state == ExecutionLoopState.DISPATCHED

    def test_ready_halt_valid(self) -> None:
        """READY + HALT → HALTED."""
        context = _make_valid_context(current_state=ExecutionLoopState.READY)
        result = validate_transition(context, LoopTransition.HALT)
        assert result.is_valid is True
        assert result.to_state == ExecutionLoopState.HALTED

    def test_dispatched_receive_valid(self) -> None:
        """DISPATCHED + RECEIVE → AWAITING_RESPONSE."""
        context = _make_valid_context(current_state=ExecutionLoopState.DISPATCHED)
        result = validate_transition(context, LoopTransition.RECEIVE)
        assert result.is_valid is True
        assert result.to_state == ExecutionLoopState.AWAITING_RESPONSE

    def test_dispatched_halt_valid(self) -> None:
        """DISPATCHED + HALT → HALTED."""
        context = _make_valid_context(current_state=ExecutionLoopState.DISPATCHED)
        result = validate_transition(context, LoopTransition.HALT)
        assert result.is_valid is True
        assert result.to_state == ExecutionLoopState.HALTED

    def test_awaiting_dispatch_valid(self) -> None:
        """AWAITING_RESPONSE + DISPATCH → DISPATCHED (loop back)."""
        context = _make_valid_context(current_state=ExecutionLoopState.AWAITING_RESPONSE)
        result = validate_transition(context, LoopTransition.DISPATCH)
        assert result.is_valid is True
        assert result.to_state == ExecutionLoopState.DISPATCHED

    def test_awaiting_halt_valid(self) -> None:
        """AWAITING_RESPONSE + HALT → HALTED."""
        context = _make_valid_context(current_state=ExecutionLoopState.AWAITING_RESPONSE)
        result = validate_transition(context, LoopTransition.HALT)
        assert result.is_valid is True
        assert result.to_state == ExecutionLoopState.HALTED

    def test_halted_halt_valid(self) -> None:
        """HALTED + HALT → HALTED (stays terminal)."""
        context = _make_valid_context(current_state=ExecutionLoopState.HALTED)
        result = validate_transition(context, LoopTransition.HALT)
        assert result.is_valid is True
        assert result.to_state == ExecutionLoopState.HALTED


# ============================================================================
# get_allowed_transitions TESTS
# ============================================================================

class TestGetAllowedTransitionsDenyByDefault:
    """Deny-by-default tests for get_allowed_transitions."""

    def test_none_returns_empty(self) -> None:
        """None → empty frozenset."""
        result = get_allowed_transitions(None)
        assert result == frozenset()

    def test_non_state_returns_empty(self) -> None:
        """Non-ExecutionLoopState → empty frozenset."""
        result = get_allowed_transitions("INITIALIZED")  # type: ignore
        assert result == frozenset()


class TestGetAllowedTransitionsPositive:
    """Positive tests for get_allowed_transitions."""

    def test_initialized_allows_init_halt(self) -> None:
        """INITIALIZED allows INIT and HALT."""
        result = get_allowed_transitions(ExecutionLoopState.INITIALIZED)
        assert result == frozenset({LoopTransition.INIT, LoopTransition.HALT})

    def test_ready_allows_dispatch_halt(self) -> None:
        """READY allows DISPATCH and HALT."""
        result = get_allowed_transitions(ExecutionLoopState.READY)
        assert result == frozenset({LoopTransition.DISPATCH, LoopTransition.HALT})

    def test_dispatched_allows_receive_halt(self) -> None:
        """DISPATCHED allows RECEIVE and HALT."""
        result = get_allowed_transitions(ExecutionLoopState.DISPATCHED)
        assert result == frozenset({LoopTransition.RECEIVE, LoopTransition.HALT})

    def test_awaiting_allows_dispatch_halt(self) -> None:
        """AWAITING_RESPONSE allows DISPATCH and HALT."""
        result = get_allowed_transitions(ExecutionLoopState.AWAITING_RESPONSE)
        assert result == frozenset({LoopTransition.DISPATCH, LoopTransition.HALT})

    def test_halted_allows_only_halt(self) -> None:
        """HALTED allows only HALT (terminal)."""
        result = get_allowed_transitions(ExecutionLoopState.HALTED)
        assert result == frozenset({LoopTransition.HALT})


# ============================================================================
# get_next_state TESTS
# ============================================================================

class TestGetNextStateDenyByDefault:
    """Deny-by-default tests for get_next_state."""

    def test_none_state_returns_halted(self) -> None:
        """None state → HALTED."""
        result = get_next_state(None, LoopTransition.INIT)
        assert result == ExecutionLoopState.HALTED

    def test_non_state_returns_halted(self) -> None:
        """Non-ExecutionLoopState → HALTED."""
        result = get_next_state("INITIALIZED", LoopTransition.INIT)  # type: ignore
        assert result == ExecutionLoopState.HALTED

    def test_none_transition_returns_halted(self) -> None:
        """None transition → HALTED."""
        result = get_next_state(ExecutionLoopState.INITIALIZED, None)
        assert result == ExecutionLoopState.HALTED

    def test_non_transition_returns_halted(self) -> None:
        """Non-LoopTransition → HALTED."""
        result = get_next_state(ExecutionLoopState.INITIALIZED, "INIT")  # type: ignore
        assert result == ExecutionLoopState.HALTED

    def test_invalid_transition_returns_halted(self) -> None:
        """Invalid transition → HALTED."""
        result = get_next_state(ExecutionLoopState.INITIALIZED, LoopTransition.DISPATCH)
        assert result == ExecutionLoopState.HALTED


class TestGetNextStatePositive:
    """Positive tests for get_next_state."""

    def test_initialized_init_returns_ready(self) -> None:
        """INITIALIZED + INIT → READY."""
        result = get_next_state(ExecutionLoopState.INITIALIZED, LoopTransition.INIT)
        assert result == ExecutionLoopState.READY

    def test_ready_dispatch_returns_dispatched(self) -> None:
        """READY + DISPATCH → DISPATCHED."""
        result = get_next_state(ExecutionLoopState.READY, LoopTransition.DISPATCH)
        assert result == ExecutionLoopState.DISPATCHED


# ============================================================================
# is_terminal_state TESTS
# ============================================================================

class TestIsTerminalStateDenyByDefault:
    """Deny-by-default tests for is_terminal_state."""

    def test_none_returns_false(self) -> None:
        """None → False."""
        assert is_terminal_state(None) is False

    def test_non_state_returns_false(self) -> None:
        """Non-ExecutionLoopState → False."""
        assert is_terminal_state("HALTED") is False  # type: ignore


class TestIsTerminalStatePositive:
    """Positive tests for is_terminal_state."""

    def test_halted_is_terminal(self) -> None:
        """HALTED is terminal."""
        assert is_terminal_state(ExecutionLoopState.HALTED) is True

    def test_initialized_not_terminal(self) -> None:
        """INITIALIZED is not terminal."""
        assert is_terminal_state(ExecutionLoopState.INITIALIZED) is False

    def test_ready_not_terminal(self) -> None:
        """READY is not terminal."""
        assert is_terminal_state(ExecutionLoopState.READY) is False

    def test_dispatched_not_terminal(self) -> None:
        """DISPATCHED is not terminal."""
        assert is_terminal_state(ExecutionLoopState.DISPATCHED) is False

    def test_awaiting_not_terminal(self) -> None:
        """AWAITING_RESPONSE is not terminal."""
        assert is_terminal_state(ExecutionLoopState.AWAITING_RESPONSE) is False
