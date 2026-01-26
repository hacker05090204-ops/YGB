"""
impl_v1 Phase-34 Authorization Types.

NON-AUTHORITATIVE MIRROR of governance Phase-34.
Contains CLOSED enums only.

THIS MODULE HAS NO EXECUTION AUTHORITY.

CLOSED ENUMS:
- AuthorizationStatus: 4 members (AUTHORIZED, REJECTED, REVOKED, EXPIRED)
- AuthorizationDecision: 2 members (ALLOW, DENY)

DENY-BY-DEFAULT:
- Authorization is DENIED unless explicitly GRANTED
"""
from enum import Enum, auto


class AuthorizationStatus(Enum):
    """Authorization lifecycle status.
    
    CLOSED ENUM - Exactly 4 members. No additions permitted.
    
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
    
    CLOSED ENUM - Exactly 2 members. No additions permitted.
    
    Decision values:
    - ALLOW: Execution MAY proceed (but is not invoked here)
    - DENY: Execution MUST NOT proceed
    """
    ALLOW = auto()
    DENY = auto()


# Valid authorization statuses that permit ALLOW decision
# FROZEN: Exactly 1 member
ALLOW_STATUSES = frozenset({
    AuthorizationStatus.AUTHORIZED,
})

# Statuses that result in DENY decision
# FROZEN: Exactly 3 members
DENY_STATUSES = frozenset({
    AuthorizationStatus.REJECTED,
    AuthorizationStatus.REVOKED,
    AuthorizationStatus.EXPIRED,
})
