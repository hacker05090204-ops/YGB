"""
impl_v1 Phase-29 Governed Execution Loop Mirror.

NON-AUTHORITATIVE MIRROR of governance Phase-29.
Contains ONLY data structures and validation logic.

THIS MODULE HAS NO EXECUTION AUTHORITY.
THIS MODULE DOES NOT EXECUTE INSTRUCTIONS.
THIS MODULE DOES NOT RUN LOOPS.
THIS MODULE DOES NOT CONTROL EXECUTORS.

CLOSED ENUMS:
- ExecutionLoopState: 5 members
- LoopTransition: 4 members

FROZEN DATACLASSES:
- ExecutionLoopContext: 6 fields
- LoopTransitionResult: 5 fields

ENGINE FUNCTIONS (VALIDATION ONLY):
- validate_loop_state
- validate_transition
- get_allowed_transitions
- get_next_state
- is_terminal_state

EXECUTION IS A CONTROLLED LOOP.
EXECUTORS NEVER CONTROL IT.
"""
from .phase29_types import (
    ExecutionLoopState,
    LoopTransition,
)
from .phase29_context import (
    ExecutionLoopContext,
    LoopTransitionResult,
)
from .phase29_engine import (
    validate_loop_state,
    validate_transition,
    get_allowed_transitions,
    get_next_state,
    is_terminal_state,
)

__all__ = [
    # Types
    "ExecutionLoopState",
    "LoopTransition",
    # Context
    "ExecutionLoopContext",
    "LoopTransitionResult",
    # Engine
    "validate_loop_state",
    "validate_transition",
    "get_allowed_transitions",
    "get_next_state",
    "is_terminal_state",
]
