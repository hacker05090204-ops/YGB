"""
impl_v1 Phase-32 Human Decision Engine.

NON-AUTHORITATIVE MIRROR of governance Phase-32.
Contains PURE VALIDATION FUNCTIONS ONLY.

THIS MODULE HAS NO EXECUTION AUTHORITY.
THIS MODULE DOES NOT CREATE DECISIONS.
THIS MODULE DOES NOT PRESENT UI.
THIS MODULE DOES NOT ACCEPT HUMAN INPUT.

VALIDATION FUNCTIONS ONLY:
- validate_decision_id
- validate_decision_record
- validate_evidence_visibility
- validate_audit_chain
- get_decision_outcome
- is_decision_final

DENY-BY-DEFAULT:
- None → DENY / False
- Empty → DENY / False
- Invalid → DENY / False
"""
import hashlib
import re
from typing import Optional

from .phase32_types import (
    HumanDecision,
    DecisionOutcome,
    EvidenceVisibility,
)
from .phase32_context import (
    EvidenceSummary,
    DecisionRequest,
    DecisionRecord,
    DecisionAudit,
)


# Regex pattern for valid decision ID: DECISION-{8+ hex chars}
_DECISION_ID_PATTERN = re.compile(r'^DECISION-[a-fA-F0-9]{8,}$')

# Regex pattern for valid request ID: DECISION-REQ-{8+ hex chars}
_REQUEST_ID_PATTERN = re.compile(r'^DECISION-REQ-[a-fA-F0-9]{8,}$')

# Final decisions (cannot be changed)
_FINAL_DECISIONS = frozenset({HumanDecision.ABORT, HumanDecision.CONTINUE})

# Decisions requiring a reason
_REASON_REQUIRED_DECISIONS = frozenset({HumanDecision.RETRY, HumanDecision.ESCALATE})

# Valid visibility levels per evidence field
_FIELD_VISIBILITY_RULES: dict[str, EvidenceVisibility] = {
    "observation_point": EvidenceVisibility.VISIBLE,
    "evidence_type": EvidenceVisibility.VISIBLE,
    "timestamp": EvidenceVisibility.VISIBLE,
    "chain_length": EvidenceVisibility.VISIBLE,
    "execution_state": EvidenceVisibility.VISIBLE,
    "confidence_score": EvidenceVisibility.VISIBLE,
    "raw_data": EvidenceVisibility.HIDDEN,
    "self_hash": EvidenceVisibility.VISIBLE,
    "prior_hash": EvidenceVisibility.VISIBLE,
}


def validate_decision_id(decision_id: Optional[str]) -> bool:
    """Validate decision ID format.
    
    Args:
        decision_id: ID to validate
        
    Returns:
        True if valid DECISION-{hex8+} format, False otherwise
        
    Rules:
        - DENY-BY-DEFAULT
        - None → False
        - Empty → False
        - Non-string → False
        - Wrong format → False
    """
    # DENY-BY-DEFAULT: None
    if decision_id is None:
        return False
    
    # DENY-BY-DEFAULT: Non-string
    if not isinstance(decision_id, str):
        return False
    
    # DENY-BY-DEFAULT: Empty or whitespace
    if not decision_id.strip():
        return False
    
    # Validate format: DECISION-{8+ hex chars}
    if not _DECISION_ID_PATTERN.match(decision_id):
        return False
    
    return True


def validate_decision_record(record: Optional[DecisionRecord]) -> bool:
    """Validate a decision record.
    
    Args:
        record: DecisionRecord to validate
        
    Returns:
        True if valid, False otherwise
        
    Rules:
        - DENY-BY-DEFAULT
        - None → False
        - Missing required fields → False
        - Invalid decision_id format → False
        - RETRY without reason → False
        - ESCALATE without reason → False
        - ESCALATE without target → False
    """
    # DENY-BY-DEFAULT: None
    if record is None:
        return False
    
    # Validate decision_id format
    if not validate_decision_id(record.decision_id):
        return False
    
    # Validate request_id format
    if not record.request_id or not isinstance(record.request_id, str):
        return False
    if not _REQUEST_ID_PATTERN.match(record.request_id):
        return False
    
    # Validate human_id
    if not record.human_id or not isinstance(record.human_id, str):
        return False
    if not record.human_id.strip():
        return False
    
    # Validate decision is a HumanDecision
    if not isinstance(record.decision, HumanDecision):
        return False
    
    # Validate reason requirement for RETRY
    if record.decision == HumanDecision.RETRY:
        if record.reason is None or not record.reason.strip():
            return False
    
    # Validate reason and target requirement for ESCALATE
    if record.decision == HumanDecision.ESCALATE:
        if record.reason is None or not record.reason.strip():
            return False
        if record.escalation_target is None or not record.escalation_target.strip():
            return False
    
    # Validate timestamp
    if not record.timestamp or not isinstance(record.timestamp, str):
        return False
    if not record.timestamp.strip():
        return False
    
    # Validate evidence_chain_hash
    if not record.evidence_chain_hash or not isinstance(record.evidence_chain_hash, str):
        return False
    if not record.evidence_chain_hash.strip():
        return False
    
    return True


