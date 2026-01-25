"""
Phase-19 Capability Types.

This module defines enums for browser capability governance.

CLOSED ENUMS - No new members may be added.
"""
from enum import Enum, auto


class BrowserActionType(Enum):
    """Browser action types.
    
    CLOSED ENUM - No new members may be added.
    """
    NAVIGATE = auto()
    CLICK = auto()
    READ = auto()
    SCROLL = auto()
    EXTRACT_TEXT = auto()
    SCREENSHOT = auto()
    FILL_INPUT = auto()
    SUBMIT_FORM = auto()
    FILE_UPLOAD = auto()
    SCRIPT_EXECUTE = auto()


class ActionRiskLevel(Enum):
    """Action risk levels.
    
    CLOSED ENUM - No new members may be added.
    """
    LOW = auto()
    MEDIUM = auto()
    HIGH = auto()
    FORBIDDEN = auto()


class CapabilityDecision(Enum):
    """Capability decision.
    
    CLOSED ENUM - No new members may be added.
    """
    ALLOWED = auto()
    DENIED = auto()
    HUMAN_REQUIRED = auto()


# Default risk classification
DEFAULT_RISK_CLASSIFICATION = {
    BrowserActionType.NAVIGATE: ActionRiskLevel.MEDIUM,
    BrowserActionType.CLICK: ActionRiskLevel.LOW,
    BrowserActionType.READ: ActionRiskLevel.LOW,
    BrowserActionType.SCROLL: ActionRiskLevel.LOW,
    BrowserActionType.EXTRACT_TEXT: ActionRiskLevel.LOW,
    BrowserActionType.SCREENSHOT: ActionRiskLevel.LOW,
    BrowserActionType.FILL_INPUT: ActionRiskLevel.MEDIUM,
    BrowserActionType.SUBMIT_FORM: ActionRiskLevel.HIGH,
    BrowserActionType.FILE_UPLOAD: ActionRiskLevel.FORBIDDEN,
    BrowserActionType.SCRIPT_EXECUTE: ActionRiskLevel.FORBIDDEN,
}

# Forbidden actions (always denied)
FORBIDDEN_ACTIONS = frozenset({
    BrowserActionType.FILE_UPLOAD,
    BrowserActionType.SCRIPT_EXECUTE,
})

# Valid execution states for capability checks
VALID_EXECUTION_STATES = frozenset({
    "REQUESTED",
    "ALLOWED",
    "ATTEMPTED",
    "FAILED",
})

# Terminal states (no more actions allowed)
TERMINAL_STATES = frozenset({
    "COMPLETED",
    "ESCALATED",
})
