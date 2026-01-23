"""
State Transitions - Phase-05 Workflow State Model
REIMPLEMENTED-2026

Defines StateTransition enum and helper functions.
Pure definitions only - no execution logic.
"""

from enum import Enum
from typing import FrozenSet


class StateTransition(Enum):
    """
    Closed enum representing all valid state transitions.
    
    Transitions:
        VALIDATE: Move from INIT to VALIDATED
        ESCALATE: Move to ESCALATED (requires human)
        APPROVE: Human approves (HUMAN only)
        REJECT: Human rejects (HUMAN only)
        COMPLETE: Finalize workflow
        ABORT: Abort workflow (HUMAN only)
    """
    VALIDATE = "validate"
    ESCALATE = "escalate"
    APPROVE = "approve"
    REJECT = "reject"
    COMPLETE = "complete"
    ABORT = "abort"


# Transitions that require HUMAN actor - SYSTEM cannot perform these
_HUMAN_ONLY_TRANSITIONS: FrozenSet[StateTransition] = frozenset({
    StateTransition.APPROVE,
    StateTransition.REJECT,
    StateTransition.ABORT,
})


def requires_human(transition: StateTransition) -> bool:
    """
    Check if a transition requires a HUMAN actor.
    
    SYSTEM cannot perform APPROVE, REJECT, or ABORT transitions.
    These require explicit human authorization.
    
    Args:
        transition: The state transition to check
        
    Returns:
        True if the transition requires HUMAN, False otherwise
    """
    return transition in _HUMAN_ONLY_TRANSITIONS
