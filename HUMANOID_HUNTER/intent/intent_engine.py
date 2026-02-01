"""
Phase-33 Intent Engine.

This module provides intent binding functions.

All functions are PURE (no side effects).
Intent is DATA, not action.
Systems bind, never decide.

HUMANS DECIDE.
SYSTEMS BIND INTENT.
EXECUTION WAITS.

CORE RULES:
- Deny-by-default
- One decision → one intent
- Revocation is permanent
- Audit is append-only
"""
import hashlib
import uuid
from typing import Optional, Tuple, Set

from HUMANOID_HUNTER.decision import DecisionRecord, HumanDecision

from .intent_types import IntentStatus, BindingResult
from .intent_context import (
    ExecutionIntent,
    IntentRevocation,
    IntentRecord,
    IntentAudit
)


# Track bound decisions to prevent duplicates (in-memory for pure function use)
# In real implementation, this would be persisted
_BOUND_DECISIONS: Set[str] = set()


def _compute_intent_hash(
    intent_id: str,
    decision_id: str,
    decision_type: HumanDecision,
    evidence_chain_hash: str,
    session_id: str,
    execution_state: str,
    created_at: str,
    created_by: str
) -> str:
    """Compute SHA-256 hash for an execution intent.
    
    Args:
        intent_id: Intent identifier
        decision_id: Decision identifier
        decision_type: Decision type
        evidence_chain_hash: Evidence hash
        session_id: Session identifier
        execution_state: Execution state
        created_at: Creation timestamp
        created_by: Creator identifier
        
    Returns:
        Hex-encoded SHA-256 hash
    """
    hasher = hashlib.sha256()
    hasher.update(intent_id.encode('utf-8'))
    hasher.update(b'\x00')
    hasher.update(decision_id.encode('utf-8'))
    hasher.update(b'\x00')
    hasher.update(decision_type.name.encode('utf-8'))
    hasher.update(b'\x00')
    hasher.update(evidence_chain_hash.encode('utf-8'))
    hasher.update(b'\x00')
    hasher.update(session_id.encode('utf-8'))
    hasher.update(b'\x00')
    hasher.update(execution_state.encode('utf-8'))
    hasher.update(b'\x00')
    hasher.update(created_at.encode('utf-8'))
    hasher.update(b'\x00')
    hasher.update(created_by.encode('utf-8'))
    return hasher.hexdigest()


def _compute_revocation_hash(
    revocation_id: str,
    intent_id: str,
    revoked_by: str,
    revocation_reason: str,
    revoked_at: str
) -> str:
    """Compute SHA-256 hash for a revocation.
    
    Args:
        revocation_id: Revocation identifier
        intent_id: Intent being revoked
        revoked_by: Human revoking
        revocation_reason: Reason for revocation
        revoked_at: Revocation timestamp
        
    Returns:
        Hex-encoded SHA-256 hash
    """
    hasher = hashlib.sha256()
    hasher.update(revocation_id.encode('utf-8'))
    hasher.update(b'\x00')
    hasher.update(intent_id.encode('utf-8'))
    hasher.update(b'\x00')
    hasher.update(revoked_by.encode('utf-8'))
    hasher.update(b'\x00')
    hasher.update(revocation_reason.encode('utf-8'))
    hasher.update(b'\x00')
    hasher.update(revoked_at.encode('utf-8'))
    return hasher.hexdigest()


def _compute_record_hash(
    record_id: str,
    record_type: str,
    intent_id: str,
    timestamp: str,
    prior_hash: str
) -> str:
    """Compute SHA-256 hash for an audit record.
    
    Args:
        record_id: Record identifier
        record_type: Type of record
        intent_id: Related intent
        timestamp: Record timestamp
        prior_hash: Hash of prior record
        
    Returns:
        Hex-encoded SHA-256 hash
    """
    hasher = hashlib.sha256()
    hasher.update(record_id.encode('utf-8'))
    hasher.update(b'\x00')
    hasher.update(record_type.encode('utf-8'))
    hasher.update(b'\x00')
    hasher.update(intent_id.encode('utf-8'))
    hasher.update(b'\x00')
    hasher.update(timestamp.encode('utf-8'))
    hasher.update(b'\x00')
    hasher.update(prior_hash.encode('utf-8'))
    return hasher.hexdigest()


