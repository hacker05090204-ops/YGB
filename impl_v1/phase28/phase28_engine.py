"""
impl_v1 Phase-28 Handshake Engine.

NON-AUTHORITATIVE MIRROR of governance Phase-28.
Contains PURE VALIDATION FUNCTIONS ONLY.

THIS MODULE HAS NO EXECUTION AUTHORITY.
THIS MODULE DOES NOT PERFORM HANDSHAKES.
THIS MODULE DOES NOT GRANT AUTHORITY.
THIS MODULE DOES NOT REGISTER EXECUTORS.

VALIDATION FUNCTIONS ONLY:
- validate_executor_identity
- validate_envelope_hash
- validate_handshake_context
- decide_handshake
- is_handshake_valid

INVARIANTS:
- Handshake proves eligibility, never authority
- Hash mismatch → REJECT
- Unknown identity → REJECT
- Default = REJECT

DENY-BY-DEFAULT:
- None → REJECT
- Empty → REJECT
- Invalid → REJECT
"""
import re
from typing import Optional

from .phase28_types import (
    ExecutorIdentityStatus,
    HandshakeDecision,
)
from .phase28_context import (
    HandshakeContext,
    HandshakeResult,
)


# Regex pattern for valid handshake ID: HANDSHAKE-{8+ hex chars}
_HANDSHAKE_ID_PATTERN = re.compile(r'^HANDSHAKE-[a-fA-F0-9]{8,}$')

# Regex pattern for valid executor ID: EXECUTOR-{alphanumeric}
_EXECUTOR_ID_PATTERN = re.compile(r'^EXECUTOR-[a-zA-Z0-9_-]+$')


def validate_executor_identity(
    identity_status: Optional[ExecutorIdentityStatus]
) -> bool:
    """Validate an executor's identity status.
    
    Args:
        identity_status: ExecutorIdentityStatus to validate
        
    Returns:
        True if identity is acceptable for handshake, False otherwise
        
    Rules:
        - DENY-BY-DEFAULT
        - None → False
        - Non-ExecutorIdentityStatus → False
        - UNKNOWN → False
        - REVOKED → False
        - UNVERIFIED → False
        - VERIFIED → True
    """
    # DENY-BY-DEFAULT: None
    if identity_status is None:
        return False
    
    # DENY-BY-DEFAULT: Non-ExecutorIdentityStatus
    if not isinstance(identity_status, ExecutorIdentityStatus):
        return False
    
    # Only VERIFIED is acceptable
    return identity_status == ExecutorIdentityStatus.VERIFIED


def validate_envelope_hash(
    envelope_hash: Optional[str],
    expected_hash: Optional[str]
) -> bool:
    """Validate envelope hash matches expected hash.
    
    Args:
        envelope_hash: Hash from the envelope
        expected_hash: Expected hash value
        
    Returns:
        True if hashes match, False otherwise
        
    Rules:
        - DENY-BY-DEFAULT
        - None envelope_hash → False
        - None expected_hash → False
        - Empty envelope_hash → False
        - Empty expected_hash → False
        - Mismatch → False
        - Match → True
    """
    # DENY-BY-DEFAULT: None
    if envelope_hash is None or expected_hash is None:
        return False
    
    # DENY-BY-DEFAULT: Non-string
    if not isinstance(envelope_hash, str) or not isinstance(expected_hash, str):
        return False
    
    # DENY-BY-DEFAULT: Empty
    if not envelope_hash.strip() or not expected_hash.strip():
        return False
    
    # Compare hashes
    return envelope_hash == expected_hash


