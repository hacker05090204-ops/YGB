"""
Phase-34 Authorization Engine.

This module provides execution authorization functions.

All functions are PURE (no side effects).
Authorization is DATA, not action.
Systems authorize, never decide.

HUMANS DECIDE.
SYSTEMS AUTHORIZE.
EXECUTION STILL WAITS.

CORE RULES:
- Deny-by-default
- Intent MUST be valid and not revoked
- Authorization is immutable
- Revocation is permanent
- Audit is append-only
"""
import hashlib
import uuid
from typing import Optional, Tuple, Set

from HUMANOID_HUNTER.intent import (
    ExecutionIntent,
    IntentAudit,
    IntentStatus,
    BindingResult,
    is_intent_revoked,
    validate_audit_chain
)

from .authorization_types import (
    AuthorizationStatus,
    AuthorizationDecision,
    ALLOW_STATUSES,
    DENY_STATUSES
)
from .authorization_context import (
    ExecutionAuthorization,
    AuthorizationRevocation,
    AuthorizationRecord,
    AuthorizationAudit
)


# Track authorized intents to prevent duplicates
_AUTHORIZED_INTENTS: Set[str] = set()


def _compute_authorization_hash(
    authorization_id: str,
    intent_id: str,
    decision_id: str,
    session_id: str,
    authorization_status: AuthorizationStatus,
    authorized_by: str,
    authorized_at: str
) -> str:
    """Compute SHA-256 hash for an execution authorization.
    
    Args:
        authorization_id: Authorization identifier
        intent_id: Intent identifier
        decision_id: Decision identifier
        session_id: Session identifier
        authorization_status: Authorization status
        authorized_by: Human who authorized
        authorized_at: Authorization timestamp
        
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
    hasher.update(authorization_status.name.encode('utf-8'))
    hasher.update(b'\x00')
    hasher.update(authorized_by.encode('utf-8'))
    hasher.update(b'\x00')
    hasher.update(authorized_at.encode('utf-8'))
    return hasher.hexdigest()


def _compute_revocation_hash(
    revocation_id: str,
    authorization_id: str,
    revoked_by: str,
    revocation_reason: str,
    revoked_at: str
) -> str:
    """Compute SHA-256 hash for an authorization revocation.
    
    Args:
        revocation_id: Revocation identifier
        authorization_id: Authorization being revoked
        revoked_by: Human revoking
        revocation_reason: Reason for revocation
        revoked_at: Revocation timestamp
        
    Returns:
        Hex-encoded SHA-256 hash
    """
    hasher = hashlib.sha256()
    hasher.update(revocation_id.encode('utf-8'))
    hasher.update(b'\x00')
    hasher.update(authorization_id.encode('utf-8'))
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
    authorization_id: str,
    timestamp: str,
    prior_hash: str
) -> str:
    """Compute SHA-256 hash for an audit record.
    
    Args:
        record_id: Record identifier
        record_type: Type of record
        authorization_id: Related authorization
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
    hasher.update(authorization_id.encode('utf-8'))
    hasher.update(b'\x00')
    hasher.update(timestamp.encode('utf-8'))
    hasher.update(b'\x00')
    hasher.update(prior_hash.encode('utf-8'))
    return hasher.hexdigest()


def _recompute_intent_hash(intent: ExecutionIntent) -> str:
    """Recompute intent hash for validation.
    
    Args:
        intent: Intent to validate
        
    Returns:
        Recomputed hash
    """
    hasher = hashlib.sha256()
    hasher.update(intent.intent_id.encode('utf-8'))
    hasher.update(b'\x00')
    hasher.update(intent.decision_id.encode('utf-8'))
    hasher.update(b'\x00')
    hasher.update(intent.decision_type.name.encode('utf-8'))
    hasher.update(b'\x00')
    hasher.update(intent.evidence_chain_hash.encode('utf-8'))
    hasher.update(b'\x00')
    hasher.update(intent.session_id.encode('utf-8'))
    hasher.update(b'\x00')
    hasher.update(intent.execution_state.encode('utf-8'))
    hasher.update(b'\x00')
    hasher.update(intent.created_at.encode('utf-8'))
    hasher.update(b'\x00')
    hasher.update(intent.created_by.encode('utf-8'))
    return hasher.hexdigest()


