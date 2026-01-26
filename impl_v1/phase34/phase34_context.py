"""
impl_v1 Phase-34 Authorization Context.

NON-AUTHORITATIVE MIRROR of governance Phase-34.
Contains FROZEN dataclasses only.

THIS MODULE HAS NO EXECUTION AUTHORITY.

ALL DATACLASSES ARE FROZEN (frozen=True):
- ExecutionAuthorization: 8 fields
- AuthorizationRevocation: 6 fields
- AuthorizationRecord: 6 fields
- AuthorizationAudit: 5 fields

IMMUTABILITY GUARANTEE:
- No mutation permitted after creation
- Attempting mutation raises FrozenInstanceError
"""
from dataclasses import dataclass
from typing import Tuple

from .phase34_types import AuthorizationStatus


@dataclass(frozen=True)
class ExecutionAuthorization:
    """Immutable execution authorization record.
    
    All fields are frozen after creation.
    
    Attributes:
        authorization_id: Unique identifier (AUTH-{uuid_hex})
        intent_id: Reference to ExecutionIntent
        decision_id: Reference to DecisionRecord
        session_id: Observation session
        authorization_status: Current status
        authorized_by: Human who authorized
        authorized_at: ISO-8601 timestamp
        authorization_hash: SHA-256 of all other fields
    """
    authorization_id: str
    intent_id: str
    decision_id: str
    session_id: str
    authorization_status: AuthorizationStatus
    authorized_by: str
    authorized_at: str
    authorization_hash: str


@dataclass(frozen=True)
class AuthorizationRevocation:
    """Record of authorization revocation.
    
    Immutable once created. Revocation is permanent.
    
    Attributes:
        revocation_id: Unique identifier (AUTHREV-{uuid_hex})
        authorization_id: Authorization being revoked
        revoked_by: Human who revoked
        revocation_reason: Mandatory reason
        revoked_at: ISO-8601 timestamp
        revocation_hash: SHA-256 of revocation fields
    """
    revocation_id: str
    authorization_id: str
    revoked_by: str
    revocation_reason: str
    revoked_at: str
    revocation_hash: str


@dataclass(frozen=True)
class AuthorizationRecord:
    """Record in authorization audit trail.
    
    Either authorization or revocation event.
    
    Attributes:
        record_id: Unique identifier
        record_type: "AUTHORIZATION" or "REVOCATION"
        authorization_id: Authorization this record pertains to
        timestamp: When recorded
        prior_hash: Hash of prior record
        self_hash: Hash of this record
    """
    record_id: str
    record_type: str
    authorization_id: str
    timestamp: str
    prior_hash: str
    self_hash: str


@dataclass(frozen=True)
class AuthorizationAudit:
    """Append-only authorization audit trail.
    
    Immutable chain structure. Hash-linked.
    
    Attributes:
        audit_id: Unique identifier
        records: Immutable tuple of AuthorizationRecord
        session_id: Session reference
        head_hash: Hash of most recent record (empty if empty)
        length: Number of records
    """
    audit_id: str
    records: Tuple[AuthorizationRecord, ...]
    session_id: str
    head_hash: str
    length: int
