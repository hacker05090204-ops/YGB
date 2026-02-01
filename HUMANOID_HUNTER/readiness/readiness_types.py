"""
Phase-26 Readiness Types.

This module defines enums for execution readiness.

CLOSED ENUMS - No new members may be added.

THIS IS A POLICY LAYER ONLY.
IT DOES NOT EXECUTE ANYTHING.
"""
from enum import Enum, auto


class ExecutionReadinessState(Enum):
    """Execution readiness states.
    
    CLOSED ENUM - No new members may be added.
    """
    READY = auto()
    NOT_READY = auto()


class ReadinessDecision(Enum):
    """Readiness decisions.
    
    CLOSED ENUM - No new members may be added.
    """
    ALLOW = auto()
    BLOCK = auto()