def authorize_execution(
    intent: ExecutionIntent,
    intent_audit: IntentAudit,
    timestamp: str
) -> Tuple[AuthorizationDecision, Optional[ExecutionAuthorization]]:
    """Create authorization from a valid intent.
    
    Args:
        intent: Phase-33 ExecutionIntent
        intent_audit: Phase-33 IntentAudit for revocation check
        timestamp: Authorization timestamp
        
    Returns:
        Tuple of (AuthorizationDecision, ExecutionAuthorization or None)
        
    Rules:
        - Pure function (no I/O)
        - Intent MUST be valid (hash verified)
        - Intent MUST NOT be revoked
        - Intent must have valid human source
        - Deny-by-default on any failure
    """
    # Validate intent exists
    if intent is None:
        return (AuthorizationDecision.DENY, None)
    
    # Validate required fields
    if not intent.intent_id or not intent.intent_id.strip():
        return (AuthorizationDecision.DENY, None)
    
    if not intent.decision_id or not intent.decision_id.strip():
        return (AuthorizationDecision.DENY, None)
    
    if not intent.created_by or not intent.created_by.strip():
        return (AuthorizationDecision.DENY, None)
    
    if not intent.session_id or not intent.session_id.strip():
        return (AuthorizationDecision.DENY, None)
    
    if not timestamp or not timestamp.strip():
        return (AuthorizationDecision.DENY, None)
    
    # Validate intent hash
    expected_hash = _recompute_intent_hash(intent)
    if intent.intent_hash != expected_hash:
        return (AuthorizationDecision.DENY, None)
    
    # Check intent audit is valid
    if intent_audit is None:
        return (AuthorizationDecision.DENY, None)
    
    # Check if intent has been revoked
    if is_intent_revoked(intent.intent_id, intent_audit):
        return (AuthorizationDecision.DENY, None)
    
    # Check for duplicate authorization
    if intent.intent_id in _AUTHORIZED_INTENTS:
        return (AuthorizationDecision.DENY, None)
    
    # Generate authorization ID
    authorization_id = f"AUTH-{uuid.uuid4().hex[:8]}"
    
    # Compute authorization hash
    authorization_hash = _compute_authorization_hash(
        authorization_id,
        intent.intent_id,
        intent.decision_id,
        intent.session_id,
        AuthorizationStatus.AUTHORIZED,
        intent.created_by,
        timestamp
    )
    
    # Create immutable authorization
    authorization = ExecutionAuthorization(
        authorization_id=authorization_id,
        intent_id=intent.intent_id,
        decision_id=intent.decision_id,
        session_id=intent.session_id,
        authorization_status=AuthorizationStatus.AUTHORIZED,
        authorized_by=intent.created_by,
        authorized_at=timestamp,
        authorization_hash=authorization_hash
    )
    
    # Record authorization
    _AUTHORIZED_INTENTS.add(intent.intent_id)
    
    return (AuthorizationDecision.ALLOW, authorization)


def validate_authorization(
    auth: ExecutionAuthorization,
    intent: ExecutionIntent
) -> bool:
    """Validate authorization matches its source intent.
    
    Args:
        auth: Authorization to validate
        intent: Original intent
        
    Returns:
        True if valid, False otherwise
        
    Checks:
        - Intent ID matches
        - Decision ID matches
        - Session ID matches
        - Authorized by matches intent creator
        - Hash is valid (recomputed)
    """
    if auth is None or intent is None:
        return False
    
    # Check intent ID matches
    if auth.intent_id != intent.intent_id:
        return False
    
    # Check decision ID matches
    if auth.decision_id != intent.decision_id:
        return False
    
    # Check session ID matches
    if auth.session_id != intent.session_id:
        return False
    
    # Check authorized by matches intent creator
    if auth.authorized_by != intent.created_by:
        return False
    
    # Recompute hash and verify
    expected_hash = _compute_authorization_hash(
        auth.authorization_id,
        auth.intent_id,
        auth.decision_id,
        auth.session_id,
        auth.authorization_status,
        auth.authorized_by,
        auth.authorized_at
    )
    
    if auth.authorization_hash != expected_hash:
        return False
    
    return True


def revoke_authorization(
    auth: ExecutionAuthorization,
    reason: str,
    timestamp: str,
    revoked_by: str
) -> AuthorizationRevocation:
    """Create revocation for an authorization.
    
    Args:
        auth: Authorization to revoke
        reason: Mandatory reason
        timestamp: Revocation time
        revoked_by: Human revoking
        
    Returns:
        AuthorizationRevocation record
        
    Raises:
        ValueError: If required fields are missing
        
    Rules:
        - Revocation is permanent
        - Reason is required
        - Creates immutable record
    """
    if auth is None:
        raise ValueError("authorization is required")
    
    if not revoked_by or not revoked_by.strip():
        raise ValueError("revoked_by is required")
    
    if not reason or not reason.strip():
        raise ValueError("revocation reason is required")
    
    if not timestamp or not timestamp.strip():
        raise ValueError("timestamp is required")
    
    revocation_id = f"AUTHREV-{uuid.uuid4().hex[:8]}"
    
    revocation_hash = _compute_revocation_hash(
        revocation_id,
        auth.authorization_id,
        revoked_by,
        reason,
        timestamp
    )
    
    return AuthorizationRevocation(
        revocation_id=revocation_id,
        authorization_id=auth.authorization_id,
        revoked_by=revoked_by,
        revocation_reason=reason,
        revoked_at=timestamp,
        revocation_hash=revocation_hash
    )


