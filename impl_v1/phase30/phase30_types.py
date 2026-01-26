"""
impl_v1 Phase-30 Response Types.

NON-AUTHORITATIVE MIRROR of governance Phase-30.
Contains CLOSED enums only.

THIS MODULE HAS NO EXECUTION AUTHORITY.
THIS MODULE DOES NOT EVALUATE RESPONSES.
THIS MODULE DOES NOT DECIDE OUTCOMES.

CLOSED ENUMS:
- ExecutorResponseType: 5 members (SUCCESS, FAILURE, TIMEOUT, PARTIAL, MALFORMED)
- ResponseDecision: 3 members (ACCEPT, REJECT, ESCALATE)

EXECUTOR OUTPUT IS DATA, NOT TRUTH.
GOVERNANCE DECIDES.
"""
from enum import Enum, auto


class ExecutorResponseType(Enum):
    """Types of executor responses.
    
    CLOSED ENUM - Exactly 5 members. No additions permitted.
    
    Types:
    - SUCCESS: Executor completed successfully
    - FAILURE: Executor failed
    - TIMEOUT: Executor timed out
    - PARTIAL: Executor returned partial result
    - MALFORMED: Executor returned malformed data
    """
    SUCCESS = auto()
    FAILURE = auto()
    TIMEOUT = auto()
    PARTIAL = auto()
    MALFORMED = auto()


class ResponseDecision(Enum):
    """Decisions for executor response handling.
    
    CLOSED ENUM - Exactly 3 members. No additions permitted.
    
    Decisions:
    - ACCEPT: Response accepted for processing
    - REJECT: Response rejected
    - ESCALATE: Response requires human review
    """
    ACCEPT = auto()
    REJECT = auto()
    ESCALATE = auto()
