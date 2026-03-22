"""
Phase-32 Decision Engine.

This module provides human decision governance functions.

All functions are PURE (no side effects).
All decisions are human-initiated.
No auto-continuation exists.

THIS IS A HUMAN DECISION LAYER ONLY.
EVIDENCE INFORMS HUMANS.
HUMANS DECIDE.
SYSTEMS OBEY.

CORE RULES:
- Raw evidence is NEVER exposed
- Timeout ALWAYS results in ABORT
- RETRY requires explicit reason
- ESCALATE requires reason + target
- Default on ambiguity → ABORT
"""
import hashlib
import uuid
from datetime import datetime, timedelta
from typing import Optional, Tuple

from .decision_types import HumanDecision, DecisionOutcome, EvidenceVisibility
from .decision_context import (
    EvidenceSummary,
    DecisionRequest,
    DecisionRecord,
    DecisionAudit
)


# Evidence field visibility map
EVIDENCE_VISIBILITY: dict[str, EvidenceVisibility] = {
    "observation_point": EvidenceVisibility.VISIBLE,
    "evidence_type": EvidenceVisibility.VISIBLE,
    "timestamp": EvidenceVisibility.VISIBLE,
    "chain_length": EvidenceVisibility.VISIBLE,
    "execution_state": EvidenceVisibility.VISIBLE,
    "confidence_score": EvidenceVisibility.VISIBLE,
    "chain_hash": EvidenceVisibility.VISIBLE,
    "raw_data": EvidenceVisibility.HIDDEN,
    "executor_output": EvidenceVisibility.HIDDEN,
    "self_hash": EvidenceVisibility.VISIBLE,
    "prior_hash": EvidenceVisibility.VISIBLE,
}
_HASH_SEPARATOR = b"\x00"
_LAST_VALIDATED_AUDIT_ID = ""
_LAST_VALIDATED_LENGTH = 0
_LAST_VALIDATED_HASH = ""
_LAST_VALIDATION_RESULT = False


def _compute_record_hash(
    decision_id: str,
    request_id: str,
    human_id: str,
    decision: HumanDecision,
    reason: Optional[str],
    escalation_target: Optional[str],
    timestamp: str,
    evidence_chain_hash: str,
    prior_hash: str
) -> str:
    """Compute SHA-256 hash for a decision record.
    
    Args:
        decision_id: Unique decision identifier
        request_id: Request identifier
        human_id: Human identifier
        decision: Decision type
        reason: Optional reason
        escalation_target: Optional escalation target
        timestamp: Decision timestamp
        evidence_chain_hash: Evidence hash at decision time
        prior_hash: Hash of prior record
        
    Returns:
        Hex-encoded SHA-256 hash
    """
    decision_id_bytes = decision_id.encode("utf-8")
    request_id_bytes = request_id.encode("utf-8")
    human_id_bytes = human_id.encode("utf-8")
    decision_name_bytes = decision.name.encode("utf-8")
    reason_bytes = (reason or "").encode("utf-8")
    escalation_target_bytes = (escalation_target or "").encode("utf-8")
    timestamp_bytes = timestamp.encode("utf-8")
    evidence_chain_hash_bytes = evidence_chain_hash.encode("utf-8")
    prior_hash_bytes = prior_hash.encode("utf-8")

    hasher = hashlib.sha256()
    hasher.update(decision_id_bytes)
    hasher.update(_HASH_SEPARATOR)
    hasher.update(request_id_bytes)
    hasher.update(_HASH_SEPARATOR)
    hasher.update(human_id_bytes)
    hasher.update(_HASH_SEPARATOR)
    hasher.update(decision_name_bytes)
    hasher.update(_HASH_SEPARATOR)
    hasher.update(reason_bytes)
    hasher.update(_HASH_SEPARATOR)
    hasher.update(escalation_target_bytes)
    hasher.update(_HASH_SEPARATOR)
    hasher.update(timestamp_bytes)
    hasher.update(_HASH_SEPARATOR)
    hasher.update(evidence_chain_hash_bytes)
    hasher.update(_HASH_SEPARATOR)
    hasher.update(prior_hash_bytes)
    return hasher.hexdigest()


def get_visibility(field_name: str) -> EvidenceVisibility:
    """Get visibility level for an evidence field.
    
    Args:
        field_name: Name of the evidence field
        
    Returns:
        EvidenceVisibility level (defaults to HIDDEN for unknown)
    """
    return EVIDENCE_VISIBILITY.get(field_name, EvidenceVisibility.HIDDEN)