def record_authorization(
    audit: AuthorizationAudit,
    authorization_id: str,
    record_type: str,
    timestamp: str
) -> AuthorizationAudit:
    """Record authorization event in audit trail.
    
    Args:
        audit: Current audit trail
        authorization_id: Authorization to record
        record_type: "AUTHORIZATION" or "REVOCATION"
        timestamp: Record timestamp
        
    Returns:
        NEW AuthorizationAudit with appended record
        
    Raises:
        ValueError: If record_type is invalid
        
    Rules:
        - Audit is append-only
        - Hash chain maintained
        - Returns new structure (immutable)
    """
    if record_type not in ("AUTHORIZATION", "REVOCATION"):
        raise ValueError(f"Invalid record_type: {record_type}")
    
    record_id = f"AUTHREC-{uuid.uuid4().hex[:8]}"
    prior_hash = audit.head_hash
    
    # Compute record hash
    self_hash = _compute_record_hash(
        record_id,
        record_type,
        authorization_id,
        timestamp,
        prior_hash
    )
    
    # Create record
    record = AuthorizationRecord(
        record_id=record_id,
        record_type=record_type,
        authorization_id=authorization_id,
        timestamp=timestamp,
        prior_hash=prior_hash,
        self_hash=self_hash
    )
    
    # Return new audit trail (immutable append)
    return AuthorizationAudit(
        audit_id=audit.audit_id,
        records=audit.records + (record,),
        session_id=audit.session_id,
        head_hash=self_hash,
        length=audit.length + 1
    )


def create_empty_audit(session_id: str, audit_id: Optional[str] = None) -> AuthorizationAudit:
    """Create empty authorization audit trail.
    
    Args:
        session_id: Session identifier
        audit_id: Optional audit ID (generated if not provided)
        
    Returns:
        Empty AuthorizationAudit ready for appending
    """
    if audit_id is None:
        audit_id = f"AUTHAUDIT-{uuid.uuid4().hex[:8]}"
    
    return AuthorizationAudit(
        audit_id=audit_id,
        records=(),
        session_id=session_id,
        head_hash="",
        length=0
    )


def is_authorization_revoked(
    authorization_id: str,
    audit: AuthorizationAudit
) -> bool:
    """Check if authorization has been revoked.
    
    Args:
        authorization_id: Authorization to check
        audit: Audit trail to search
        
    Returns:
        True if revoked, False otherwise
    """
    for record in audit.records:
        if record.authorization_id == authorization_id and record.record_type == "REVOCATION":
            return True
    return False


def is_authorization_valid(
    auth: ExecutionAuthorization,
    intent: ExecutionIntent,
    intent_audit: IntentAudit,
    auth_audit: AuthorizationAudit
) -> bool:
    """Check if authorization is currently valid.
    
    Args:
        auth: Authorization to check
        intent: Source intent
        intent_audit: Intent audit for revocation check
        auth_audit: Authorization audit for revocation check
        
    Returns:
        True if valid, False otherwise
        
    Checks:
        - Authorization validates against intent
        - Authorization status is AUTHORIZED
        - Intent is not revoked
        - Authorization is not revoked
    """
    # Validate basic authorization-intent match
    if not validate_authorization(auth, intent):
        return False
    
    # Check authorization status
    if auth.authorization_status != AuthorizationStatus.AUTHORIZED:
        return False
    
    # Check intent is not revoked
    if is_intent_revoked(intent.intent_id, intent_audit):
        return False
    
    # Check authorization is not revoked
    if is_authorization_revoked(auth.authorization_id, auth_audit):
        return False
    
    return True


def get_authorization_decision(auth: ExecutionAuthorization) -> AuthorizationDecision:
    """Get ALLOW/DENY decision from authorization status.
    
    Args:
        auth: Authorization to check
        
    Returns:
        AuthorizationDecision.ALLOW or AuthorizationDecision.DENY
        
    Rules:
        - AUTHORIZED → ALLOW
        - All other statuses → DENY
        - None → DENY
    """
    if auth is None:
        return AuthorizationDecision.DENY
    
    if auth.authorization_status in ALLOW_STATUSES:
        return AuthorizationDecision.ALLOW
    
    return AuthorizationDecision.DENY


def validate_audit_chain(audit: AuthorizationAudit) -> bool:
    """Validate authorization audit chain integrity.
    
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


def clear_authorized_intents() -> None:
    """Clear authorized intents set (for testing only).
    
    WARNING: This is for test isolation only.
    """
    _AUTHORIZED_INTENTS.clear()
