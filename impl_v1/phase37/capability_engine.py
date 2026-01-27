# Phase-37: Native Capability Governor - Decision Engine
# GOVERNANCE LAYER ONLY - No execution logic
# Implements capability governance decision making

"""
Phase-37 Capability Governance Engine

Implements the decision engine for capability requests:
- Conflict detection
- Decision making (GRANTED/DENIED/PENDING)
- Grant issuance
- Audit logging

ALL UNKNOWN → DENY
ALL CONFLICTS → DENY BOTH
ALL NEVER → IMMEDIATE DENY
"""

import uuid
from datetime import datetime, timedelta
from typing import Optional, List, Dict

from .capability_types import (
    CapabilityRequest,
    CapabilityResponse,
    CapabilityGrant,
    RequestDecision,
    DenialReason,
    ConflictType,
    ConflictDetectionResult,
    ValidationResult,
    SandboxCapability,
    CapabilityState,
    ScopeType,
    AuditEntry,
    AuditEventType,
)

from .capability_validator import (
    validate_capability_request,
    get_capability_state,
    scope_requires_escalate,
)


# =============================================================================
# CONFLICT DETECTION MATRIX (FROM DESIGN)
# =============================================================================

# Capabilities that NEVER coexist with anything
EXCLUSIVE_CAPABILITIES: frozenset = frozenset([
    SandboxCapability.NETWORK,
    SandboxCapability.FILESYSTEM,
    SandboxCapability.PROCESS,
])

# Capabilities that need scope checking when both present
SCOPE_CHECK_PAIRS: frozenset = frozenset([
    (SandboxCapability.MEMORY_READ, SandboxCapability.MEMORY_WRITE),
    (SandboxCapability.HEAP_ALLOCATE, SandboxCapability.HEAP_ALLOCATE),
])


def detect_conflict(
    request: CapabilityRequest,
    pending_requests: List[CapabilityRequest],
    active_grants: List[CapabilityGrant],
) -> ConflictDetectionResult:
    """
    Detect conflicts between a request and existing requests/grants.
    
    Conflict Rules (from PHASE37_DESIGN.md §5):
    - CR-01: Two requests for same capability → DENY both
    - CR-02: Mutually exclusive capabilities → DENY both
    - CR-03: Overlapping scope ranges → DENY later
    - CR-06: NETWORK + any other → DENY NETWORK
    """
    
    # Check against pending requests
    for pending in pending_requests:
        # CR-01: Same capability from same requester
        if (pending.capability == request.capability and 
            pending.requester_id == request.requester_id and
            pending.request_id != request.request_id):
            return ConflictDetectionResult(
                has_conflict=True,
                conflict_type=ConflictType.RESOURCE_CONTENTION,
                conflicting_request_id=pending.request_id,
                description=f"Duplicate capability request for {request.capability.value}"
            )
        
        # CR-06: NETWORK + any other
        if request.capability in EXCLUSIVE_CAPABILITIES:
            return ConflictDetectionResult(
                has_conflict=True,
                conflict_type=ConflictType.MUTUAL_EXCLUSION,
                conflicting_request_id=pending.request_id,
                description=f"Capability {request.capability.value} cannot coexist with others"
            )
    
    # Check against active grants
    for grant in active_grants:
        if grant.consumed:
            continue
            
        # Same capability still active
        if (grant.capability == request.capability and
            grant.context_hash == request.context_hash):
            return ConflictDetectionResult(
                has_conflict=True,
                conflict_type=ConflictType.RESOURCE_CONTENTION,
                conflicting_request_id=grant.request_id,
                description=f"Active grant exists for {request.capability.value}"
            )
        
        # Check scope overlap for memory operations
        cap_pair = (grant.capability, request.capability)
        cap_pair_rev = (request.capability, grant.capability)
        if cap_pair in SCOPE_CHECK_PAIRS or cap_pair_rev in SCOPE_CHECK_PAIRS:
            # Simplified scope overlap check
            if (grant.scope.scope_type == request.requested_scope.scope_type and
                grant.scope.scope_value == request.requested_scope.scope_value):
                return ConflictDetectionResult(
                    has_conflict=True,
                    conflict_type=ConflictType.SCOPE_OVERLAP,
                    conflicting_request_id=grant.request_id,
                    description=f"Scope overlap detected"
                )
    
    # No conflict
    return ConflictDetectionResult(
        has_conflict=False,
        conflict_type=None,
        conflicting_request_id=None,
        description="No conflict detected"
    )


# =============================================================================
# GRANT GENERATION
# =============================================================================

def generate_grant_id() -> str:
    """Generate a unique grant ID."""
    return f"GRANT-{uuid.uuid4().hex[:16].upper()}"


def generate_grant_token() -> str:
    """Generate a one-time grant token."""
    return uuid.uuid4().hex


