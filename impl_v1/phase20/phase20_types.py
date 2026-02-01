"""
impl_v1 Phase-20 System Root Boundary Types.

NON-AUTHORITATIVE MIRROR of governance Phase-20.
Contains CLOSED enums only.

THIS MODULE HAS NO EXECUTION AUTHORITY.
THIS MODULE NEVER ENFORCES BOUNDARIES.
THIS MODULE ONLY DEFINES WHAT THE SYSTEM IS.

PHASE-20 IS THE ABSOLUTE ROOT BOUNDARY.
NOTHING EXISTS BELOW IT.
NOTHING BYPASSES IT.

CLOSED ENUMS:
- SystemLayer: 5 members (ROOT, GOVERNANCE, EXECUTION, OBSERVATION, HUMAN)
- BoundaryViolation: 4 members
- BoundaryDecision: 3 members (ALLOW, DENY, ESCALATE)

DEFAULT = DENY.
"""
from enum import Enum, auto


class SystemLayer(Enum):
    """System layer hierarchy.
    
    CLOSED ENUM - Exactly 5 members. No additions permitted.
    
    ROOT is the absolute foundation. Nothing exists below it.
    """
    ROOT = auto()
    GOVERNANCE = auto()
    EXECUTION = auto()
    OBSERVATION = auto()
    HUMAN = auto()


class BoundaryViolation(Enum):
    """Types of boundary violations.
    
    CLOSED ENUM - Exactly 4 members. No additions permitted.
    
    Violations:
    - BYPASS_ATTEMPT: Attempt to bypass a boundary
    - UNKNOWN_LAYER: Layer is unknown
    - ORDER_BREACH: Layer order violated
    - UNDEFINED_ROOT: ROOT is undefined or missing
    """
    BYPASS_ATTEMPT = auto()
    UNKNOWN_LAYER = auto()
    ORDER_BREACH = auto()
    UNDEFINED_ROOT = auto()


class BoundaryDecision(Enum):
    """Decision from boundary evaluation.
    
    CLOSED ENUM - Exactly 3 members. No additions permitted.
    
    Decisions:
    - ALLOW: Transition is allowed
    - DENY: Transition is denied
    - ESCALATE: Transition requires human review
    """
    ALLOW = auto()
    DENY = auto()
    ESCALATE = auto()
