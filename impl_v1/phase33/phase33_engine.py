"""
impl_v1 Phase-33 Intent Engine.

NON-AUTHORITATIVE MIRROR of governance Phase-33.
Contains PURE VALIDATION FUNCTIONS ONLY.

THIS MODULE HAS NO EXECUTION AUTHORITY.
THIS MODULE DOES NOT CREATE INTENTS.
THIS MODULE DOES NOT REVOKE INTENTS.
THIS MODULE DOES NOT BIND DECISIONS.

VALIDATION FUNCTIONS ONLY:
- validate_intent_id
- validate_intent_hash
- validate_decision_binding
- is_intent_revoked
- validate_audit_chain
- get_intent_state

DENY-BY-DEFAULT:
- None → DENY / False
- Empty → DENY / False
- Invalid → DENY / False
"""
import hashlib
import re
from typing import Optional

from .phase33_types import (
    IntentStatus,
    BindingResult,
)
from .phase33_context import (
    ExecutionIntent,
    IntentAudit,
)


# Regex pattern for valid intent ID: INTENT-{8+ hex chars}
_INTENT_ID_PATTERN = re.compile(r'^INTENT-[a-fA-F0-9]{8,}$')

# Valid decision types (from Phase-32)
_VALID_DECISION_TYPES = frozenset({
    "CONTINUE", "RETRY", "ABORT", "ESCALATE"
})


def validate_intent_id(intent_id: Optional[str]) -> bool:
    """Validate intent ID format.
    
    Args:
        intent_id: ID to validate
        
    Returns:
        True if valid INTENT-{hex8+} format, False otherwise
        
    Rules:
        - DENY-BY-DEFAULT
        - None → False
        - Empty → False
        - Non-string → False
        - Wrong format → False
    """
    # DENY-BY-DEFAULT: None
    if intent_id is None:
        return False
    
    # DENY-BY-DEFAULT: Non-string
    if not isinstance(intent_id, str):
        return False
    
    # DENY-BY-DEFAULT: Empty or whitespace
    if not intent_id.strip():
        return False
    
    # Validate format: INTENT-{8+ hex chars}
    if not _INTENT_ID_PATTERN.match(intent_id):
        return False
    
    return True


def validate_intent_hash(intent: Optional[ExecutionIntent]) -> bool:
    """Validate intent hash matches computed hash.
    
    Args:
        intent: ExecutionIntent to validate
        
    Returns:
        True if hash is valid, False otherwise
        
    Rules:
        - DENY-BY-DEFAULT
        - None → False
        - Empty hash → False
        - Tampered hash → False
    """
    # DENY-BY-DEFAULT: None
    if intent is None:
        return False
    
    # DENY-BY-DEFAULT: Empty hash
    if not intent.intent_hash:
        return False
    
    # Compute expected hash
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
    
    # Compare hashes
    return intent.intent_hash == expected_hash


def _compute_intent_hash(
    intent_id: str,
    decision_id: str,
    decision_type: str,
    evidence_chain_hash: str,
    session_id: str,
    execution_state: str,
    created_at: str,
    created_by: str
) -> str:
    """Compute SHA-256 hash for intent validation.
    
    This is a PURE internal function.
    
    Args:
        intent_id: Intent ID
        decision_id: Decision ID
        decision_type: Decision type
        evidence_chain_hash: Evidence hash
        session_id: Session ID
        execution_state: Execution state
        created_at: Timestamp
        created_by: Human identifier
        
    Returns:
        Hex-encoded SHA-256 hash
    """
    hasher = hashlib.sha256()
    hasher.update(intent_id.encode('utf-8'))
    hasher.update(b'\x00')
    hasher.update(decision_id.encode('utf-8'))
    hasher.update(b'\x00')
    hasher.update(decision_type.encode('utf-8'))
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


