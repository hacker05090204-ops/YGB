"""
Phase-29 Governed Execution Loop Definition (NO EXECUTION).

This module provides execution loop governance.

THIS IS A POLICY LAYER ONLY.
IT DOES NOT EXECUTE BROWSERS.
IT DOES NOT INVOKE SUBPROCESSES.
IT DOES NOT MAKE NETWORK CALLS.

CORE PRINCIPLES:
- Execution is a controlled loop
- Executors NEVER control it
- State machine is closed
- No retries without governance decision

Exports:
    Enums (CLOSED):
        ExecutionLoopState: INIT, DISPATCHED, AWAITING_RESPONSE, EVALUATED, HALTED
        ExecutionDecision: CONTINUE, STOP, ESCALATE
    
    Dataclasses (all frozen=True):
        ExecutionLoopContext: Execution loop context
        ExecutionEvaluationResult: Evaluation result
    
    Functions (pure, deterministic):
        initialize_execution_loop: Initialize loop
        transition_execution_state: Transition state
        evaluate_executor_response: Evaluate response
"""
from .execution_types import (
    ExecutionLoopState,
    ExecutionDecision
)
from .execution_context import (
    ExecutionLoopContext,
    ExecutionEvaluationResult
)
from .execution_engine import (
    initialize_execution_loop,
    transition_execution_state,
    evaluate_executor_response
)

__all__ = [
    # Enums
    "ExecutionLoopState",
    "ExecutionDecision",
    # Dataclasses
    "ExecutionLoopContext",
    "ExecutionEvaluationResult",
    # Functions
    "initialize_execution_loop",
    "transition_execution_state",
    "evaluate_executor_response",
]
