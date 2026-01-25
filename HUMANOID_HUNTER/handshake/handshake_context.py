"""
Phase-28 Handshake Context.

This module defines frozen dataclasses for executor handshake.

All dataclasses are frozen=True (immutable).

THIS IS A POLICY LAYER ONLY.
IT DOES NOT EXECUTE ANYTHING.
"""
from dataclasses import dataclass

from .handshake_types import ExecutorIdentityStatus, HandshakeDecision


@dataclass(frozen=True)
class ExecutorIdentity:
    """Executor identity.
    
    Frozen=True - Cannot be modified after creation.
    
    Attributes:
        executor_id: Unique executor identifier
        public_key_hash: Hash of executor's public key
        trust_status: Current trust status
    """
    executor_id: str
    public_key_hash: str
    trust_status: ExecutorIdentityStatus


@dataclass(frozen=True)
class HandshakeContext:
    """Handshake context.
    
    Frozen=True - Cannot be modified after creation.
    
    Attributes:
        instruction_envelope_hash: Hash of sealed instruction envelope
        executor_identity: Executor identity
        timestamp: Logical timestamp
    """
    instruction_envelope_hash: str
    executor_identity: ExecutorIdentity
    timestamp: str


@dataclass(frozen=True)
class HandshakeResult:
    """Handshake result.
    
    Frozen=True - Cannot be modified after creation.
    
    Attributes:
        decision: HandshakeDecision (ACCEPT, REJECT)
        reason: Human-readable reason
    """
    decision: HandshakeDecision
    reason: str
