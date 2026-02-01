"""
Phase-24 Planning Types.

This module defines enums for execution plan governance.

CLOSED ENUMS - No new members may be added.

THIS IS A POLICY LAYER ONLY.
IT DOES NOT EXECUTE ANYTHING.
"""
from enum import Enum, auto


class PlannedActionType(Enum):
    """Planned action types.
    
    CLOSED ENUM - No new members may be added.
    """
    CLICK = auto()
    TYPE = auto()
    NAVIGATE = auto()
    WAIT = auto()
    SCREENSHOT = auto()
    SCROLL = auto()
    UPLOAD = auto()


class PlanRiskLevel(Enum):
    """Plan risk levels.
    
    CLOSED ENUM - No new members may be added.
    
    Ordering: LOW < MEDIUM < HIGH < CRITICAL
    """
    LOW = 1
    MEDIUM = 2
    HIGH = 3
    CRITICAL = 4


class PlanValidationDecision(Enum):
    """Plan validation decisions.
    
    CLOSED ENUM - No new members may be added.
    """
    ACCEPT = auto()
    REJECT = auto()
    REQUIRES_HUMAN = auto()
