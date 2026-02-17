# Phase-37: Native Capability Governor - Validator Module
# GOVERNANCE LAYER ONLY - No execution logic
# Implements request validation per PHASE37_DESIGN.md §4

"""
Phase-37 Capability Request Validator

Implements the validation decision flow from PHASE37_DESIGN.md:
- Parse validation
- Field validation
- Capability state check
- Scope validation
- Context validation
- Rate limit check
- Replay detection

ALL UNKNOWN CAPABILITIES → DENY
ALL VALIDATION FAILURES → DENY
"""

import re
from datetime import datetime
from typing import Optional, Set

from .capability_types import (
    CapabilityRequest,
    RequestScope,
    SandboxCapability,
    CapabilityState,
    ScopeType,
    DenialReason,
    ValidationResult,
)


# =============================================================================
# CAPABILITY STATE REGISTRY (IMMUTABLE)
# =============================================================================

# NEVER capabilities - immediately denied, no validation
NEVER_CAPABILITIES: frozenset = frozenset([
    SandboxCapability.NETWORK,
    SandboxCapability.FILESYSTEM,
    SandboxCapability.PROCESS,
])

# ESCALATE capabilities - require human approval
ESCALATE_CAPABILITIES: frozenset = frozenset([
    SandboxCapability.MEMORY_WRITE,
])

# ALLOW capabilities - can be granted after validation
ALLOW_CAPABILITIES: frozenset = frozenset([
    SandboxCapability.MEMORY_READ,
    SandboxCapability.HEAP_ALLOCATE,
    SandboxCapability.INPUT_READ,
    SandboxCapability.OUTPUT_WRITE,
])


def get_capability_state(capability: SandboxCapability) -> CapabilityState:
    """
    Get the governance state for a capability.
    Unknown capabilities default to NEVER (deny-by-default).
    """
    if capability in NEVER_CAPABILITIES:
        return CapabilityState.NEVER
    if capability in ESCALATE_CAPABILITIES:
        return CapabilityState.ESCALATE
    if capability in ALLOW_CAPABILITIES:
        return CapabilityState.ALLOW
    # Unknown → DENY (treated as NEVER)
    return CapabilityState.NEVER


# =============================================================================
# REQUEST ID VALIDATION
# =============================================================================

REQUEST_ID_PATTERN = re.compile(r"^REQ-[a-fA-F0-9]{16}$")


def validate_request_id(request_id: str) -> bool:
    """Validate request_id format: REQ-[a-fA-F0-9]{16}"""
    if not request_id:
        return False
    return bool(REQUEST_ID_PATTERN.match(request_id))


# =============================================================================
# TIMESTAMP VALIDATION
# =============================================================================

def validate_timestamp(timestamp: str) -> bool:
    """Validate ISO 8601 timestamp format."""
    if not timestamp:
        return False
    try:
        datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        return True
    except (ValueError, AttributeError):
        return False


def validate_expiry_after_timestamp(timestamp: str, expiry: str) -> bool:
    """Verify expiry is after timestamp."""
    if not timestamp or not expiry:
        return False
    try:
        ts = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        exp = datetime.fromisoformat(expiry.replace("Z", "+00:00"))
        return exp > ts
    except (ValueError, AttributeError):
        return False


# =============================================================================
# SCOPE VALIDATION
# =============================================================================

def validate_scope(scope: RequestScope) -> bool:
    """
    Validate request scope.
    - scope_type must be valid ScopeType
    - scope_value must be non-empty
    - scope_limit must be positive (except UNBOUNDED)
    """
    if scope is None:
        return False
    
    if not isinstance(scope.scope_type, ScopeType):
        return False
    
    if not scope.scope_value:
        return False
    
    # UNBOUNDED requires ESCALATE, but limit check is separate
    if scope.scope_type != ScopeType.UNBOUNDED and scope.scope_limit <= 0:
        return False
    
    return True


def scope_requires_escalate(scope: RequestScope) -> bool:
    """Check if scope requires human escalation."""
    return scope.scope_type == ScopeType.UNBOUNDED


# =============================================================================
# CONTEXT HASH VALIDATION
# =============================================================================

CONTEXT_HASH_PATTERN = re.compile(r"^[a-fA-F0-9]{64}$")


def validate_context_hash(context_hash: str) -> bool:
    """Validate context hash is valid SHA-256."""
    if not context_hash:
        return False
    return bool(CONTEXT_HASH_PATTERN.match(context_hash))


# =============================================================================
# INTENT DESCRIPTION VALIDATION
# =============================================================================

MAX_INTENT_LENGTH = 256


def validate_intent_description(intent: str) -> bool:
    """Validate intent description is non-empty and within length."""
    if not intent:
        return False
    if len(intent) > MAX_INTENT_LENGTH:
        return False
    return True


