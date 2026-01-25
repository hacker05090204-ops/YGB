"""
Phase-16 Execution Types.

This module defines enums for execution permission.

CLOSED ENUMS - No new members may be added.
"""
from enum import Enum, auto


class ExecutionPermission(Enum):
    """Execution permission decision.
    
    CLOSED ENUM - No new members may be added.
    
    Members:
        ALLOWED: Execution is permitted
        DENIED: Execution is not permitted
    """
    ALLOWED = auto()
    DENIED = auto()


# Valid readiness states for execution
VALID_READINESS_STATES = frozenset({
    "READY_FOR_BROWSER",
    "REVIEW_REQUIRED",
    "NOT_READY"
})

# Human presence values
HUMAN_PRESENCE_VALUES = frozenset({
    "REQUIRED",
    "OPTIONAL",
    "BLOCKING"
})
