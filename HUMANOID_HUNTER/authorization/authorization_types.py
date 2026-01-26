"""
Phase-34 Authorization Types.

This module defines enums for execution authorization.

CLOSED ENUMS - No new members may be added.

THIS IS AN AUTHORIZATION LAYER ONLY.
IT DOES NOT EXECUTE ANYTHING.

CORE RULES:
- Humans decide
- Systems authorize
- Execution still waits

DENY-BY-DEFAULT:
- Authorization is DENIED unless explicitly GRANTED
"""
from enum import Enum, auto


class AuthorizationStatus(Enum):
    """Authorization lifecycle status.
    
    CLOSED ENUM - No new members may be added.
    
    Status values:
    - AUTHORIZED: Authorization has been granted
    - REJECTED: Authorization was denied
    - REVOKED: Authorization was revoked after being granted
    - EXPIRED: Authorization timed out without use
    """
    AUTHORIZED = auto()
    REJECTED = auto()
    REVOKED = auto()
    EXPIRED = auto()


class AuthorizationDecision(Enum):
    """Final authorization decision.
    
    CLOSED ENUM - No new members may be added.
    
    Decision values:
    - ALLOW: Execution MAY proceed (but is not invoked here)
    - DENY: Execution MUST NOT proceed
    """
    ALLOW = auto()
    DENY = auto()


# Valid authorization statuses that permit ALLOW decision
ALLOW_STATUSES = frozenset({
    AuthorizationStatus.AUTHORIZED,
})

# Statuses that result in DENY decision
DENY_STATUSES = frozenset({
    AuthorizationStatus.REJECTED,
    AuthorizationStatus.REVOKED,
    AuthorizationStatus.EXPIRED,
})
