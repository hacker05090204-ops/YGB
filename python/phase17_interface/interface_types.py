"""
Phase-17 Interface Types.

This module defines enums for interface contract.

CLOSED ENUMS - No new members may be added.
"""
from enum import Enum, auto


class ActionType(Enum):
    """Allowed action types.
    
    CLOSED ENUM - No new members may be added.
    """
    NAVIGATE = "NAVIGATE"
    CLICK = "CLICK"
    FILL = "FILL"
    SCREENSHOT = "SCREENSHOT"
    EXTRACT = "EXTRACT"


class ResponseStatus(Enum):
    """Response status values.
    
    CLOSED ENUM - No new members may be added.
    """
    SUCCESS = auto()
    FAILURE = auto()
    TIMEOUT = auto()


class ContractStatus(Enum):
    """Contract validation status.
    
    CLOSED ENUM - No new members may be added.
    """
    VALID = auto()
    DENIED = auto()


# Valid action types (string values)
VALID_ACTION_TYPES = frozenset({
    "NAVIGATE",
    "CLICK",
    "FILL",
    "SCREENSHOT",
    "EXTRACT"
})

# Valid response statuses (string values)
VALID_RESPONSE_STATUSES = frozenset({
    "SUCCESS",
    "FAILURE",
    "TIMEOUT"
})

# Required request fields
REQUIRED_REQUEST_FIELDS = frozenset({
    "request_id",
    "bug_id",
    "target_id",
    "action_type",
    "timestamp",
    "execution_permission"
})

# Optional request fields
OPTIONAL_REQUEST_FIELDS = frozenset({
    "parameters",
    "timeout_seconds",
    "session_id"
})

# Forbidden request fields
FORBIDDEN_REQUEST_FIELDS = frozenset({
    "trust_level",
    "confidence",
    "severity",
    "override",
    "bypass"
})

# Required response fields
REQUIRED_RESPONSE_FIELDS = frozenset({
    "request_id",
    "status",
    "timestamp"
})

# Optional response fields
OPTIONAL_RESPONSE_FIELDS = frozenset({
    "evidence_hash",
    "error_code",
    "error_message",
    "execution_time_ms"
})

# Forbidden response fields (executor cannot claim trust/approval)
FORBIDDEN_RESPONSE_FIELDS = frozenset({
    "approved",
    "validated",
    "trusted"
})
