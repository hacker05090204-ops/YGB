"""
impl_v1 Phase-34 Authorization Engine.

NON-AUTHORITATIVE MIRROR of governance Phase-34.
Contains PURE VALIDATION FUNCTIONS ONLY.

THIS MODULE HAS NO EXECUTION AUTHORITY.
THIS MODULE DOES NOT CREATE RECORDS.
THIS MODULE DOES NOT ISSUE AUTHORIZATIONS.

VALIDATION FUNCTIONS ONLY:
- validate_authorization_id
- validate_authorization_hash
- validate_authorization_status
- is_authorization_revoked
- validate_audit_chain
- get_authorization_decision

DENY-BY-DEFAULT:
- None → DENY / False
- Empty → DENY / False
- Invalid → DENY / False
"""
import hashlib
import re
from typing import Optional

from .phase34_types import (
    AuthorizationStatus,
    AuthorizationDecision,
    ALLOW_STATUSES,
)
from .phase34_context import (
    ExecutionAuthorization,
    AuthorizationAudit,
)


# Regex pattern for valid authorization ID: AUTH-{8+ hex chars}
_AUTH_ID_PATTERN = re.compile(r'^AUTH-[a-fA-F0-9]{8,}$')


def validate_authorization_id(authorization_id: Optional[str]) -> bool:
    """Validate authorization ID format.
    
    Args:
        authorization_id: ID to validate
        
    Returns:
        True if valid AUTH-{hex8+} format, False otherwise
        
    Rules:
        - DENY-BY-DEFAULT
        - None → False
        - Empty → False
        - Non-string → False
        - Wrong format → False
    """
    # DENY-BY-DEFAULT: None
    if authorization_id is None:
        return False
    
    # DENY-BY-DEFAULT: Non-string
    if not isinstance(authorization_id, str):
        return False
    
    # DENY-BY-DEFAULT: Empty or whitespace
    if not authorization_id.strip():
        return False
    
    # Validate format: AUTH-{8+ hex chars}
    if not _AUTH_ID_PATTERN.match(authorization_id):
        return False
    
    return True


def validate_authorization_hash(auth: Optional[ExecutionAuthorization]) -> bool:
    """Validate authorization hash matches computed hash.
    
    Args:
        auth: ExecutionAuthorization to validate
        
    Returns:
        True if hash is valid, False otherwise
        
    Rules:
        - DENY-BY-DEFAULT
        - None → False
        - Empty hash → False
        - Tampered hash → False
    """
    # DENY-BY-DEFAULT: None
    if auth is None:
        return False
    
    # DENY-BY-DEFAULT: Empty hash
    if not auth.authorization_hash:
        return False
    
    # Compute expected hash
    expected_hash = _compute_authorization_hash(
        auth.authorization_id,
        auth.intent_id,
        auth.decision_id,
        auth.session_id,
        auth.authorization_status.name,
        auth.authorized_by,
        auth.authorized_at
    )
    
    # Compare hashes
    return auth.authorization_hash == expected_hash


def _compute_authorization_hash(
    authorization_id: str,
    intent_id: str,
    decision_id: str,
    session_id: str,
    status_name: str,
    authorized_by: str,
    authorized_at: str
) -> str:
    """Compute SHA-256 hash for authorization validation.
    
    This is a PURE internal function.
    
    Args:
        authorization_id: Authorization ID
        intent_id: Intent ID
        decision_id: Decision ID
        session_id: Session ID
        status_name: Status enum name
        authorized_by: Human identifier
        authorized_at: Timestamp
        
    Returns:
        Hex-encoded SHA-256 hash
    """
    hasher = hashlib.sha256()
    hasher.update(authorization_id.encode('utf-8'))
    hasher.update(b'\x00')
    hasher.update(intent_id.encode('utf-8'))
    hasher.update(b'\x00')
    hasher.update(decision_id.encode('utf-8'))
    hasher.update(b'\x00')
    hasher.update(session_id.encode('utf-8'))
    hasher.update(b'\x00')
    hasher.update(status_name.encode('utf-8'))
    hasher.update(b'\x00')
    hasher.update(authorized_by.encode('utf-8'))
    hasher.update(b'\x00')
    hasher.update(authorized_at.encode('utf-8'))
    return hasher.hexdigest()


def validate_authorization_status(status: Optional[AuthorizationStatus]) -> bool:
    """Validate authorization status is a valid enum member.
    
    Args:
        status: Status to validate
        
    Returns:
        True if valid AuthorizationStatus, False otherwise
        
    Rules:
        - DENY-BY-DEFAULT
        - None → False
        - Non-enum → False
    """
    # DENY-BY-DEFAULT: None
    if status is None:
        return False
    
    # DENY-BY-DEFAULT: Not an AuthorizationStatus
    if not isinstance(status, AuthorizationStatus):
        return False
    
    return True


def is_authorization_revoked(
    authorization_id: Optional[str],
    audit: Optional[AuthorizationAudit]
) -> bool:
    """Check if authorization has been revoked.
    
    Args:
        authorization_id: Authorization ID to check
        audit: Audit trail to search
        
    Returns:
        True if revoked, False otherwise
        
    Rules:
        - DENY-BY-DEFAULT for invalid inputs
        - Searches for REVOCATION record type
    """
    # DENY-BY-DEFAULT: None inputs
    if authorization_id is None or audit is None:
        return False
    
    # DENY-BY-DEFAULT: Empty authorization_id
    if not authorization_id:
        return False
    
    # Search for revocation record
    for record in audit.records:
        if (record.authorization_id == authorization_id and 
            record.record_type == "REVOCATION"):
            return True
    
    return False


def validate_audit_chain(audit: Optional[AuthorizationAudit]) -> bool:
    """Validate authorization audit chain integrity.
    
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
            record.authorization_id,
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
    authorization_id: str,
    timestamp: str,
    prior_hash: str
) -> str:
    """Compute SHA-256 hash for audit record validation.
    
    This is a PURE internal function.
    
    Args:
        record_id: Record ID
        record_type: Record type
        authorization_id: Authorization ID
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
    hasher.update(authorization_id.encode('utf-8'))
    hasher.update(b'\x00')
    hasher.update(timestamp.encode('utf-8'))
    hasher.update(b'\x00')
    hasher.update(prior_hash.encode('utf-8'))
    return hasher.hexdigest()


def get_authorization_decision(
    auth: Optional[ExecutionAuthorization]
) -> AuthorizationDecision:
    """Get ALLOW/DENY decision from authorization.
    
    Args:
        auth: Authorization to check
        
    Returns:
        AuthorizationDecision.ALLOW or AuthorizationDecision.DENY
        
    Rules:
        - DENY-BY-DEFAULT
        - None → DENY
        - AUTHORIZED status → ALLOW
        - All other statuses → DENY
    """
    # DENY-BY-DEFAULT: None
    if auth is None:
        return AuthorizationDecision.DENY
    
    # Only AUTHORIZED status permits ALLOW
    if auth.authorization_status in ALLOW_STATUSES:
        return AuthorizationDecision.ALLOW
    
    # All other statuses → DENY
    return AuthorizationDecision.DENY
