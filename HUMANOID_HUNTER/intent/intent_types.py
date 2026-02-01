"""
Phase-33 Intent Types.

This module defines enums for intent binding.

CLOSED ENUMS - No new members may be added.

HUMANS DECIDE.
SYSTEMS BIND INTENT.
EXECUTION WAITS.

CORE RULES:
- Intent is DATA, not action
- Binding translates decision to intent
- All enums are closed
"""
from enum import Enum, auto


class IntentStatus(Enum):
    """Intent lifecycle status.
    
    CLOSED ENUM - No new members may be added.
    
    Status values:
    - PENDING: Bound but not yet executed
    - EXECUTED: Execution completed
    - REVOKED: Revoked before execution
    - EXPIRED: Timeout occurred without execution
    """
    PENDING = auto()
    EXECUTED = auto()
    REVOKED = auto()
    EXPIRED = auto()


class BindingResult(Enum):
    """Result of binding attempt.
    
    CLOSED ENUM - No new members may be added.
    
    Result values:
    - SUCCESS: Binding succeeded
    - INVALID_DECISION: Decision validation failed
    - MISSING_FIELD: Required field missing
    - DUPLICATE: Intent already exists for this decision
    - REJECTED: Binding rejected for other reason
    """
    SUCCESS = auto()
    INVALID_DECISION = auto()
    MISSING_FIELD = auto()
    DUPLICATE = auto()
    REJECTED = auto()