def bind_decision(
    decision_record: DecisionRecord,
    evidence_chain_hash: str,
    session_id: str,
    execution_state: str,
    timestamp: str
) -> Tuple[BindingResult, Optional[ExecutionIntent]]:
    """Bind a human decision to an execution intent.
    
    Args:
        decision_record: Phase-32 decision record
        evidence_chain_hash: Phase-31 evidence chain hash
        session_id: Observation session ID
        execution_state: Current execution loop state
        timestamp: Binding timestamp
        
    Returns:
        Tuple of (BindingResult, ExecutionIntent or None)
        
    Rules:
        - Pure function (no I/O)
        - Validates all fields
        - Computes intent_hash
        - Returns immutable intent
        - Fails on invalid input (deny-by-default)
    """
    # Validate decision_record
    if decision_record is None:
        return (BindingResult.INVALID_DECISION, None)
    
    # Validate required fields are non-empty
    if not decision_record.decision_id or not decision_record.decision_id.strip():
        return (BindingResult.MISSING_FIELD, None)
    
    if not decision_record.human_id or not decision_record.human_id.strip():
        return (BindingResult.MISSING_FIELD, None)
    
    if not evidence_chain_hash or not evidence_chain_hash.strip():
        return (BindingResult.MISSING_FIELD, None)
    
    if not session_id or not session_id.strip():
        return (BindingResult.MISSING_FIELD, None)
    
    if not execution_state or not execution_state.strip():
        return (BindingResult.MISSING_FIELD, None)
    
    if not timestamp or not timestamp.strip():
        return (BindingResult.MISSING_FIELD, None)
    
    # Validate decision type is known (defensive - always true for valid DecisionRecord)
    if decision_record.decision not in HumanDecision:  # pragma: no cover
        return (BindingResult.INVALID_DECISION, None)
    
    # Check for duplicate binding
    if decision_record.decision_id in _BOUND_DECISIONS:
        return (BindingResult.DUPLICATE, None)
    
    # Generate intent ID
    intent_id = f"INTENT-{uuid.uuid4().hex[:8]}"
    
    # Compute intent hash
    intent_hash = _compute_intent_hash(
        intent_id,
        decision_record.decision_id,
        decision_record.decision,
        evidence_chain_hash,
        session_id,
        execution_state,
        timestamp,
        decision_record.human_id
    )
    
    # Create immutable intent
    intent = ExecutionIntent(
        intent_id=intent_id,
        decision_id=decision_record.decision_id,
        decision_type=decision_record.decision,
        evidence_chain_hash=evidence_chain_hash,
        session_id=session_id,
        execution_state=execution_state,
        created_at=timestamp,
        created_by=decision_record.human_id,
        intent_hash=intent_hash
    )
    
    # Record binding
    _BOUND_DECISIONS.add(decision_record.decision_id)
    
    return (BindingResult.SUCCESS, intent)


def validate_intent(
    intent: ExecutionIntent,
    decision_record: DecisionRecord
) -> bool:
    """Validate intent matches its source decision.
    
    Args:
        intent: Intent to validate
        decision_record: Original decision
        
    Returns:
        True if valid, False otherwise
        
    Checks:
        - Decision ID matches
        - Decision type matches
        - Hash is valid (recomputed)
    """
    if intent is None or decision_record is None:
        return False
    
    # Check decision ID matches
    if intent.decision_id != decision_record.decision_id:
        return False
    
    # Check decision type matches
    if intent.decision_type != decision_record.decision:
        return False
    
    # Recompute hash and verify
    expected_hash = _compute_intent_hash(
        intent.intent_id,
        intent.decision_id,
        intent.decision_type,
        intent.evidence_chain_hash,
        intent.session_id,
        intent.execution_state,
        intent.created_at,
        intent.created_by
    )
    
    if intent.intent_hash != expected_hash:
        return False
    
    return True


