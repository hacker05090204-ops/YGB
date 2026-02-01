"""
Tests for Phase-29 Executor Cannot Advance.

Tests:
- Executor cannot directly modify state
- State changes require governance function
"""
import pytest


class TestExecutorCannotAdvance:
    """Test executor cannot advance state."""

    def test_context_is_immutable(self):
        """ExecutionLoopContext is immutable."""
        from HUMANOID_HUNTER.execution_loop.execution_context import ExecutionLoopContext
        from HUMANOID_HUNTER.execution_loop.execution_types import ExecutionLoopState

        context = ExecutionLoopContext(
            loop_id="LOOP-001",
            instruction_envelope_hash="HASH-001",
            current_state=ExecutionLoopState.INIT,
            executor_id="EXEC-001"
        )

        with pytest.raises(Exception):
            context.current_state = ExecutionLoopState.DISPATCHED

    def test_transition_returns_new_context(self):
        """transition_execution_state returns NEW context."""
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

        # Original is unchanged
        assert context.current_state == ExecutionLoopState.INIT
        # New context has new state
        assert new_context.current_state == ExecutionLoopState.DISPATCHED
        # They are different objects
        assert context is not new_context

    def test_loop_id_preserved_on_transition(self):
        """Loop ID is preserved on state transition."""
        from HUMANOID_HUNTER.execution_loop.execution_engine import (
            initialize_execution_loop, transition_execution_state
        )
        from HUMANOID_HUNTER.execution_loop.execution_types import ExecutionLoopState

        context = initialize_execution_loop(
            instruction_envelope_hash="HASH-001",
            executor_id="EXEC-001"
        )
        original_loop_id = context.loop_id

        new_context = transition_execution_state(
            context, ExecutionLoopState.DISPATCHED
        )

        assert new_context.loop_id == original_loop_id


class TestExecutionEvaluationResultStructure:
    """Test ExecutionEvaluationResult structure."""

    def test_result_creation(self):
        """ExecutionEvaluationResult can be created."""
        from HUMANOID_HUNTER.execution_loop.execution_context import ExecutionEvaluationResult
        from HUMANOID_HUNTER.execution_loop.execution_types import ExecutionDecision

        result = ExecutionEvaluationResult(
            decision=ExecutionDecision.CONTINUE,
            reason="Execution successful"
        )

        assert result.decision == ExecutionDecision.CONTINUE

    def test_result_frozen(self):
        """ExecutionEvaluationResult is frozen."""
        from HUMANOID_HUNTER.execution_loop.execution_context import ExecutionEvaluationResult
        from HUMANOID_HUNTER.execution_loop.execution_types import ExecutionDecision

        result = ExecutionEvaluationResult(
            decision=ExecutionDecision.CONTINUE,
            reason="Execution successful"
        )

        with pytest.raises(Exception):
            result.decision = ExecutionDecision.STOP
