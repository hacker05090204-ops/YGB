"""
Tests for Phase-29 Invalid Transitions.

Tests:
- Invalid state transitions → HALTED
- HALTED is terminal
"""
import pytest


class TestInvalidTransitions:
    """Test invalid state transitions."""

    def test_init_to_awaiting_halts(self):
        """INIT → AWAITING_RESPONSE is invalid → HALTED."""
        from HUMANOID_HUNTER.execution_loop.execution_engine import (
            initialize_execution_loop, transition_execution_state
        )
        from HUMANOID_HUNTER.execution_loop.execution_types import ExecutionLoopState

        context = initialize_execution_loop(
            instruction_envelope_hash="HASH-001",
            executor_id="EXEC-001"
        )

        new_context = transition_execution_state(
            context, ExecutionLoopState.AWAITING_RESPONSE
        )

        assert new_context.current_state == ExecutionLoopState.HALTED

    def test_init_to_evaluated_halts(self):
        """INIT → EVALUATED is invalid → HALTED."""
        from HUMANOID_HUNTER.execution_loop.execution_engine import (
            initialize_execution_loop, transition_execution_state
        )
        from HUMANOID_HUNTER.execution_loop.execution_types import ExecutionLoopState

        context = initialize_execution_loop(
            instruction_envelope_hash="HASH-001",
            executor_id="EXEC-001"
        )

        new_context = transition_execution_state(
            context, ExecutionLoopState.EVALUATED
        )

        assert new_context.current_state == ExecutionLoopState.HALTED

    def test_dispatched_to_evaluated_halts(self):
        """DISPATCHED → EVALUATED is invalid → HALTED."""
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
            context, ExecutionLoopState.EVALUATED
        )

        assert new_context.current_state == ExecutionLoopState.HALTED

    def test_awaiting_to_dispatched_halts(self):
        """AWAITING_RESPONSE → DISPATCHED is invalid → HALTED."""
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
            context, ExecutionLoopState.DISPATCHED
        )

        assert new_context.current_state == ExecutionLoopState.HALTED


class TestHaltedIsTerminal:
    """Test HALTED is terminal state."""

    def test_halted_stays_halted(self):
        """HALTED → any transition stays HALTED."""
        from HUMANOID_HUNTER.execution_loop.execution_engine import (
            initialize_execution_loop, transition_execution_state
        )
        from HUMANOID_HUNTER.execution_loop.execution_types import ExecutionLoopState

        context = initialize_execution_loop(
            instruction_envelope_hash="HASH-001",
            executor_id="EXEC-001"
        )
        context = transition_execution_state(context, ExecutionLoopState.HALTED)

        # Try to transition to any other state
        new_context = transition_execution_state(
            context, ExecutionLoopState.DISPATCHED
        )

        assert new_context.current_state == ExecutionLoopState.HALTED

    def test_halted_to_init_stays_halted(self):
        """HALTED → INIT stays HALTED."""
        from HUMANOID_HUNTER.execution_loop.execution_engine import (
            initialize_execution_loop, transition_execution_state
        )
        from HUMANOID_HUNTER.execution_loop.execution_types import ExecutionLoopState

        context = initialize_execution_loop(
            instruction_envelope_hash="HASH-001",
            executor_id="EXEC-001"
        )
        context = transition_execution_state(context, ExecutionLoopState.HALTED)

        new_context = transition_execution_state(
            context, ExecutionLoopState.INIT
        )

        assert new_context.current_state == ExecutionLoopState.HALTED
