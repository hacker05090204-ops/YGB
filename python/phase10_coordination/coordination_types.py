"""
Phase-10 Coordination Types.

Defines closed enums for work claim status and actions.
"""
from enum import Enum, auto


class WorkClaimStatus(Enum):
    """Status of a work claim on a target.

    CLOSED ENUM - No new members may be added.

    Members:
        UNCLAIMED: No active claim on this target
        CLAIMED: Active claim by a researcher
        RELEASED: Claim voluntarily released
        EXPIRED: Claim expired due to timeout
        COMPLETED: Work completed, finding submitted
        DENIED: Claim request denied
    """

    UNCLAIMED = auto()
    CLAIMED = auto()
    RELEASED = auto()
    EXPIRED = auto()
    COMPLETED = auto()
    DENIED = auto()


class ClaimAction(Enum):
    """Actions that can be performed on claims.

    CLOSED ENUM - No new members may be added.

    Members:
        CLAIM: Request to claim a target
        RELEASE: Request to release a claim
        COMPLETE: Mark work as complete
        CHECK: Check current claim status
    """

    CLAIM = auto()
    RELEASE = auto()
    COMPLETE = auto()
    CHECK = auto()
