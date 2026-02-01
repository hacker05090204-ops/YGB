"""
Phase-29 Execution Types.

This module defines enums for execution loop governance.

CLOSED ENUMS - No new members may be added.

THIS IS A POLICY LAYER ONLY.
IT DOES NOT EXECUTE ANYTHING.
"""
from enum import Enum, auto


class ExecutionLoopState(Enum):
    """Execution loop state.
    
    CLOSED ENUM - No new members may be added.
    
    State machine:
    - INIT → DISPATCHED → AWAITING_RESPONSE → EVALUATED → (loop)
    - Any → HALTED (terminal)
    """
    INIT = auto()
    DISPATCHED = auto()
    AWAITING_RESPONSE = auto()
    EVALUATED = auto()
    HALTED = auto()


class ExecutionDecision(Enum):
    """Execution decision.
    
    CLOSED ENUM - No new members may be added.
    """
    CONTINUE = auto()
    STOP = auto()
    ESCALATE = auto()
