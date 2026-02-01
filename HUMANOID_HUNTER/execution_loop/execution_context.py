"""
Phase-29 Execution Context.

This module defines frozen dataclasses for execution loop governance.

All dataclasses are frozen=True (immutable).

THIS IS A POLICY LAYER ONLY.
IT DOES NOT EXECUTE ANYTHING.
"""
from dataclasses import dataclass

from .execution_types import ExecutionLoopState, ExecutionDecision


@dataclass(frozen=True)
class ExecutionLoopContext:
    """Execution loop context.
    
    Frozen=True - Cannot be modified after creation.
    
    Attributes:
        loop_id: Unique loop identifier
        instruction_envelope_hash: Hash of bound instruction envelope
        current_state: Current state in the loop
        executor_id: Bound executor identifier
    """
    loop_id: str
    instruction_envelope_hash: str
    current_state: ExecutionLoopState
    executor_id: str


@dataclass(frozen=True)
class ExecutionEvaluationResult:
    """Execution evaluation result.
    
    Frozen=True - Cannot be modified after creation.
    
    Attributes:
        decision: ExecutionDecision (CONTINUE, STOP, ESCALATE)
        reason: Human-readable reason
    """
    decision: ExecutionDecision
    reason: str
