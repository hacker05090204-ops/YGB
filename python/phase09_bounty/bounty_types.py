"""
Bounty Types - Phase-09 Bug Bounty Policy.

Defines closed enums for bounty eligibility logic:
- BountyDecision: Final eligibility decision
- ScopeResult: Asset scope determination
- AssetType: Type of asset being reported

All enums are CLOSED - no dynamic members allowed.
"""

from enum import Enum


class BountyDecision(Enum):
    """Final bounty eligibility decision.
    
    CLOSED enum - exactly 4 values.
    """
    ELIGIBLE = "eligible"
    NOT_ELIGIBLE = "not_eligible"
    DUPLICATE = "duplicate"
    NEEDS_REVIEW = "needs_review"


class ScopeResult(Enum):
    """Result of scope check.
    
    CLOSED enum - exactly 2 values.
    """
    IN_SCOPE = "in_scope"
    OUT_OF_SCOPE = "out_of_scope"


class AssetType(Enum):
    """Type of asset being reported.
    
    CLOSED enum - exactly 6 values.
    """
    WEB_APP = "web_app"
    API = "api"
    MOBILE = "mobile"
    INFRASTRUCTURE = "infrastructure"
    OUT_OF_PROGRAM = "out_of_program"
    UNKNOWN = "unknown"
