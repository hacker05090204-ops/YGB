"""
Phase-04 Action Types
REIMPLEMENTED-2026

Defines action types that can be validated.
This module contains NO execution logic.
All action types are immutable.
"""

from enum import Enum
from typing import Final, Dict


class ActionType(Enum):
    """
    Types of actions that can be validated.
    
    Action types are ordered by criticality:
    - READ: Low risk, read-only operations
    - WRITE: High risk, state modification
    - DELETE: Critical risk, data removal
    - EXECUTE: Critical risk, command execution
    - CONFIGURE: High risk, settings changes
    """
    READ = "read"
    """Read-only access - lowest risk."""
    
    WRITE = "write"
    """State modification - requires validation."""
    
    DELETE = "delete"
    """Data removal - critical, requires escalation."""
    
    EXECUTE = "execute"
    """Command execution - critical, requires escalation."""
    
    CONFIGURE = "configure"
    """Settings change - requires validation."""


# =============================================================================
# CRITICALITY MAPPING
# =============================================================================

_CRITICALITY: Final[Dict[ActionType, str]] = {
    ActionType.READ: "LOW",
    ActionType.WRITE: "HIGH",
    ActionType.DELETE: "CRITICAL",
    ActionType.EXECUTE: "CRITICAL",
    ActionType.CONFIGURE: "HIGH",
}


def get_criticality(action_type: ActionType) -> str:
    """
    Get the criticality level for an action type.
    
    Args:
        action_type: The action type to check.
        
    Returns:
        Criticality level: "LOW", "HIGH", or "CRITICAL".
    """
    return _CRITICALITY[action_type]
