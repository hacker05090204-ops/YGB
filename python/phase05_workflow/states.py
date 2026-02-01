"""
Workflow States - Phase-05 Workflow State Model
REIMPLEMENTED-2026

Defines WorkflowState enum and helper functions.
Pure definitions only - no execution logic.
"""

from enum import Enum
from typing import FrozenSet


class WorkflowState(Enum):
    """
    Closed enum representing all valid workflow states.
    
    States:
        INIT: Initial state, action not yet validated
        VALIDATED: Action passed Phase-04 validation
        ESCALATED: Action requires human approval
        APPROVED: Human approved the action
        REJECTED: Human rejected the action (TERMINAL)
        COMPLETED: Action workflow finished successfully (TERMINAL)
        ABORTED: Action workflow aborted (TERMINAL)
    """
    INIT = "init"
    VALIDATED = "validated"
    ESCALATED = "escalated"
    APPROVED = "approved"
    REJECTED = "rejected"
    COMPLETED = "completed"
    ABORTED = "aborted"


# Terminal states - no transitions allowed from these states
_TERMINAL_STATES: FrozenSet[WorkflowState] = frozenset({
    WorkflowState.COMPLETED,
    WorkflowState.ABORTED,
    WorkflowState.REJECTED,
})


def is_terminal_state(state: WorkflowState) -> bool:
    """
    Check if a state is terminal (no further transitions allowed).
    
    Args:
        state: The workflow state to check
        
    Returns:
        True if the state is terminal, False otherwise
    """
    return state in _TERMINAL_STATES
