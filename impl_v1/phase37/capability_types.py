# Phase-37: Native Capability Governor - Types Module
# GOVERNANCE LAYER ONLY - No execution logic
# All capabilities unknown or not explicitly ALLOW → DENY

"""
Phase-37 defines the governance types for native capability requests.
This module implements:
- Capability enums (CLOSED)
- Request/Response dataclasses (frozen=True)
- Validation types
- Audit types

NO EXECUTION LOGIC - PURE TYPE DEFINITIONS
"""

from dataclasses import dataclass
from enum import Enum, auto
from typing import Optional


# =============================================================================
# CLOSED ENUMS (3 members - RequestDecision)
# =============================================================================

class RequestDecision(Enum):
    """
    CLOSED ENUM - 3 members
    Decision outcome for capability requests.
    """
    GRANTED = "GRANTED"    # Request approved, grant token issued
    DENIED = "DENIED"      # Request rejected
    PENDING = "PENDING"    # Awaiting human review


# =============================================================================
# CLOSED ENUMS (6 members - ScopeType)
# =============================================================================

class ScopeType(Enum):
    """
    CLOSED ENUM - 6 members
    Scope classification for capability requests.
    """
    MEMORY_RANGE = "MEMORY_RANGE"        # Specific memory addresses
    TIME_WINDOW = "TIME_WINDOW"          # Duration limit
    OPERATION_COUNT = "OPERATION_COUNT"  # Number of operations
    BYTE_LIMIT = "BYTE_LIMIT"            # Data size limit
    SINGLE_USE = "SINGLE_USE"            # One operation only
    UNBOUNDED = "UNBOUNDED"              # No limit (requires ESCALATE)


# =============================================================================
# CLOSED ENUMS (12 members - DenialReason)
# =============================================================================

class DenialReason(Enum):
    """
    CLOSED ENUM - 12 members
    Reason codes for denied requests.
    """
    MALFORMED_REQUEST = "MALFORMED_REQUEST"
    UNKNOWN_CAPABILITY = "UNKNOWN_CAPABILITY"
    NEVER_CAPABILITY = "NEVER_CAPABILITY"
    MISSING_FIELD = "MISSING_FIELD"
    INVALID_FIELD = "INVALID_FIELD"
    RATE_LIMITED = "RATE_LIMITED"
    CONFLICT_DETECTED = "CONFLICT_DETECTED"
    CONTEXT_MISMATCH = "CONTEXT_MISMATCH"
    EXPIRED_REQUEST = "EXPIRED_REQUEST"
    HUMAN_DENIED = "HUMAN_DENIED"
    SCOPE_EXCEEDED = "SCOPE_EXCEEDED"
    REPLAY_DETECTED = "REPLAY_DETECTED"


# =============================================================================
# CLOSED ENUMS (5 members - ConflictType)
# =============================================================================

class ConflictType(Enum):
    """
    CLOSED ENUM - 5 members
    Types of conflicts between capability requests.
    """
    MUTUAL_EXCLUSION = "MUTUAL_EXCLUSION"      # Capabilities cannot coexist
    SCOPE_OVERLAP = "SCOPE_OVERLAP"            # Overlapping scope ranges
    INTENT_CONTRADICTION = "INTENT_CONTRADICTION"  # Conflicting purposes
    TEMPORAL_CONFLICT = "TEMPORAL_CONFLICT"    # Overlapping time windows
    RESOURCE_CONTENTION = "RESOURCE_CONTENTION"  # Same resource requested


# =============================================================================
# CLOSED ENUMS (8 members - AuditEventType)
# =============================================================================

class AuditEventType(Enum):
    """
    CLOSED ENUM - 8 members
    Types of audit events for capability governance.
    """
    REQUEST_RECEIVED = "REQUEST_RECEIVED"
    VALIDATION_PASSED = "VALIDATION_PASSED"
    VALIDATION_FAILED = "VALIDATION_FAILED"
    HUMAN_ESCALATED = "HUMAN_ESCALATED"
    HUMAN_APPROVED = "HUMAN_APPROVED"
    HUMAN_DENIED = "HUMAN_DENIED"
    GRANT_ISSUED = "GRANT_ISSUED"
    GRANT_CONSUMED = "GRANT_CONSUMED"