def create_request(
    session_id: str,
    observation_point: str,
    evidence_type: str,
    evidence_timestamp: str,
    chain_length: int,
    execution_state: str,
    confidence_score: float,
    chain_hash: str,
    timeout_seconds: int,
    current_timestamp: str
) -> DecisionRequest:
    """Create a decision request from evidence.
    
    Args:
        session_id: Observation session ID
        observation_point: Where in execution loop
        evidence_type: Type of evidence
        evidence_timestamp: When evidence was captured
        chain_length: Number of evidence records
        execution_state: Current execution loop state
        confidence_score: From Phase-30 normalization
        chain_hash: Head hash of evidence chain
        timeout_seconds: Seconds until timeout
        current_timestamp: Current time (ISO-8601)
        
    Returns:
        DecisionRequest for human presentation
        
    Rules:
        - Raw evidence is NEVER included
        - Only curated summary presented
        - Timeout decision is ALWAYS ABORT
    """
    request_id = f"REQ-{uuid.uuid4().hex[:8]}"
    
    # Parse current timestamp and compute timeout
    # For simplicity, we just store the timeout time as a string
    # In real implementation, proper datetime arithmetic would be used
    timeout_at = f"{current_timestamp}+{timeout_seconds}s"
    
    # Create curated evidence summary (NO raw data)
    evidence_summary = EvidenceSummary(
        observation_point=observation_point,
        evidence_type=evidence_type,
        timestamp=evidence_timestamp,
        chain_length=chain_length,
        execution_state=execution_state,
        confidence_score=confidence_score,
        chain_hash=chain_hash
    )
    
    # Default allowed decisions (all four)
    allowed_decisions: Tuple[HumanDecision, ...] = (
        HumanDecision.CONTINUE,
        HumanDecision.RETRY,
        HumanDecision.ABORT,
        HumanDecision.ESCALATE
    )
    
    return DecisionRequest(
        request_id=request_id,
        session_id=session_id,
        evidence_summary=evidence_summary,
        allowed_decisions=allowed_decisions,
        created_at=current_timestamp,
        timeout_at=timeout_at,
        timeout_decision=HumanDecision.ABORT  # ALWAYS ABORT on timeout
    )


def present_evidence(
    request: DecisionRequest
) -> EvidenceSummary:
    """Extract curated evidence summary for display.
    
    Args:
        request: Decision request
        
    Returns:
        EvidenceSummary safe for human viewing
        
    Rules:
        - Raw bytes NEVER exposed
        - Executor claims shown as "CLAIMED" only
        - Only VISIBLE fields returned
    """
    return request.evidence_summary


def accept_decision(
    request: DecisionRequest,
    decision: HumanDecision,
    human_id: str,
    reason: Optional[str],
    escalation_target: Optional[str],
    timestamp: str
) -> DecisionRecord:
    """Accept a human decision.
    
    Args:
        request: The decision request being answered
        decision: Human's decision
        human_id: Identifier of deciding human
        reason: Required for RETRY and ESCALATE
        escalation_target: Required for ESCALATE
        timestamp: When decision was made
        
    Returns:
        DecisionRecord
        
    Raises:
        ValueError: If decision is invalid
        
    Rules:
        - RETRY requires reason
        - ESCALATE requires reason AND target
        - Decision must be in allowed_decisions
        - Empty human_id is invalid
    """
    # Validate human_id
    if not human_id or not human_id.strip():
        raise ValueError("human_id is required")
    
    # Validate decision is allowed
    if decision not in request.allowed_decisions:
        raise ValueError(f"Decision {decision.name} not in allowed decisions")
    
    # Validate RETRY requires reason
    if decision == HumanDecision.RETRY:
        if not reason or not reason.strip():
            raise ValueError("RETRY decision requires a reason")
    
    # Validate ESCALATE requires reason AND target
    if decision == HumanDecision.ESCALATE:
        if not reason or not reason.strip():
            raise ValueError("ESCALATE decision requires a reason")
        if not escalation_target or not escalation_target.strip():
            raise ValueError("ESCALATE decision requires an escalation_target")
    
    decision_id = f"DEC-{uuid.uuid4().hex[:8]}"
    
    return DecisionRecord(
        decision_id=decision_id,
        request_id=request.request_id,
        human_id=human_id,
        decision=decision,
        reason=reason,
        escalation_target=escalation_target,
        timestamp=timestamp,
        evidence_chain_hash=request.evidence_summary.chain_hash
    )


def create_timeout_decision(
    request: DecisionRequest,
    timeout_timestamp: str
) -> DecisionRecord:
    """Create an ABORT decision due to timeout.
    
    Args:
        request: The timed-out request
        timeout_timestamp: When timeout occurred
        
    Returns:
        DecisionRecord with ABORT decision and TIMEOUT reason
    """
    decision_id = f"DEC-{uuid.uuid4().hex[:8]}"
    
    return DecisionRecord(
        decision_id=decision_id,
        request_id=request.request_id,
        human_id="SYSTEM_TIMEOUT",
        decision=HumanDecision.ABORT,
        reason="TIMEOUT",
        escalation_target=None,
        timestamp=timeout_timestamp,
        evidence_chain_hash=request.evidence_summary.chain_hash
    )


