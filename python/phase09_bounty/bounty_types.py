"""
Phase-09 Bounty Types.

Defines the core enums for bounty eligibility decisions.

CLOSED ENUMS - No new members may be added.
"""
from enum import Enum, auto


class ScopeResult(Enum):
    """Classification of target scope status.

    CLOSED ENUM - No new members may be added.

    Members:
        IN_SCOPE: Target is within bounty program scope
        OUT_OF_SCOPE: Target is NOT within scope
    """

    IN_SCOPE = auto()
    OUT_OF_SCOPE = auto()


class BountyDecision(Enum):
    """Final eligibility decision for a bounty submission.

    CLOSED ENUM - No new members may be added.

    Members:
        ELIGIBLE: Report qualifies for bounty
        NOT_ELIGIBLE: Report does NOT qualify
        DUPLICATE: Report duplicates existing
        NEEDS_REVIEW: Requires human decision
    """

    ELIGIBLE = auto()
    NOT_ELIGIBLE = auto()
    DUPLICATE = auto()
    NEEDS_REVIEW = auto()
