"""
impl_v1 Phase-29 Execution Loop Context.

NON-AUTHORITATIVE MIRROR of governance Phase-29.
Contains FROZEN dataclasses only.

THIS MODULE HAS NO EXECUTION AUTHORITY.

ALL DATACLASSES ARE FROZEN (frozen=True):
- ExecutionLoopContext: 6 fields
- LoopTransitionResult: 5 fields

IMMUTABILITY GUARANTEE:
- No mutation permitted after creation
- Attempting mutation raises FrozenInstanceError
"""
from dataclasses import dataclass
from typing import Optional

from .phase29_types import ExecutionLoopState, LoopTransition


@dataclass(frozen=True)
class ExecutionLoopContext:
    """Context for a governed execution loop.
    
    Immutable once created.
    
    Attributes:
        loop_id: Unique identifier for the loop
        current_state: Current state of the loop
        executor_id: ID of the assigned executor
        envelope_hash: Expected instruction envelope hash
        created_at: Timestamp of loop creation (ISO-8601)
        iteration_count: Number of loop iterations
    """
    loop_id: str
    current_state: ExecutionLoopState
    executor_id: str
    envelope_hash: str
    created_at: str
    iteration_count: int


@dataclass(frozen=True)
class LoopTransitionResult:
    """Result of a loop transition validation.
    
    Immutable once created.
    
    Attributes:
        transition: The transition that was validated
        from_state: The state before transition
        to_state: The resulting state (HALTED if invalid)
        is_valid: Whether the transition was valid
        reason: Human-readable reason for result
    """
    transition: LoopTransition
    from_state: ExecutionLoopState
    to_state: ExecutionLoopState
    is_valid: bool
    reason: str