def validate_decision_binding(intent: Optional[ExecutionIntent]) -> BindingResult:
    """Validate that intent is properly bound to a decision.
    
    Args:
        intent: ExecutionIntent to validate
        
    Returns:
        BindingResult indicating validation result
        
    Rules:
        - DENY-BY-DEFAULT
        - None → REJECTED
        - Missing fields → MISSING_FIELD
        - Invalid decision type → INVALID_DECISION
        - Valid → SUCCESS
    """
    # DENY-BY-DEFAULT: None
    if intent is None:
        return BindingResult.REJECTED
    
    # Check required fields
    if not intent.intent_id or not intent.intent_id.strip():
        return BindingResult.MISSING_FIELD
    
    if not intent.decision_id or not intent.decision_id.strip():
        return BindingResult.MISSING_FIELD
    
    if not intent.decision_type or not intent.decision_type.strip():
        return BindingResult.MISSING_FIELD
    
    if not intent.session_id or not intent.session_id.strip():
        return BindingResult.MISSING_FIELD
    
    if not intent.created_by or not intent.created_by.strip():
        return BindingResult.MISSING_FIELD
    
    if not intent.created_at or not intent.created_at.strip():
        return BindingResult.MISSING_FIELD
    
    # Validate decision type
    if intent.decision_type not in _VALID_DECISION_TYPES:
        return BindingResult.INVALID_DECISION
    
    # Validate intent ID format
    if not validate_intent_id(intent.intent_id):
        return BindingResult.REJECTED
    
    return BindingResult.SUCCESS


def is_intent_revoked(
    intent_id: Optional[str],
    audit: Optional[IntentAudit]
) -> bool:
    """Check if intent has been revoked.
    
    Args:
        intent_id: Intent ID to check
        audit: Audit trail to search
        
    Returns:
        True if revoked, False otherwise
        
    Rules:
        - DENY-BY-DEFAULT for invalid inputs
        - Searches for REVOCATION record type
    """
    # DENY-BY-DEFAULT: None inputs
    if intent_id is None or audit is None:
        return False
    
    # DENY-BY-DEFAULT: Empty intent_id
    if not intent_id:
        return False
    
    # Search for revocation record
    for record in audit.records:
        if (record.intent_id == intent_id and 
            record.record_type == "REVOCATION"):
            return True
    
    return False


def validate_audit_chain(audit: Optional[IntentAudit]) -> bool:
    """Validate intent audit chain integrity.
    
    Args:
        audit: Audit trail to validate
        
    Returns:
        True if chain is valid, False otherwise
        
    Rules:
        - DENY-BY-DEFAULT
        - Empty audit: head_hash must be empty, length must be 0
        - Length must match records count
        - Hash chain must be valid
    """
    # DENY-BY-DEFAULT: None
    if audit is None:
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


def _compute_record_hash(
    record_id: str,
    record_type: str,
    intent_id: str,
    timestamp: str,
    prior_hash: str
) -> str:
    """Compute SHA-256 hash for audit record validation.
    
    This is a PURE internal function.
    
    Args:
        record_id: Record ID
        record_type: Record type
        intent_id: Intent ID
        timestamp: Record timestamp
        prior_hash: Prior record hash
        
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


def get_intent_state(intent: Optional[ExecutionIntent], audit: Optional[IntentAudit]) -> IntentStatus:
    """Get current state of an intent.
    
    Args:
        intent: Intent to check
        audit: Audit trail for revocation check
        
    Returns:
        IntentStatus indicating current state
        
    Rules:
        - DENY-BY-DEFAULT
        - None intent → REVOKED (safest assumption)
        - Revoked in audit → REVOKED
        - Otherwise → PENDING (default safe state)
    """
    # DENY-BY-DEFAULT: None intent → treat as revoked (safest)
    if intent is None:
        return IntentStatus.REVOKED
    
    # Check if revoked
    if audit is not None and is_intent_revoked(intent.intent_id, audit):
        return IntentStatus.REVOKED
    
    # Default to PENDING (safe state, no execution implied)
    return IntentStatus.PENDING
