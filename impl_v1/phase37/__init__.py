# Phase-37 Package Init
"""
Phase-37: Native Capability Governor
GOVERNANCE LAYER ONLY - No execution logic

Exports:
- Types (enums, dataclasses)
- Validator functions
- Decision engine
"""

from .capability_types import (
    # Enums
    RequestDecision,
    ScopeType,
    DenialReason,
    ConflictType,
    AuditEventType,
    SandboxCapability,
    CapabilityState,
    # Dataclasses
    RequestScope,
    CapabilityRequest,
    CapabilityResponse,
    CapabilityGrant,
    RateLimitState,
    AuditEntry,
    ConflictDetectionResult,
    ValidationResult,
)

from .capability_validator import (
    get_capability_state,
    validate_capability_request,
    validate_request_id,
    validate_timestamp,
    validate_scope,
    validate_context_hash,
    validate_intent_description,
    NEVER_CAPABILITIES,
    ESCALATE_CAPABILITIES,
    ALLOW_CAPABILITIES,
    reset_replay_detection,
    reset_rate_limits,
)

from .capability_engine import (
    detect_conflict,
    make_capability_decision,
    create_grant,
    create_audit_entry,
)

__all__ = [
    # Enums
    "RequestDecision",
    "ScopeType",
    "DenialReason",
    "ConflictType",
    "AuditEventType",
    "SandboxCapability",
    "CapabilityState",
    # Dataclasses
    "RequestScope",
    "CapabilityRequest",
    "CapabilityResponse",
    "CapabilityGrant",
    "RateLimitState",
    "AuditEntry",
    "ConflictDetectionResult",
    "ValidationResult",
    # Validator
    "get_capability_state",
    "validate_capability_request",
    "validate_request_id",
    "validate_timestamp",
    "validate_scope",
    "validate_context_hash",
    "validate_intent_description",
    "NEVER_CAPABILITIES",
    "ESCALATE_CAPABILITIES",
    "ALLOW_CAPABILITIES",
    "reset_replay_detection",
    "reset_rate_limits",
    # Engine
    "detect_conflict",
    "make_capability_decision",
    "create_grant",
    "create_audit_entry",
]
