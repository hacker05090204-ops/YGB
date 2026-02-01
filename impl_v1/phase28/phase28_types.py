"""
impl_v1 Phase-28 Handshake Types.

NON-AUTHORITATIVE MIRROR of governance Phase-28.
Contains CLOSED enums only.

THIS MODULE HAS NO EXECUTION AUTHORITY.
THIS MODULE DOES NOT PERFORM HANDSHAKES.
THIS MODULE DOES NOT GRANT AUTHORITY.

CLOSED ENUMS:
- ExecutorIdentityStatus: 4 members (VERIFIED, UNVERIFIED, REVOKED, UNKNOWN)
- HandshakeDecision: 2 members (ACCEPT, REJECT)

HANDSHAKE PROVES ELIGIBILITY.
IT NEVER GRANTS AUTHORITY.
"""
from enum import Enum, auto


class ExecutorIdentityStatus(Enum):
    """Status of an executor's identity.
    
    CLOSED ENUM - Exactly 4 members. No additions permitted.
    
    States:
    - VERIFIED: Identity has been verified
    - UNVERIFIED: Identity has not been verified
    - REVOKED: Identity has been revoked
    - UNKNOWN: Identity is unknown
    """
    VERIFIED = auto()
    UNVERIFIED = auto()
    REVOKED = auto()
    UNKNOWN = auto()


class HandshakeDecision(Enum):
    """Decision for handshake validation.
    
    CLOSED ENUM - Exactly 2 members. No additions permitted.
    
    Decisions:
    - ACCEPT: Handshake accepted
    - REJECT: Handshake rejected
    """
    ACCEPT = auto()
    REJECT = auto()
