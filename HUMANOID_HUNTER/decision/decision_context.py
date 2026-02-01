"""
Phase-32 Decision Context.

This module defines frozen dataclasses for human decision governance.

ALL DATACLASSES ARE FROZEN - No mutation permitted after creation.

THIS IS A HUMAN DECISION LAYER ONLY.
EVIDENCE INFORMS HUMANS.
HUMANS DECIDE.
SYSTEMS OBEY.

CORE RULES:
- Evidence summary never contains raw data
- All decisions are immutable
- Audit trail is append-only
"""
from dataclasses import dataclass
from typing import Optional, Tuple

from .decision_types import HumanDecision


@dataclass(frozen=True)
class EvidenceSummary:
    """Curated evidence summary for human presentation.
    
    Contains ONLY safe-to-display information.
    RAW DATA IS NEVER INCLUDED.
    
    Attributes:
        observation_point: Point name string (e.g., "PRE_DISPATCH")
        evidence_type: Type name string (e.g., "STATE_TRANSITION")
        timestamp: ISO-8601 formatted timestamp
        chain_length: Number of evidence records
        execution_state: Current execution loop state name
        confidence_score: From Phase-30 normalization (0.0-1.0)
        chain_hash: Head hash for verification
    """
    observation_point: str
    evidence_type: str
    timestamp: str
    chain_length: int
    execution_state: str
    confidence_score: float
    chain_hash: str


@dataclass(frozen=True)
class DecisionRequest:
    """Request for human decision.
    
    Immutable once created.
    
    Attributes:
        request_id: Unique request identifier
        session_id: From Phase-31 ObservationContext
        evidence_summary: Curated summary (no raw data)
        allowed_decisions: Tuple of allowed decision types
        created_at: When request was created (ISO-8601)
        timeout_at: When request will timeout (ISO-8601)
        timeout_decision: Decision on timeout (ALWAYS ABORT)
    """
    request_id: str
    session_id: str
    evidence_summary: EvidenceSummary
    allowed_decisions: Tuple[HumanDecision, ...]
    created_at: str
    timeout_at: str
    timeout_decision: HumanDecision  # Always ABORT


@dataclass(frozen=True)
class DecisionRecord:
    """Record of a human decision.
    
    Immutable audit entry.
    
    Attributes:
        decision_id: Unique decision identifier
        request_id: Link to DecisionRequest
        human_id: Identifier of deciding human
        decision: The decision made
        reason: Required for RETRY and ESCALATE
        escalation_target: Required for ESCALATE only
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
    
    Immutable chain structure.
    
    Attributes:
        audit_id: Unique audit trail identifier
        records: Immutable tuple of DecisionRecord
        session_id: Observation session ID
        head_hash: Hash of most recent record (empty if empty)
        length: Number of records
    """
    audit_id: str
    records: Tuple[DecisionRecord, ...]
    session_id: str
    head_hash: str
    length: int
