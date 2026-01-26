"""
impl_v1 Phase-28 Handshake Context.

NON-AUTHORITATIVE MIRROR of governance Phase-28.
Contains FROZEN dataclasses only.

THIS MODULE HAS NO EXECUTION AUTHORITY.

ALL DATACLASSES ARE FROZEN (frozen=True):
- HandshakeContext: 6 fields
- HandshakeResult: 5 fields

IMMUTABILITY GUARANTEE:
- No mutation permitted after creation
- Attempting mutation raises FrozenInstanceError
"""
from dataclasses import dataclass

from .phase28_types import ExecutorIdentityStatus, HandshakeDecision


@dataclass(frozen=True)
class HandshakeContext:
    """Context for a handshake validation.
    
    Immutable once created.
    
    Attributes:
        handshake_id: Unique identifier for the handshake
        executor_id: ID of the executor requesting handshake
        identity_status: Current identity status of the executor
        envelope_hash: Hash of the instruction envelope
        expected_hash: Expected hash for validation
        timestamp: Timestamp of handshake request (ISO-8601)
    """
    handshake_id: str
    executor_id: str
    identity_status: ExecutorIdentityStatus
    envelope_hash: str
    expected_hash: str
    timestamp: str


@dataclass(frozen=True)
class HandshakeResult:
    """Result of a handshake validation.
    
    Immutable once created.
    
    Attributes:
        handshake_id: Link to original handshake
        decision: Decision for the handshake
        identity_status: Identity status at time of decision
        hash_matched: Whether envelope hash matched expected
        reason: Human-readable reason for decision
    """
    handshake_id: str
    decision: HandshakeDecision
    identity_status: ExecutorIdentityStatus
    hash_matched: bool
    reason: str
