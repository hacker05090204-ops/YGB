"""
impl_v1 Phase-33 Intent Context.

NON-AUTHORITATIVE MIRROR of governance Phase-33.
Contains FROZEN dataclasses only.

THIS MODULE HAS NO EXECUTION AUTHORITY.

ALL DATACLASSES ARE FROZEN (frozen=True):
- ExecutionIntent: 9 fields
- IntentRevocation: 6 fields
- IntentRecord: 6 fields
- IntentAudit: 5 fields

IMMUTABILITY GUARANTEE:
- No mutation permitted after creation
- Attempting mutation raises FrozenInstanceError
"""
from dataclasses import dataclass
from typing import Tuple

from .phase33_types import IntentStatus


@dataclass(frozen=True)
class ExecutionIntent:
    """Immutable execution intent bound to a human decision.
    
    All fields are frozen after creation.
    
    Attributes:
        intent_id: Unique identifier (INTENT-{uuid_hex})
        decision_id: Reference to DecisionRecord
        decision_type: CONTINUE/RETRY/ABORT/ESCALATE as string
        evidence_chain_hash: Frozen evidence state at binding
        session_id: Observation session
        execution_state: ExecutionLoopState at binding
        created_at: ISO-8601 timestamp
        created_by: Human who decided
        intent_hash: SHA-256 of all other fields
    """
    intent_id: str
    decision_id: str
    decision_type: str  # Stored as string to avoid cross-phase imports
    evidence_chain_hash: str
    session_id: str
    execution_state: str
    created_at: str
    created_by: str
    intent_hash: str


@dataclass(frozen=True)
class IntentRevocation:
    """Record of intent revocation.
    
    Immutable once created. Revocation is permanent.
    
    Attributes:
        revocation_id: Unique identifier (INTENTREV-{uuid_hex})
        intent_id: Intent being revoked
        revoked_by: Human who revoked
        revocation_reason: Mandatory reason
        revoked_at: ISO-8601 timestamp
        revocation_hash: SHA-256 of revocation fields
    """
    revocation_id: str
    intent_id: str
    revoked_by: str
    revocation_reason: str
    revoked_at: str
    revocation_hash: str


@dataclass(frozen=True)
class IntentRecord:
    """Record in intent audit trail.
    
    Either binding or revocation event.
    
    Attributes:
        record_id: Unique identifier
        record_type: "BINDING" or "REVOCATION"
        intent_id: Intent this record pertains to
        timestamp: When recorded
        prior_hash: Hash of prior record
        self_hash: Hash of this record
    """
    record_id: str
    record_type: str
    intent_id: str
    timestamp: str
    prior_hash: str
    self_hash: str


@dataclass(frozen=True)
class IntentAudit:
    """Append-only intent audit trail.
    
    Immutable chain structure. Hash-linked.
    
    Attributes:
        audit_id: Unique identifier
        records: Immutable tuple of IntentRecord
        session_id: Session reference
        head_hash: Hash of most recent record (empty if empty)
        length: Number of records
    """
    audit_id: str
    records: Tuple[IntentRecord, ...]
    session_id: str
    head_hash: str
    length: int
