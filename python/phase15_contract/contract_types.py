"""
Phase-15 Contract Types.

This module defines enums for contract validation.

CLOSED ENUMS - No new members may be added.
"""
from enum import Enum, auto


class RequestType(Enum):
    """Allowed request types.
    
    CLOSED ENUM - No new members may be added.
    
    Members:
        STATUS_CHECK: Check current status
        READINESS_CHECK: Check browser readiness
        FULL_EVALUATION: Full pipeline evaluation
    """
    STATUS_CHECK = "STATUS_CHECK"
    READINESS_CHECK = "READINESS_CHECK"
    FULL_EVALUATION = "FULL_EVALUATION"


class ValidationStatus(Enum):
    """Validation result status.
    
    CLOSED ENUM - No new members may be added.
    
    Members:
        VALID: Validation passed
        DENIED: Validation denied
    """
    VALID = auto()
    DENIED = auto()


# Allowed field names
REQUIRED_FIELDS = frozenset({
    "request_id",
    "bug_id",
    "target_id",
    "request_type",
    "timestamp"
})

OPTIONAL_FIELDS = frozenset({
    "session_id",
    "user_context",
    "notes"
})

ALLOWED_FIELDS = REQUIRED_FIELDS | OPTIONAL_FIELDS

# Forbidden field names (backend-only)
FORBIDDEN_FIELDS = frozenset({
    "confidence",
    "confidence_level",
    "severity",
    "bug_severity",
    "readiness",
    "readiness_state",
    "human_presence",
    "can_proceed",
    "is_blocked",
    "evidence_state",
    "trust_level",
    "authority"
})

# Valid request types
VALID_REQUEST_TYPES = frozenset({
    "STATUS_CHECK",
    "READINESS_CHECK",
    "FULL_EVALUATION"
})