def validate_evidence_visibility(field_name: Optional[str]) -> EvidenceVisibility:
    """Validate evidence field visibility.
    
    Args:
        field_name: Name of the evidence field
        
    Returns:
        EvidenceVisibility for the field
        
    Rules:
        - DENY-BY-DEFAULT
        - None → HIDDEN
        - Empty → HIDDEN
        - Unknown field → HIDDEN
        - Known field → configured visibility
    """
    # DENY-BY-DEFAULT: None
    if field_name is None:
        return EvidenceVisibility.HIDDEN
    
    # DENY-BY-DEFAULT: Non-string
    if not isinstance(field_name, str):
        return EvidenceVisibility.HIDDEN
    
    # DENY-BY-DEFAULT: Empty
    if not field_name.strip():
        return EvidenceVisibility.HIDDEN
    
    # Look up configured visibility, default to HIDDEN
    return _FIELD_VISIBILITY_RULES.get(field_name.strip(), EvidenceVisibility.HIDDEN)


def validate_audit_chain(audit: Optional[DecisionAudit]) -> bool:
    """Validate decision audit chain integrity.
    
    Args:
        audit: Audit trail to validate
        
    Returns:
        True if chain is valid, False otherwise
        
    Rules:
        - DENY-BY-DEFAULT
        - None → False
        - Empty audit: head_hash must be empty, length must be 0
        - Length must match records count
        - Hash chain must be valid
    """
    # DENY-BY-DEFAULT: None
    if audit is None:
        return False
    
    # DENY-BY-DEFAULT: Invalid audit_id
    if not audit.audit_id or not isinstance(audit.audit_id, str):
        return False
    if not audit.audit_id.strip():
        return False
    
    # DENY-BY-DEFAULT: Invalid session_id
    if not audit.session_id or not isinstance(audit.session_id, str):
        return False
    if not audit.session_id.strip():
        return False
    
    # Empty audit validation
    if len(audit.records) == 0:
        return audit.head_hash == "" and audit.length == 0
    
    # Length must match
    if audit.length != len(audit.records):
        return False
    
    # Validate hash chain
    expected_prior_hash = ""
    computed_hash = ""
    
    for record in audit.records:
        # Validate each record
        if not validate_decision_record(record):
            return False
        
        # Compute hash for chain validation
        computed_hash = _compute_record_hash(
            record.decision_id,
            record.request_id,
            record.human_id,
            record.decision.name,
            record.timestamp,
            expected_prior_hash
        )
        
        expected_prior_hash = computed_hash
    
    # Head hash must match last computed hash
    if audit.head_hash != computed_hash:
        return False
    
    return True


def _compute_record_hash(
    decision_id: str,
    request_id: str,
    human_id: str,
    decision_name: str,
    timestamp: str,
    prior_hash: str
) -> str:
    """Compute SHA-256 hash for decision record validation.
    
    This is a PURE internal function.
    
    Args:
        decision_id: Decision ID
        request_id: Request ID
        human_id: Human identifier
        decision_name: Decision type name
        timestamp: Record timestamp
        prior_hash: Prior record hash
        
    Returns:
        Hex-encoded SHA-256 hash
    """
    hasher = hashlib.sha256()
    hasher.update(decision_id.encode('utf-8'))
    hasher.update(b'\x00')
    hasher.update(request_id.encode('utf-8'))
    hasher.update(b'\x00')
    hasher.update(human_id.encode('utf-8'))
    hasher.update(b'\x00')
    hasher.update(decision_name.encode('utf-8'))
    hasher.update(b'\x00')
    hasher.update(timestamp.encode('utf-8'))
    hasher.update(b'\x00')
    hasher.update(prior_hash.encode('utf-8'))
    return hasher.hexdigest()


def get_decision_outcome(
    record: Optional[DecisionRecord],
    current_state: Optional[str]
) -> DecisionOutcome:
    """Determine decision outcome based on record and state.
    
    Args:
        record: Decision record to evaluate
        current_state: Current execution state name
        
    Returns:
        DecisionOutcome indicating result
        
    Rules:
        - DENY-BY-DEFAULT
        - None record → REJECTED
        - Empty state → REJECTED
        - Invalid record → REJECTED
        - ABORT decision → APPLIED (always allowed)
        - Valid record + valid state → PENDING (safe default)
    """
    # DENY-BY-DEFAULT: None record
    if record is None:
        return DecisionOutcome.REJECTED
    
    # DENY-BY-DEFAULT: Invalid record
    if not validate_decision_record(record):
        return DecisionOutcome.REJECTED
    
    # DENY-BY-DEFAULT: None state
    if current_state is None:
        return DecisionOutcome.REJECTED
    
    # DENY-BY-DEFAULT: Empty state
    if not isinstance(current_state, str) or not current_state.strip():
        return DecisionOutcome.REJECTED
    
    # ABORT is always allowed (safety default)
    if record.decision == HumanDecision.ABORT:
        return DecisionOutcome.APPLIED
    
    # For all other decisions, return PENDING (safe default)
    # Actual application requires external validation
    return DecisionOutcome.PENDING


def is_decision_final(decision: Optional[HumanDecision]) -> bool:
    """Check if a decision type is final (cannot be changed).
    
    Args:
        decision: Decision type to check
        
    Returns:
        True if final, False otherwise
        
    Rules:
        - DENY-BY-DEFAULT
        - None → False
        - Non-HumanDecision → False
        - ABORT → True (final)
        - CONTINUE → True (final, moves to next step)
        - RETRY → False (can be changed)
        - ESCALATE → False (awaiting higher authority)
    """
    # DENY-BY-DEFAULT: None
    if decision is None:
        return False
    
    # DENY-BY-DEFAULT: Non-HumanDecision
    if not isinstance(decision, HumanDecision):
        return False
    
    # Check if in final set
    return decision in _FINAL_DECISIONS