# =============================================================================
# CLOSED ENUMS (6 members - SandboxCapability from Phase-36)
# =============================================================================

class SandboxCapability(Enum):
    """
    CLOSED ENUM - 6 members
    Capability types for sandbox (from Phase-36).
    These define what a native executor can request.
    """
    MEMORY_READ = "MEMORY_READ"
    MEMORY_WRITE = "MEMORY_WRITE"
    HEAP_ALLOCATE = "HEAP_ALLOCATE"
    INPUT_READ = "INPUT_READ"
    OUTPUT_WRITE = "OUTPUT_WRITE"
    NETWORK = "NETWORK"  # NEVER capability
    FILESYSTEM = "FILESYSTEM"  # NEVER capability
    PROCESS = "PROCESS"  # NEVER capability


# =============================================================================
# CLOSED ENUMS (3 members - CapabilityState)
# =============================================================================

class CapabilityState(Enum):
    """
    CLOSED ENUM - 3 members
    The governance state for each capability.
    """
    NEVER = "NEVER"        # Immediately denied, no validation
    ESCALATE = "ESCALATE"  # Requires human approval
    ALLOW = "ALLOW"        # Can be granted with validation


# =============================================================================
# FROZEN DATACLASSES
# =============================================================================

@dataclass(frozen=True)
class RequestScope:
    """
    Frozen dataclass defining the scope of a capability request.
    """
    scope_type: ScopeType
    scope_value: str
    scope_limit: int


@dataclass(frozen=True)
class CapabilityRequest:
    """
    Frozen dataclass for a capability request from native code.
    """
    request_id: str              # Format: REQ-[a-fA-F0-9]{16}
    capability: SandboxCapability
    intent_description: str       # Human-readable (max 256 chars)
    requested_scope: RequestScope
    timestamp: str               # ISO 8601 format
    expiry: str                  # ISO 8601 format
    context_hash: str            # SHA-256 of execution context
    requester_id: str            # Native instance identifier


@dataclass(frozen=True)
class CapabilityResponse:
    """
    Frozen dataclass for the response to a capability request.
    """
    request_id: str              # Echo back request_id
    decision: RequestDecision
    reason_code: str             # Machine-readable reason
    reason_description: str      # Human-readable reason
    grant_token: str             # If GRANTED, one-time token
    grant_expiry: str            # When grant expires
    requires_human: bool         # True if ESCALATE


@dataclass(frozen=True)
class CapabilityGrant:
    """
    Frozen dataclass for an issued capability grant.
    """
    grant_id: str                # Format: GRANT-[a-fA-F0-9]{16}
    request_id: str              # Original request
    capability: SandboxCapability
    scope: RequestScope
    granted_at: str              # Timestamp
    expires_at: str              # Expiry timestamp
    context_hash: str            # Must match at use time
    consumed: bool               # One-time use flag


@dataclass(frozen=True)
class RateLimitState:
    """
    Frozen dataclass tracking rate limit state for a requester.
    """
    requester_id: str
    window_start: str
    request_count: int
    escalate_count: int
    last_denial: str
    consecutive_denials: int
    backoff_until: str


@dataclass(frozen=True)
class AuditEntry:
    """
    Frozen dataclass for audit log entries.
    """
    audit_id: str
    event_type: AuditEventType
    timestamp: str
    request_id: str
    capability: SandboxCapability
    decision: RequestDecision
    reason_code: str
    requester_id: str
    context_hash: str


@dataclass(frozen=True)
class ConflictDetectionResult:
    """
    Frozen dataclass for conflict detection outcome.
    """
    has_conflict: bool
    conflict_type: Optional[ConflictType]
    conflicting_request_id: Optional[str]
    description: str


@dataclass(frozen=True)
class ValidationResult:
    """
    Frozen dataclass for request validation outcome.
    """
    is_valid: bool
    denial_reason: Optional[DenialReason]
    description: str
