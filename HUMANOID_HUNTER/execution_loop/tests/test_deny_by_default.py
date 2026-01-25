"""
Tests for Phase-29 Deny-By-Default.

Tests:
- Empty envelope hash → HALT
- Empty executor ID → HALT
- evaluate_executor_response behavior
"""
import pytest


class TestDenyByDefault:
    """Test deny-by-default behavior."""

    def test_empty_envelope_hash_halts(self):
        """Empty envelope hash → HALTED."""
        from HUMANOID_HUNTER.execution_loop.execution_engine import initialize_execution_loop
        from HUMANOID_HUNTER.execution_loop.execution_types import ExecutionLoopState

        context = initialize_execution_loop(
            instruction_envelope_hash="",  # Empty!
            executor_id="EXEC-001"
        )

        assert context.current_state == ExecutionLoopState.HALTED

    def test_empty_executor_id_halts(self):
        """Empty executor ID → HALTED."""
        from HUMANOID_HUNTER.execution_loop.execution_engine import initialize_execution_loop
        from HUMANOID_HUNTER.execution_loop.execution_types import ExecutionLoopState

        context = initialize_execution_loop(
            instruction_envelope_hash="HASH-001",
            executor_id=""  # Empty!
        )

        assert context.current_state == ExecutionLoopState.HALTED


class TestEvaluateExecutorResponse:
    """Test evaluate_executor_response function."""

    def test_success_response_continues(self):
        """Success response → CONTINUE."""
        from HUMANOID_HUNTER.execution_loop.execution_engine import evaluate_executor_response
        from HUMANOID_HUNTER.execution_loop.execution_types import ExecutionDecision

        result = evaluate_executor_response(
            executor_response_success=True,
            executor_response_error=None
        )

        assert result.decision == ExecutionDecision.CONTINUE

    def test_error_response_stops(self):
        """Error response → STOP."""
        from HUMANOID_HUNTER.execution_loop.execution_engine import evaluate_executor_response
        from HUMANOID_HUNTER.execution_loop.execution_types import ExecutionDecision

        result = evaluate_executor_response(
            executor_response_success=False,
            executor_response_error="Connection failed"
        )

        assert result.decision == ExecutionDecision.STOP

    def test_critical_error_escalates(self):
        """Critical error → ESCALATE."""
        from HUMANOID_HUNTER.execution_loop.execution_engine import evaluate_executor_response
        from HUMANOID_HUNTER.execution_loop.execution_types import ExecutionDecision

        result = evaluate_executor_response(
            executor_response_success=False,
            executor_response_error="CRITICAL: Security violation"
        )

        assert result.decision == ExecutionDecision.ESCALATE

    def test_result_has_reason(self):
        """Evaluation result has reason."""
        from HUMANOID_HUNTER.execution_loop.execution_engine import evaluate_executor_response

        result = evaluate_executor_response(
            executor_response_success=True,
            executor_response_error=None
        )

        assert len(result.reason) > 0


class TestExecutionLoopContextStructure:
    """Test ExecutionLoopContext structure."""

    def test_context_creation(self):
        """ExecutionLoopContext can be created."""
        from HUMANOID_HUNTER.execution_loop.execution_context import ExecutionLoopContext
        from HUMANOID_HUNTER.execution_loop.execution_types import ExecutionLoopState

        context = ExecutionLoopContext(
            loop_id="LOOP-001",
            instruction_envelope_hash="HASH-001",
            current_state=ExecutionLoopState.INIT,
            executor_id="EXEC-001"
        )

        assert context.loop_id == "LOOP-001"

    def test_context_frozen(self):
        """ExecutionLoopContext is frozen."""
        from HUMANOID_HUNTER.execution_loop.execution_context import ExecutionLoopContext
        from HUMANOID_HUNTER.execution_loop.execution_types import ExecutionLoopState

        context = ExecutionLoopContext(
            loop_id="LOOP-001",
            instruction_envelope_hash="HASH-001",
            current_state=ExecutionLoopState.INIT,
            executor_id="EXEC-001"
        )

        with pytest.raises(Exception):
            context.loop_id = "MODIFIED"