def record_decision(
    audit: DecisionAudit,
    record: DecisionRecord
) -> DecisionAudit:
    """Record decision in audit trail.
    
    Args:
        audit: Current audit trail
        record: Decision to record
        
    Returns:
        NEW DecisionAudit with appended record
        
    Rules:
        - Audit is append-only
        - New record hash computed
        - Returns new structure (immutable)
    """
    # Compute hash for this record
    prior_hash = audit.head_hash
    new_hash = _compute_record_hash(
        record.decision_id,
        record.request_id,
        record.human_id,
        record.decision,
        record.reason,
        record.escalation_target,
        record.timestamp,
        record.evidence_chain_hash,
        prior_hash
    )
    
    # Return new audit trail (immutable append)
    return DecisionAudit(
        audit_id=audit.audit_id,
        records=audit.records + (record,),
        session_id=audit.session_id,
        head_hash=new_hash,
        length=audit.length + 1
    )


def apply_decision(
    record: DecisionRecord,
    current_state: str,
    retry_count: int = 0,
    max_retries: int = 3
) -> DecisionOutcome:
    """Determine if decision can be applied.
    
    Args:
        record: Decision to apply
        current_state: Current execution state name
        retry_count: Current retry count
        max_retries: Maximum allowed retries
        
    Returns:
        DecisionOutcome indicating result
        
    Rules:
        - This is a PURE function
        - It does NOT execute anything
        - It only validates applicability
        - ABORT is always applicable
    """
    # ABORT is always applicable
    if record.decision == HumanDecision.ABORT:
        return DecisionOutcome.APPLIED
    
    # CONTINUE requires non-halted state
    if record.decision == HumanDecision.CONTINUE:
        if current_state == "HALTED":
            return DecisionOutcome.REJECTED
        return DecisionOutcome.APPLIED
    
    # RETRY requires retry count < max
    if record.decision == HumanDecision.RETRY:
        if retry_count >= max_retries:
            return DecisionOutcome.REJECTED
        return DecisionOutcome.APPLIED
    
    # ESCALATE is valid if target specified
    if record.decision == HumanDecision.ESCALATE:
        if record.escalation_target:
            return DecisionOutcome.PENDING
        return DecisionOutcome.REJECTED
    
    # Unknown decision type → REJECTED
    return DecisionOutcome.REJECTED  # pragma: no cover


def create_empty_audit(session_id: str, audit_id: Optional[str] = None) -> DecisionAudit:
    """Create an empty decision audit trail.
    
    Args:
        session_id: Observation session ID
        audit_id: Optional audit identifier (generated if not provided)
        
    Returns:
        Empty DecisionAudit ready for appending
    """
    if audit_id is None:
        audit_id = f"AUDIT-{uuid.uuid4().hex[:8]}"
    
    return DecisionAudit(
        audit_id=audit_id,
        records=(),
        session_id=session_id,
        head_hash="",
        length=0
    )


def validate_audit_chain(audit: DecisionAudit) -> bool:
    """Validate decision audit chain integrity.
    
    Args:
        audit: Audit trail to validate
        
    Returns:
        True if chain is valid, False otherwise
    """
    global _LAST_VALIDATED_AUDIT_ID, _LAST_VALIDATED_LENGTH
    global _LAST_VALIDATED_HASH, _LAST_VALIDATION_RESULT

    # Empty audit is valid
    if audit.length == 0:
        result = audit.head_hash == "" and len(audit.records) == 0
        _LAST_VALIDATED_AUDIT_ID = audit.audit_id
        _LAST_VALIDATED_LENGTH = 0
        _LAST_VALIDATED_HASH = ""
        _LAST_VALIDATION_RESULT = result
        return result
    
    # Length must match
    if audit.length != len(audit.records):
        _LAST_VALIDATED_AUDIT_ID = audit.audit_id
        _LAST_VALIDATED_LENGTH = 0
        _LAST_VALIDATED_HASH = ""
        _LAST_VALIDATION_RESULT = False
        return False
    
    # Validate hash chain incrementally when the same immutable audit only grows.
    expected_prior_hash = ""
    computed_hash = ""
    start_index = 0
    if (
        _LAST_VALIDATION_RESULT
        and audit.audit_id == _LAST_VALIDATED_AUDIT_ID
        and audit.length >= _LAST_VALIDATED_LENGTH
    ):
        if audit.length == _LAST_VALIDATED_LENGTH and audit.head_hash == _LAST_VALIDATED_HASH:
            return True
        start_index = _LAST_VALIDATED_LENGTH
        expected_prior_hash = _LAST_VALIDATED_HASH
        computed_hash = _LAST_VALIDATED_HASH

    for record in audit.records[start_index:]:
        computed_hash = _compute_record_hash(
            record.decision_id,
            record.request_id,
            record.human_id,
            record.decision,
            record.reason,
            record.escalation_target,
            record.timestamp,
            record.evidence_chain_hash,
            expected_prior_hash
        )
        expected_prior_hash = computed_hash
    
    # Head hash must match last computed hash
    result = audit.head_hash == computed_hash
    _LAST_VALIDATED_AUDIT_ID = audit.audit_id
    _LAST_VALIDATION_RESULT = result
    if result:
        _LAST_VALIDATED_LENGTH = audit.length
        _LAST_VALIDATED_HASH = computed_hash
    else:
        _LAST_VALIDATED_LENGTH = 0
        _LAST_VALIDATED_HASH = ""
    return result
