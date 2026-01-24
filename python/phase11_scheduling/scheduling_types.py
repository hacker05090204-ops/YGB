"""
Phase-11 Scheduling Types.

Defines closed enums for work scheduling and delegation.
"""
from enum import Enum, auto


class WorkSlotStatus(Enum):
    """Status of a work assignment slot.

    CLOSED ENUM - No new members may be added.

    Members:
        AVAILABLE: Slot is available for assignment
        ASSIGNED: Slot is assigned to worker
        QUEUED: Assignment queued for later
        COMPLETED: Work completed
        EXPIRED: Assignment expired
        DENIED: Assignment denied
    """

    AVAILABLE = auto()
    ASSIGNED = auto()
    QUEUED = auto()
    COMPLETED = auto()
    EXPIRED = auto()
    DENIED = auto()


class DelegationDecision(Enum):
    """Result of a delegation request.

    CLOSED ENUM - No new members may be added.

    Members:
        ALLOWED: Delegation allowed
        DENIED_NO_CONSENT: Denied, no explicit consent
        DENIED_NOT_OWNER: Denied, delegator is not owner
        DENIED_SYSTEM_DELEGATION: Denied, system cannot delegate
        DENIED_INVALID_TARGET: Denied, invalid target
    """

    ALLOWED = auto()
    DENIED_NO_CONSENT = auto()
    DENIED_NOT_OWNER = auto()
    DENIED_SYSTEM_DELEGATION = auto()
    DENIED_INVALID_TARGET = auto()


class WorkerLoadLevel(Enum):
    """Classification of worker current load.

    CLOSED ENUM - No new members may be added.

    Members:
        LIGHT: 0-2 assignments (based on policy threshold)
        MEDIUM: 3-5 assignments
        HEAVY: 6+ assignments
    """

    LIGHT = auto()
    MEDIUM = auto()
    HEAVY = auto()
