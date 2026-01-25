"""
Phase-18 Ledger Types.

This module defines enums for execution ledger.

CLOSED ENUMS - No new members may be added.
"""
from enum import Enum, auto


class ExecutionState(Enum):
    """Execution lifecycle states.
    
    CLOSED ENUM - No new members may be added.
    """
    REQUESTED = auto()
    ALLOWED = auto()
    ATTEMPTED = auto()
    FAILED = auto()
    COMPLETED = auto()
    ESCALATED = auto()


class EvidenceStatus(Enum):
    """Evidence validation status.
    
    CLOSED ENUM - No new members may be added.
    """
    MISSING = auto()
    LINKED = auto()
    INVALID = auto()
    VERIFIED = auto()


class RetryDecision(Enum):
    """Retry decision values.
    
    CLOSED ENUM - No new members may be added.
    """
    ALLOWED = auto()
    DENIED = auto()
    HUMAN_REQUIRED = auto()


# Valid state transitions
VALID_TRANSITIONS = frozenset({
    (ExecutionState.REQUESTED, ExecutionState.ALLOWED),
    (ExecutionState.REQUESTED, ExecutionState.ESCALATED),
    (ExecutionState.ALLOWED, ExecutionState.ATTEMPTED),
    (ExecutionState.ALLOWED, ExecutionState.ESCALATED),
    (ExecutionState.ATTEMPTED, ExecutionState.FAILED),
    (ExecutionState.ATTEMPTED, ExecutionState.COMPLETED),
    (ExecutionState.ATTEMPTED, ExecutionState.ESCALATED),
    (ExecutionState.FAILED, ExecutionState.ATTEMPTED),
    (ExecutionState.FAILED, ExecutionState.ESCALATED),
})

# Terminal states (no transitions allowed)
TERMINAL_STATES = frozenset({
    ExecutionState.COMPLETED,
    ExecutionState.ESCALATED
})
