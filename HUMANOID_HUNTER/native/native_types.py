"""
Phase-22 Native Types.

This module defines enums for native runtime isolation.

CLOSED ENUMS - No new members may be added.
"""
from enum import Enum, auto


class NativeProcessState(Enum):
    """Native process states.
    
    CLOSED ENUM - No new members may be added.
    """
    PENDING = auto()
    RUNNING = auto()
    EXITED = auto()
    CRASHED = auto()
    TIMED_OUT = auto()
    KILLED = auto()


class NativeExitReason(Enum):
    """Native exit reasons.
    
    CLOSED ENUM - No new members may be added.
    """
    NORMAL = auto()
    ERROR = auto()
    CRASH = auto()
    TIMEOUT = auto()
    KILLED = auto()
    UNKNOWN = auto()


class IsolationDecision(Enum):
    """Isolation decisions.
    
    CLOSED ENUM - No new members may be added.
    """
    ACCEPT = auto()
    REJECT = auto()
    QUARANTINE = auto()


# Terminal states (execution completed)
TERMINAL_STATES = frozenset({
    NativeProcessState.EXITED,
    NativeProcessState.CRASHED,
    NativeProcessState.TIMED_OUT,
    NativeProcessState.KILLED,
})

# Invalid states (should not report results)
INVALID_STATES = frozenset({
    NativeProcessState.PENDING,
    NativeProcessState.RUNNING,
})
