"""
FinalDecision enum - Phase-06 Decision Aggregation.
REIMPLEMENTED-2026

Closed enum for final decision outcomes.
No execution logic - decision types only.
"""

from enum import Enum


class FinalDecision(Enum):
    """
    Closed enum representing all valid final decisions.
    
    Decisions:
        ALLOW: Action is permitted to proceed
        DENY: Action is not permitted
        ESCALATE: Action requires human review
    """
    ALLOW = "allow"
    DENY = "deny"
    ESCALATE = "escalate"
