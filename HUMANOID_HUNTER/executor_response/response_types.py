"""
Phase-30 Response Types.

This module defines enums for executor response governance.

CLOSED ENUMS - No new members may be added.

THIS IS A POLICY LAYER ONLY.
IT DOES NOT EXECUTE ANYTHING.
"""
from enum import Enum, auto


class ExecutorResponseType(Enum):
    """Executor response type.
    
    CLOSED ENUM - No new members may be added.
    
    Values:
    - SUCCESS: Executor claims success
    - FAILURE: Executor reports failure
    - TIMEOUT: Operation timed out
    - PARTIAL: Partial completion
    - MALFORMED: Response is malformed/invalid
    """
    SUCCESS = auto()
    FAILURE = auto()
    TIMEOUT = auto()
    PARTIAL = auto()
    MALFORMED = auto()


class ResponseDecision(Enum):
    """Governance decision for executor response.
    
    CLOSED ENUM - No new members may be added.
    
    Values:
    - ACCEPT: Accept the response
    - REJECT: Reject the response  
    - ESCALATE: Escalate to human
    """
    ACCEPT = auto()
    REJECT = auto()
    ESCALATE = auto()
