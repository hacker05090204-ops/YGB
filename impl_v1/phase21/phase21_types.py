"""
impl_v1 Phase-21 System Invariant Types.

NON-AUTHORITATIVE MIRROR of governance Phase-21.
Contains CLOSED enums only.

THIS MODULE HAS NO EXECUTION AUTHORITY.
THIS MODULE NEVER ENFORCES INVARIANTS.
THIS MODULE ONLY REPORTS INVARIANT STATUS.

CLOSED ENUMS:
- InvariantScope: 5 members
- InvariantViolation: 4 members
- InvariantDecision: 3 members (PASS, FAIL, ESCALATE)

DEFAULT = FAIL.
"""
from enum import Enum, auto


class InvariantScope(Enum):
    """Scope of invariant application.
    
    CLOSED ENUM - Exactly 5 members. No additions permitted.
    """
    GLOBAL = auto()
    EXECUTION = auto()
    EVIDENCE = auto()
    AUTHORIZATION = auto()
    HUMAN = auto()


class InvariantViolation(Enum):
    """Types of invariant violations.
    
    CLOSED ENUM - Exactly 4 members. No additions permitted.
    
    Violations:
    - BROKEN_CHAIN: Chain of evidence/execution broken
    - STATE_INCONSISTENT: System state is inconsistent
    - MISSING_PRECONDITION: Required precondition not met
    - UNKNOWN_INVARIANT: Invariant is unknown
    """
    BROKEN_CHAIN = auto()
    STATE_INCONSISTENT = auto()
    MISSING_PRECONDITION = auto()
    UNKNOWN_INVARIANT = auto()


class InvariantDecision(Enum):
    """Decision from invariant evaluation.
    
    CLOSED ENUM - Exactly 3 members. No additions permitted.
    
    Decisions:
    - PASS: Invariant check passed
    - FAIL: Invariant check failed
    - ESCALATE: Invariant requires human review
    """
    PASS = auto()
    FAIL = auto()
    ESCALATE = auto()
