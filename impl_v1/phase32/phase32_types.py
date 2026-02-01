"""
impl_v1 Phase-32 Human Decision Types.

NON-AUTHORITATIVE MIRROR of governance Phase-32.
Contains CLOSED enums only.

THIS MODULE HAS NO EXECUTION AUTHORITY.

CLOSED ENUMS:
- HumanDecision: 4 members (CONTINUE, RETRY, ABORT, ESCALATE)
- DecisionOutcome: 4 members (APPLIED, REJECTED, PENDING, TIMEOUT)
- EvidenceVisibility: 3 members (VISIBLE, HIDDEN, OVERRIDE_REQUIRED)

HUMANS DECIDE.
SYSTEMS MIRROR.
EXECUTION WAITS.
"""
from enum import Enum, auto


class HumanDecision(Enum):
    """Human decision types.
    
    CLOSED ENUM - Exactly 4 members. No additions permitted.
    
    Decision values:
    - CONTINUE: Proceed to next step
    - RETRY: Re-attempt same step
    - ABORT: Terminate execution
    - ESCALATE: Defer to higher authority
    """
    CONTINUE = auto()
    RETRY = auto()
    ABORT = auto()
    ESCALATE = auto()


class DecisionOutcome(Enum):
    """Outcome of attempting to apply a decision.
    
    CLOSED ENUM - Exactly 4 members. No additions permitted.
    
    Outcome values:
    - APPLIED: Decision was applied successfully
    - REJECTED: Decision could not be applied
    - PENDING: Decision awaiting precondition
    - TIMEOUT: Decision timed out (→ ABORT)
    """
    APPLIED = auto()
    REJECTED = auto()
    PENDING = auto()
    TIMEOUT = auto()


class EvidenceVisibility(Enum):
    """Evidence visibility levels for human presentation.
    
    CLOSED ENUM - Exactly 3 members. No additions permitted.
    
    Visibility values:
    - VISIBLE: Human may see
    - HIDDEN: Human must not see (default)
    - OVERRIDE_REQUIRED: Requires higher authority to view
    """
    VISIBLE = auto()
    HIDDEN = auto()
    OVERRIDE_REQUIRED = auto()