def validate_handshake_context(
    context: Optional[HandshakeContext]
) -> bool:
    """Validate a handshake context.
    
    Args:
        context: HandshakeContext to validate
        
    Returns:
        True if valid, False otherwise
        
    Rules:
        - DENY-BY-DEFAULT
        - None → False
        - Missing required fields → False
        - Invalid handshake_id format → False
        - Invalid executor_id format → False
        - Invalid identity_status → False
        - Empty envelope_hash → False
        - Empty expected_hash → False
        - Empty timestamp → False
    """
    # DENY-BY-DEFAULT: None
    if context is None:
        return False
    
    # Validate handshake_id format
    if not context.handshake_id or not isinstance(context.handshake_id, str):
        return False
    if not _HANDSHAKE_ID_PATTERN.match(context.handshake_id):
        return False
    
    # Validate executor_id format
    if not context.executor_id or not isinstance(context.executor_id, str):
        return False
    if not _EXECUTOR_ID_PATTERN.match(context.executor_id):
        return False
    
    # Validate identity_status is ExecutorIdentityStatus
    if not isinstance(context.identity_status, ExecutorIdentityStatus):
        return False
    
    # Validate envelope_hash
    if not context.envelope_hash or not isinstance(context.envelope_hash, str):
        return False
    if not context.envelope_hash.strip():
        return False
    
    # Validate expected_hash
    if not context.expected_hash or not isinstance(context.expected_hash, str):
        return False
    if not context.expected_hash.strip():
        return False
    
    # Validate timestamp
    if not context.timestamp or not isinstance(context.timestamp, str):
        return False
    if not context.timestamp.strip():
        return False
    
    return True


def decide_handshake(
    context: Optional[HandshakeContext]
) -> HandshakeResult:
    """Decide handshake outcome based on context.
    
    Args:
        context: HandshakeContext to evaluate
        
    Returns:
        HandshakeResult with decision
        
    Rules:
        - DENY-BY-DEFAULT → REJECT
        - None context → REJECT
        - Invalid context → REJECT
        - UNKNOWN identity → REJECT
        - REVOKED identity → REJECT
        - UNVERIFIED identity → REJECT
        - Hash mismatch → REJECT
        - VERIFIED + hash match → ACCEPT
    """
    # DENY-BY-DEFAULT: None context
    if context is None:
        return HandshakeResult(
            handshake_id="",
            decision=HandshakeDecision.REJECT,
            identity_status=ExecutorIdentityStatus.UNKNOWN,
            hash_matched=False,
            reason="Context is None - defaulting to REJECT"
        )
    
    # DENY-BY-DEFAULT: Invalid context
    if not validate_handshake_context(context):
        return HandshakeResult(
            handshake_id=context.handshake_id if context.handshake_id else "",
            decision=HandshakeDecision.REJECT,
            identity_status=context.identity_status if isinstance(context.identity_status, ExecutorIdentityStatus) else ExecutorIdentityStatus.UNKNOWN,
            hash_matched=False,
            reason="Context is invalid - defaulting to REJECT"
        )
    
    # Check identity status first
    identity_valid = validate_executor_identity(context.identity_status)
    
    if not identity_valid:
        return HandshakeResult(
            handshake_id=context.handshake_id,
            decision=HandshakeDecision.REJECT,
            identity_status=context.identity_status,
            hash_matched=False,
            reason=f"Identity status {context.identity_status.name} is not acceptable"
        )
    
    # Check hash match
    hash_matched = validate_envelope_hash(context.envelope_hash, context.expected_hash)
    
    if not hash_matched:
        return HandshakeResult(
            handshake_id=context.handshake_id,
            decision=HandshakeDecision.REJECT,
            identity_status=context.identity_status,
            hash_matched=False,
            reason="Envelope hash does not match expected hash"
        )
    
    # All checks passed → ACCEPT
    return HandshakeResult(
        handshake_id=context.handshake_id,
        decision=HandshakeDecision.ACCEPT,
        identity_status=context.identity_status,
        hash_matched=True,
        reason="Handshake accepted: identity verified and hash matched"
    )


def is_handshake_valid(result: Optional[HandshakeResult]) -> bool:
    """Check if a handshake result indicates a valid handshake.
    
    Args:
        result: HandshakeResult to check
        
    Returns:
        True if handshake was accepted, False otherwise
        
    Rules:
        - DENY-BY-DEFAULT
        - None → False
        - Invalid result → False
        - REJECT decision → False
        - ACCEPT decision → True
    """
    # DENY-BY-DEFAULT: None
    if result is None:
        return False
    
    # DENY-BY-DEFAULT: Invalid decision type
    if not isinstance(result.decision, HandshakeDecision):
        return False
    
    return result.decision == HandshakeDecision.ACCEPT
