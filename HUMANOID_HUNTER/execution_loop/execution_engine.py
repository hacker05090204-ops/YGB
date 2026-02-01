"""
Phase-29 Execution Engine.

This module provides execution loop governance functions.

All functions are pure (no side effects).
All decisions are deny-by-default.

THIS IS A POLICY LAYER ONLY.
IT DOES NOT EXECUTE ANYTHING.

CORE RULES:
- Execution is a controlled loop
- Executors NEVER control it
- State machine is closed
- No retries without governance decision
"""
import uuid
from typing import Optional

from .execution_types import ExecutionLoopState, ExecutionDecision
from .execution_context import ExecutionLoopContext, ExecutionEvaluationResult


# Valid state transitions (from_state → allowed_to_states)
_VALID_TRANSITIONS = {
    ExecutionLoopState.INIT: {ExecutionLoopState.DISPATCHED, ExecutionLoopState.HALTED},
    ExecutionLoopState.DISPATCHED: {ExecutionLoopState.AWAITING_RESPONSE, ExecutionLoopState.HALTED},
    ExecutionLoopState.AWAITING_RESPONSE: {ExecutionLoopState.EVALUATED, ExecutionLoopState.HALTED},
    ExecutionLoopState.EVALUATED: {ExecutionLoopState.DISPATCHED, ExecutionLoopState.HALTED},
    ExecutionLoopState.HALTED: {ExecutionLoopState.HALTED},  # Terminal - stays HALTED
}


def initialize_execution_loop(
    instruction_envelope_hash: str,
    executor_id: str
) -> ExecutionLoopContext:
    """Initialize execution loop.
    
    Args:
        instruction_envelope_hash: Hash of sealed instruction envelope
        executor_id: Bound executor identifier
        
    Returns:
        ExecutionLoopContext in INIT state (or HALTED if invalid)
        
    Rules:
        - Empty hash → HALTED
        - Empty executor_id → HALTED
    """
    # Deny-by-default: empty inputs → HALTED
    if not instruction_envelope_hash or not executor_id:
        return ExecutionLoopContext(
            loop_id=f"LOOP-{uuid.uuid4().hex[:8]}",
            instruction_envelope_hash=instruction_envelope_hash,
            current_state=ExecutionLoopState.HALTED,
            executor_id=executor_id
        )
    
    return ExecutionLoopContext(
        loop_id=f"LOOP-{uuid.uuid4().hex[:8]}",
        instruction_envelope_hash=instruction_envelope_hash,
        current_state=ExecutionLoopState.INIT,
        executor_id=executor_id
    )


def transition_execution_state(
    context: ExecutionLoopContext,
    to_state: ExecutionLoopState
) -> ExecutionLoopContext:
    """Transition execution state.
    
    Args:
        context: Current ExecutionLoopContext
        to_state: Target state
        
    Returns:
        NEW ExecutionLoopContext with new state (or HALTED if invalid)
        
    Rules:
        - Invalid transition → HALTED
        - HALTED is terminal
    """
    # Check if transition is valid
    allowed = _VALID_TRANSITIONS.get(context.current_state, set())
    
    if to_state not in allowed:
        # Invalid transition → HALT
        return ExecutionLoopContext(
            loop_id=context.loop_id,
            instruction_envelope_hash=context.instruction_envelope_hash,
            current_state=ExecutionLoopState.HALTED,
            executor_id=context.executor_id
        )
    
    # Valid transition → new context
    return ExecutionLoopContext(
        loop_id=context.loop_id,
        instruction_envelope_hash=context.instruction_envelope_hash,
        current_state=to_state,
        executor_id=context.executor_id
    )


def evaluate_executor_response(
    executor_response_success: bool,
    executor_response_error: Optional[str]
) -> ExecutionEvaluationResult:
    """Evaluate executor response.
    
    Args:
        executor_response_success: Whether executor claims success
        executor_response_error: Error message if any
        
    Returns:
        ExecutionEvaluationResult with decision and reason
        
    Rules:
        - Executor response is DATA, not truth
        - Success → CONTINUE
        - Error with "CRITICAL" → ESCALATE
        - Other error → STOP
    """
    if executor_response_success:
        return ExecutionEvaluationResult(
            decision=ExecutionDecision.CONTINUE,
            reason="Executor reported success"
        )
    
    # Check for critical errors
    if executor_response_error and "CRITICAL" in executor_response_error:
        return ExecutionEvaluationResult(
            decision=ExecutionDecision.ESCALATE,
            reason=f"Critical error: {executor_response_error}"
        )
    
    # Regular error → STOP
    return ExecutionEvaluationResult(
        decision=ExecutionDecision.STOP,
        reason=f"Executor error: {executor_response_error}"
    )
