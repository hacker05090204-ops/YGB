"""
Phase-25 Orchestration Types.

This module defines enums for orchestration binding.

CLOSED ENUMS - No new members may be added.

THIS IS A POLICY LAYER ONLY.
IT DOES NOT EXECUTE ANYTHING.
"""
from enum import Enum, auto


class OrchestrationIntentState(Enum):
    """Orchestration intent states.
    
    CLOSED ENUM - No new members may be added.
    """
    DRAFT = auto()
    SEALED = auto()
    REJECTED = auto()


class OrchestrationDecision(Enum):
    """Orchestration decisions.
    
    CLOSED ENUM - No new members may be added.
    """
    ACCEPT = auto()
    REJECT = auto()
