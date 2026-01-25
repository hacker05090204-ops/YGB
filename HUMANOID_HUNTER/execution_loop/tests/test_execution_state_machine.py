"""
Tests for Phase-29 Execution State Machine.

Tests:
- Valid state transitions
- Initialize from INIT
- State machine closure
"""
import pytest


class TestExecutionLoopState:
    """Test ExecutionLoopState enum."""

    def test_has_five_states(self):
        """ExecutionLoopState has exactly 5 states."""
        from HUMANOID_HUNTER.execution_loop.execution_types import ExecutionLoopState
        assert len(ExecutionLoopState) == 5

    def test_state_values(self):
        """ExecutionLoopState has correct values."""
        from HUMANOID_HUNTER.execution_loop.execution_types import ExecutionLoopState
        assert hasattr(ExecutionLoopState, 'INIT')
        assert hasattr(ExecutionLoopState, 'DISPATCHED')
        assert hasattr(ExecutionLoopState, 'AWAITING_RESPONSE')
        assert hasattr(ExecutionLoopState, 'EVALUATED')
        assert hasattr(ExecutionLoopState, 'HALTED')


class TestExecutionDecision:
    """Test ExecutionDecision enum."""

    def test_has_three_decisions(self):
        """ExecutionDecision has exactly 3 decisions."""
        from HUMANOID_HUNTER.execution_loop.execution_types import ExecutionDecision
        assert len(ExecutionDecision) == 3

    def test_decision_values(self):
        """ExecutionDecision has correct values."""
        from HUMANOID_HUNTER.execution_loop.execution_types import ExecutionDecision
        assert hasattr(ExecutionDecision, 'CONTINUE')
        assert hasattr(ExecutionDecision, 'STOP')
        assert hasattr(ExecutionDecision, 'ESCALATE')


class TestInitializeExecutionLoop:
    """Test initialize_execution_loop function."""

    def test_initialization_creates_init_state(self):
        """Initialization creates INIT state."""
        from HUMANOID_HUNTER.execution_loop.execution_engine import initialize_execution_loop
        from HUMANOID_HUNTER.execution_loop.execution_types import ExecutionLoopState

        context = initialize_execution_loop(
            instruction_envelope_hash="HASH-001",
            executor_id="EXEC-001"
        )

        assert context.current_state == ExecutionLoopState.INIT

    def test_initialization_sets_envelope_hash(self):
        """Initialization sets envelope hash."""
        from HUMANOID_HUNTER.execution_loop.execution_engine import initialize_execution_loop

        context = initialize_execution_loop(
            instruction_envelope_hash="HASH-001",
            executor_id="EXEC-001"
        )

        assert context.instruction_envelope_hash == "HASH-001"

    def test_initialization_generates_loop_id(self):
        """Initialization generates loop ID."""
        from HUMANOID_HUNTER.execution_loop.execution_engine import initialize_execution_loop

        context = initialize_execution_loop(
            instruction_envelope_hash="HASH-001",
            executor_id="EXEC-001"
        )

        assert len(context.loop_id) > 0


class TestValidStateTransitions:
    """Test valid state transitions."""

    def test_init_to_dispatched(self):
        """INIT → DISPATCHED is valid."""
        from HUMANOID_HUNTER.execution_loop.execution_engine import (
            initialize_execution_loop, transition_execution_state
        )
        from HUMANOID_HUNTER.execution_loop.execution_types import ExecutionLoopState

        context = initialize_execution_loop(
            instruction_envelope_hash="HASH-001",
            executor_id="EXEC-001"
        )

        new_context = transition_execution_state(
            context, ExecutionLoopState.DISPATCHED
        )

        assert new_context.current_state == ExecutionLoopState.DISPATCHED

    def test_dispatched_to_awaiting(self):
        """DISPATCHED → AWAITING_RESPONSE is valid."""
        from HUMANOID_HUNTER.execution_loop.execution_engine import (
            initialize_execution_loop, transition_execution_state
        )
        from HUMANOID_HUNTER.execution_loop.execution_types import ExecutionLoopState

        context = initialize_execution_loop(
            instruction_envelope_hash="HASH-001",
            executor_id="EXEC-001"
        )
        context = transition_execution_state(context, ExecutionLoopState.DISPATCHED)

        new_context = transition_execution_state(
            context, ExecutionLoopState.AWAITING_RESPONSE
        )

        assert new_context.current_state == ExecutionLoopState.AWAITING_RESPONSE

    def test_awaiting_to_evaluated(self):
        """AWAITING_RESPONSE → EVALUATED is valid."""
        from HUMANOID_HUNTER.execution_loop.execution_engine import (
            initialize_execution_loop, transition_execution_state
        )
        from HUMANOID_HUNTER.execution_loop.execution_types import ExecutionLoopState

        context = initialize_execution_loop(
            instruction_envelope_hash="HASH-001",
            executor_id="EXEC-001"
        )
        context = transition_execution_state(context, ExecutionLoopState.DISPATCHED)
        context = transition_execution_state(context, ExecutionLoopState.AWAITING_RESPONSE)

        new_context = transition_execution_state(
            context, ExecutionLoopState.EVALUATED
        )

        assert new_context.current_state == ExecutionLoopState.EVALUATED

    def test_evaluated_to_dispatched(self):
        """EVALUATED → DISPATCHED is valid (loop cycle)."""
        from HUMANOID_HUNTER.execution_loop.execution_engine import (
            initialize_execution_loop, transition_execution_state
        )
        from HUMANOID_HUNTER.execution_loop.execution_types import ExecutionLoopState

        context = initialize_execution_loop(
            instruction_envelope_hash="HASH-001",
            executor_id="EXEC-001"
        )
        context = transition_execution_state(context, ExecutionLoopState.DISPATCHED)
        context = transition_execution_state(context, ExecutionLoopState.AWAITING_RESPONSE)
        context = transition_execution_state(context, ExecutionLoopState.EVALUATED)

        new_context = transition_execution_state(
            context, ExecutionLoopState.DISPATCHED
        )

        assert new_context.current_state == ExecutionLoopState.DISPATCHED

    def test_any_to_halted(self):
        """Any state → HALTED is valid."""
        from HUMANOID_HUNTER.execution_loop.execution_engine import (
            initialize_execution_loop, transition_execution_state
        )
        from HUMANOID_HUNTER.execution_loop.execution_types import ExecutionLoopState

        context = initialize_execution_loop(
            instruction_envelope_hash="HASH-001",
            executor_id="EXEC-001"
        )

        new_context = transition_execution_state(
            context, ExecutionLoopState.HALTED
        )

        assert new_context.current_state == ExecutionLoopState.HALTED
