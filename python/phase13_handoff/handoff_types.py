"""
Phase-13 Handoff Types.

This module defines enums for readiness state, human presence,
bug severity, and target type.

CLOSED ENUMS - No new members may be added.
"""
from enum import Enum, auto


class ReadinessState(Enum):
    """State of bug readiness for browser handoff.
    
    CLOSED ENUM - No new members may be added.
    
    Members:
        NOT_READY: Cannot proceed to browser
        REVIEW_REQUIRED: Needs human review first
        READY_FOR_BROWSER: Safe to proceed
    """
    NOT_READY = auto()
    REVIEW_REQUIRED = auto()
    READY_FOR_BROWSER = auto()


class HumanPresence(Enum):
    """Human presence requirement level.
    
    CLOSED ENUM - No new members may be added.
    
    Members:
        REQUIRED: Human MUST be present and approve
        OPTIONAL: Human may observe but not required
        BLOCKING: Human absence blocks all progress
    """
    REQUIRED = auto()
    OPTIONAL = auto()
    BLOCKING = auto()


class BugSeverity(Enum):
    """Severity level of the bug.
    
    CLOSED ENUM - No new members may be added.
    """
    CRITICAL = auto()
    HIGH = auto()
    MEDIUM = auto()
    LOW = auto()


class TargetType(Enum):
    """Type of target environment.
    
    CLOSED ENUM - No new members may be added.
    """
    PRODUCTION = auto()
    STAGING = auto()
    DEVELOPMENT = auto()
    SANDBOX = auto()
