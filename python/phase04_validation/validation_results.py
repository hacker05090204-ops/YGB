"""
Phase-04 Validation Results
REIMPLEMENTED-2026

Defines validation result types.
This module contains NO execution logic.
All results are immutable.
"""

from enum import Enum


class ValidationResult(Enum):
    """
    Possible outcomes of action validation.
    
    Only three results are allowed:
    - ALLOW: Action may proceed
    - DENY: Action is not permitted
    - ESCALATE: Action requires human approval
    """
    ALLOW = "allow"
    """Action may proceed."""
    
    DENY = "deny"
    """Action is not permitted."""
    
    ESCALATE = "escalate"
    """Action requires human approval."""
