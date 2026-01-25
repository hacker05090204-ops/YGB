"""
Phase-28 Handshake Types.

This module defines enums for executor handshake.

CLOSED ENUMS - No new members may be added.

THIS IS A POLICY LAYER ONLY.
IT DOES NOT EXECUTE ANYTHING.
"""
from enum import Enum, auto


class ExecutorIdentityStatus(Enum):
    """Executor identity status.
    
    CLOSED ENUM - No new members may be added.
    """
    UNKNOWN = auto()
    REGISTERED = auto()
    REVOKED = auto()


class HandshakeDecision(Enum):
    """Handshake decision.
    
    CLOSED ENUM - No new members may be added.
    """
    ACCEPT = auto()
    REJECT = auto()