# =============================================================================
# REPLAY DETECTION (IN-MEMORY)
# =============================================================================

# In-memory set for replay detection (would be persistent in production)
_seen_request_ids: Set[str] = set()


def check_replay(request_id: str) -> bool:
    """
    Check if request_id has been seen before.
    Returns True if REPLAY DETECTED (should deny).
    """
    if request_id in _seen_request_ids:
        return True  # Replay detected
    _seen_request_ids.add(request_id)
    return False  # Not a replay


def reset_replay_detection() -> None:
    """Reset replay detection (for testing)."""
    global _seen_request_ids
    _seen_request_ids = set()


# =============================================================================
# RATE LIMITING (IN-MEMORY)
# =============================================================================

# Simple rate limit tracking
_request_counts: dict = {}
MAX_REQUESTS_PER_WINDOW = 100


def check_rate_limit(requester_id: str) -> bool:
    """
    Check if requester has exceeded rate limit.
    Returns True if RATE LIMITED (should deny).
    """
    count = _request_counts.get(requester_id, 0)
    if count >= MAX_REQUESTS_PER_WINDOW:
        return True  # Rate limited
    _request_counts[requester_id] = count + 1
    return False  # Not rate limited


def reset_rate_limits() -> None:
    """Reset rate limits (for testing)."""
    global _request_counts
    _request_counts = {}


# =============================================================================
# FULL REQUEST VALIDATION
# =============================================================================

def validate_capability_request(
    request: CapabilityRequest,
    expected_context_hash: Optional[str] = None
) -> ValidationResult:
    """
    Full validation of a capability request.
    Implements the decision flow from PHASE37_DESIGN.md §4.
    
    Returns ValidationResult with:
    - is_valid: True if all checks pass
    - denial_reason: DenialReason if invalid
    - description: Human-readable explanation
    """
    
    # Step 1: Request ID format
    if not validate_request_id(request.request_id):
        return ValidationResult(
            is_valid=False,
            denial_reason=DenialReason.INVALID_FIELD,
            description="Invalid request_id format"
        )
    
    # Step 2: Capability registered check
    if not isinstance(request.capability, SandboxCapability):
        return ValidationResult(
            is_valid=False,
            denial_reason=DenialReason.UNKNOWN_CAPABILITY,
            description="Unknown capability type"
        )
    
    # Step 3: NEVER capability check
    capability_state = get_capability_state(request.capability)
    if capability_state == CapabilityState.NEVER:
        return ValidationResult(
            is_valid=False,
            denial_reason=DenialReason.NEVER_CAPABILITY,
            description=f"Capability {request.capability.value} is NEVER allowed"
        )
    
    # Step 4: Intent description
    if not validate_intent_description(request.intent_description):
        return ValidationResult(
            is_valid=False,
            denial_reason=DenialReason.MISSING_FIELD,
            description="Invalid or missing intent description"
        )
    
    # Step 5: Scope validation
    if not validate_scope(request.requested_scope):
        return ValidationResult(
            is_valid=False,
            denial_reason=DenialReason.INVALID_FIELD,
            description="Invalid request scope"
        )
    
    # Step 6: Timestamp validation
    if not validate_timestamp(request.timestamp):
        return ValidationResult(
            is_valid=False,
            denial_reason=DenialReason.INVALID_FIELD,
            description="Invalid timestamp format"
        )
    
    # Step 7: Expiry after timestamp
    if not validate_expiry_after_timestamp(request.timestamp, request.expiry):
        return ValidationResult(
            is_valid=False,
            denial_reason=DenialReason.INVALID_FIELD,
            description="Expiry must be after timestamp"
        )
    
    # Step 8: Context hash
    if not validate_context_hash(request.context_hash):
        return ValidationResult(
            is_valid=False,
            denial_reason=DenialReason.INVALID_FIELD,
            description="Invalid context hash format"
        )
    
    # Step 9: Context match (if expected hash provided)
    if expected_context_hash and request.context_hash != expected_context_hash:
        return ValidationResult(
            is_valid=False,
            denial_reason=DenialReason.CONTEXT_MISMATCH,
            description="Context hash does not match expected"
        )
    
    # Step 10: Rate limit check
    if check_rate_limit(request.requester_id):
        return ValidationResult(
            is_valid=False,
            denial_reason=DenialReason.RATE_LIMITED,
            description="Rate limit exceeded"
        )
    
    # Step 11: Replay detection
    if check_replay(request.request_id):
        return ValidationResult(
            is_valid=False,
            denial_reason=DenialReason.REPLAY_DETECTED,
            description="Request ID has been used before"
        )
    
    # All checks passed
    return ValidationResult(
        is_valid=True,
        denial_reason=None,
        description="Validation passed"
    )