def revoke_intent(
    intent: ExecutionIntent,
    revoked_by: str,
    reason: str,
    timestamp: str
) -> IntentRevocation:
    """Create revocation for an intent.
    
    Args:
        intent: Intent to revoke
        revoked_by: Human revoking
        reason: Mandatory reason
        timestamp: Revocation time
        
    Returns:
        IntentRevocation record
        
    Raises:
        ValueError: If reason is missing
        
    Rules:
        - Revocation is permanent
        - Reason is required
        - Creates immutable record
    """
    if not revoked_by or not revoked_by.strip():
        raise ValueError("revoked_by is required")
    
    if not reason or not reason.strip():
        raise ValueError("revocation reason is required")
    
    if not timestamp or not timestamp.strip():
        raise ValueError("timestamp is required")
    
    revocation_id = f"REVOKE-{uuid.uuid4().hex[:8]}"
    
    revocation_hash = _compute_revocation_hash(
        revocation_id,
        intent.intent_id,
        revoked_by,
        reason,
        timestamp
    )
    
    return IntentRevocation(
        revocation_id=revocation_id,
        intent_id=intent.intent_id,
        revoked_by=revoked_by,
        revocation_reason=reason,
        revoked_at=timestamp,
        revocation_hash=revocation_hash
    )


def record_intent(
    audit: IntentAudit,
    intent_id: str,
    record_type: str,
    timestamp: str
) -> IntentAudit:
    """Record intent event in audit trail.
    
    Args:
        audit: Current audit trail
        intent_id: Intent to record
        record_type: "BINDING" or "REVOCATION"
        timestamp: Record timestamp
        
    Returns:
        NEW IntentAudit with appended record
        
    Raises:
        ValueError: If record_type is invalid
        
    Rules:
        - Audit is append-only
        - Hash chain maintained
        - Returns new structure (immutable)
    """
    if record_type not in ("BINDING", "REVOCATION"):
        raise ValueError(f"Invalid record_type: {record_type}")
    
    record_id = f"REC-{uuid.uuid4().hex[:8]}"
    prior_hash = audit.head_hash
    
    # Compute record hash
    self_hash = _compute_record_hash(
        record_id,
        record_type,
        intent_id,
        timestamp,
        prior_hash
    )
    
    # Create record
    record = IntentRecord(
        record_id=record_id,
        record_type=record_type,
        intent_id=intent_id,
        timestamp=timestamp,
        prior_hash=prior_hash,
        self_hash=self_hash
    )
    
    # Return new audit trail (immutable append)
    return IntentAudit(
        audit_id=audit.audit_id,
        records=audit.records + (record,),
        session_id=audit.session_id,
        head_hash=self_hash,
        length=audit.length + 1
    )


def create_empty_audit(session_id: str, audit_id: Optional[str] = None) -> IntentAudit:
    """Create empty intent audit trail.
    
    Args:
        session_id: Session identifier
        audit_id: Optional audit ID (generated if not provided)
        
    Returns:
        Empty IntentAudit ready for appending
    """
    if audit_id is None:
        audit_id = f"IAUDIT-{uuid.uuid4().hex[:8]}"
    
    return IntentAudit(
        audit_id=audit_id,
        records=(),
        session_id=session_id,
        head_hash="",
        length=0
    )


def is_intent_revoked(
    intent_id: str,
    audit: IntentAudit
) -> bool:
    """Check if intent has been revoked.
    
    Args:
        intent_id: Intent to check
        audit: Audit trail to search
        
    Returns:
        True if revoked, False otherwise
    """
    for record in audit.records:
        if record.intent_id == intent_id and record.record_type == "REVOCATION":
            return True
    return False


def validate_audit_chain(audit: IntentAudit) -> bool:
    """Validate intent audit chain integrity.
    
    Args:
        audit: Audit trail to validate
        
    Returns:
        True if chain is valid, False otherwise
    """
    # Empty audit is valid
    if audit.length == 0:
        return audit.head_hash == "" and len(audit.records) == 0
    
    # Length must match
    if audit.length != len(audit.records):
        return False
    
    # Validate hash chain
    expected_prior_hash = ""
    computed_hash = ""
    
    for record in audit.records:
        if record.prior_hash != expected_prior_hash:
            return False
        
        computed_hash = _compute_record_hash(
            record.record_id,
            record.record_type,
            record.intent_id,
            record.timestamp,
            expected_prior_hash
        )
        
        if record.self_hash != computed_hash:
            return False
        
        expected_prior_hash = computed_hash
    
    # Head hash must match last computed hash
    if audit.head_hash != computed_hash:
        return False
    
    return True


def clear_bound_decisions() -> None:
    """Clear bound decisions set (for testing only).
    
    WARNING: This is for test isolation only.
    """
    _BOUND_DECISIONS.clear()