def create_grant(
    request: CapabilityRequest,
    grant_duration_seconds: int = 300
) -> CapabilityGrant:
    """
    Create a capability grant from a request.
    
    Grants are:
    - One-time use (consumed flag)
    - Time-limited (expires_at)
    - Context-bound (context_hash)
    """
    now = datetime.utcnow()
    expires_at = now + timedelta(seconds=grant_duration_seconds)
    
    return CapabilityGrant(
        grant_id=generate_grant_id(),
        request_id=request.request_id,
        capability=request.capability,
        scope=request.requested_scope,
        granted_at=now.isoformat() + "Z",
        expires_at=expires_at.isoformat() + "Z",
        context_hash=request.context_hash,
        consumed=False,
    )


# =============================================================================
# DECISION ENGINE
# =============================================================================

def make_capability_decision(
    request: CapabilityRequest,
    pending_requests: Optional[List[CapabilityRequest]] = None,
    active_grants: Optional[List[CapabilityGrant]] = None,
    expected_context_hash: Optional[str] = None,
    human_approved: Optional[bool] = None,
) -> CapabilityResponse:
    """
    Make a governance decision on a capability request.
    
    Decision Flow:
    1. Validate request
    2. Check capability state (NEVER → DENY)
    3. Detect conflicts (conflict → DENY)
    4. Check if ESCALATE needed
    5. If human_approved provided, use it
    6. Otherwise, GRANT or PENDING
    
    Returns CapabilityResponse with decision.
    """
    pending_requests = pending_requests or []
    active_grants = active_grants or []
    
    # Step 1: Validation
    validation = validate_capability_request(request, expected_context_hash)
    if not validation.is_valid:
        return CapabilityResponse(
            request_id=request.request_id,
            decision=RequestDecision.DENIED,
            reason_code=validation.denial_reason.value if validation.denial_reason else "UNKNOWN",
            reason_description=validation.description,
            grant_token="",
            grant_expiry="",
            requires_human=False,
        )
    
    # Step 2: Capability state (already checked in validation, but explicit)
    capability_state = get_capability_state(request.capability)
    if capability_state == CapabilityState.NEVER:
        return CapabilityResponse(
            request_id=request.request_id,
            decision=RequestDecision.DENIED,
            reason_code=DenialReason.NEVER_CAPABILITY.value,
            reason_description=f"Capability {request.capability.value} is NEVER allowed",
            grant_token="",
            grant_expiry="",
            requires_human=False,
        )
    
    # Step 3: Conflict detection
    conflict = detect_conflict(request, pending_requests, active_grants)
    if conflict.has_conflict:
        return CapabilityResponse(
            request_id=request.request_id,
            decision=RequestDecision.DENIED,
            reason_code=DenialReason.CONFLICT_DETECTED.value,
            reason_description=conflict.description,
            grant_token="",
            grant_expiry="",
            requires_human=False,
        )
    
    # Step 4: Check if ESCALATE required
    requires_escalate = (
        capability_state == CapabilityState.ESCALATE or
        scope_requires_escalate(request.requested_scope)
    )
    
    # Step 5: If human decision provided
    if human_approved is not None:
        if human_approved:
            grant = create_grant(request)
            return CapabilityResponse(
                request_id=request.request_id,
                decision=RequestDecision.GRANTED,
                reason_code="HUMAN_APPROVED",
                reason_description="Human approved the capability request",
                grant_token=generate_grant_token(),
                grant_expiry=grant.expires_at,
                requires_human=False,
            )
        else:
            return CapabilityResponse(
                request_id=request.request_id,
                decision=RequestDecision.DENIED,
                reason_code=DenialReason.HUMAN_DENIED.value,
                reason_description="Human denied the capability request",
                grant_token="",
                grant_expiry="",
                requires_human=False,
            )
    
    # Step 6: If escalation required but no human decision
    if requires_escalate:
        return CapabilityResponse(
            request_id=request.request_id,
            decision=RequestDecision.PENDING,
            reason_code="ESCALATE_REQUIRED",
            reason_description="Capability requires human approval",
            grant_token="",
            grant_expiry="",
            requires_human=True,
        )
    
    # Step 7: Grant the capability
    grant = create_grant(request)
    return CapabilityResponse(
        request_id=request.request_id,
        decision=RequestDecision.GRANTED,
        reason_code="VALIDATED",
        reason_description="Capability request validated and granted",
        grant_token=generate_grant_token(),
        grant_expiry=grant.expires_at,
        requires_human=False,
    )


# =============================================================================
# AUDIT LOGGING
# =============================================================================

def create_audit_entry(
    request: CapabilityRequest,
    event_type: AuditEventType,
    decision: RequestDecision,
    reason_code: str,
) -> AuditEntry:
    """Create an audit entry for a capability governance event."""
    return AuditEntry(
        audit_id=f"AUDIT-{uuid.uuid4().hex[:16].upper()}",
        event_type=event_type,
        timestamp=datetime.utcnow().isoformat() + "Z",
        request_id=request.request_id,
        capability=request.capability,
        decision=decision,
        reason_code=reason_code,
        requester_id=request.requester_id,
        context_hash=request.context_hash,
    )
