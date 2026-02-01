"""
impl_v1 Phase-32 Human Decision Context.

NON-AUTHORITATIVE MIRROR of governance Phase-32.
Contains FROZEN dataclasses only.

THIS MODULE HAS NO EXECUTION AUTHORITY.

ALL DATACLASSES ARE FROZEN (frozen=True):
- EvidenceSummary: 6 fields
- DecisionRequest: 7 fields
- DecisionRecord: 8 fields
- DecisionAudit: 5 fields

IMMUTABILITY GUARANTEE:
- No mutation permitted after creation
- Attempting mutation raises FrozenInstanceError
"""
from dataclasses import dataclass
from typing import Optional, Tuple

from .phase32_types import HumanDecision


@dataclass(frozen=True)
class EvidenceSummary:
    """Curated evidence summary for human presentation.
    
    Contains ONLY safe-to-display information.
    All fields are frozen after creation.
    
    Attributes:
        observation_point: Point name (not enum, for safety)
        evidence_type: Type name (not enum, for safety)
        timestamp: ISO-8601 formatted timestamp
        chain_length: Number of records in evidence chain
        execution_state: Current loop state name
        confidence_score: From Phase-30 (0.0-1.0)
    """
    observation_point: str
    evidence_type: str
    timestamp: str
    chain_length: int
    execution_state: str
    confidence_score: float


@dataclass(frozen=True)
class DecisionRequest:
    """Request for human decision.
    
    Immutable once created.
    
    Attributes:
        request_id: Unique identifier (DECISION-REQ-{uuid_hex})
        session_id: From observation context
        evidence_summary: Curated evidence for display
        allowed_decisions: Tuple of allowed decision types
        created_at: When request was created (ISO-8601)
        timeout_at: When request will timeout (ISO-8601)
        timeout_decision: Decision applied on timeout (always ABORT)
    """
    request_id: str
    session_id: str
    evidence_summary: EvidenceSummary
    allowed_decisions: Tuple[HumanDecision, ...]
    created_at: str
    timeout_at: str
    timeout_decision: HumanDecision


@dataclass(frozen=True)
class DecisionRecord:
    """Record of a human decision.
    
    Immutable audit entry.
    
    Attributes:
        decision_id: Unique identifier (DECISION-{uuid_hex})
        request_id: Link to DecisionRequest
        human_id: Who made the decision
        decision: The decision made
        reason: Required for RETRY and ESCALATE
        escalation_target: Required for ESCALATE
        timestamp: When decision was made (ISO-8601)
        evidence_chain_hash: Hash of evidence at decision time
    """
    decision_id: str
    request_id: str
    human_id: str
    decision: HumanDecision
    reason: Optional[str]
    escalation_target: Optional[str]
    timestamp: str
    evidence_chain_hash: str


@dataclass(frozen=True)
class DecisionAudit:
    """Append-only audit trail of decisions.
    
    Immutable chain structure. Hash-linked.
    
    Attributes:
        audit_id: Unique identifier
        records: Immutable tuple of DecisionRecord
        session_id: Session reference
        head_hash: Hash of most recent record (empty if empty)
        length: Number of records
    """
    audit_id: str
    records: Tuple[DecisionRecord, ...]
    session_id: str
    head_hash: str
    length: int
