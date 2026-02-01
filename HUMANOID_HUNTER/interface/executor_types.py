"""
Phase-20 Executor Types.

This module defines enums for executor interface.

CLOSED ENUMS - No new members may be added.
"""
from enum import Enum, auto


class ExecutorCommandType(Enum):
    """Executor command types.
    
    CLOSED ENUM - No new members may be added.
    """
    NAVIGATE = auto()
    CLICK = auto()
    READ = auto()
    SCROLL = auto()
    SCREENSHOT = auto()
    EXTRACT = auto()
    SHUTDOWN = auto()


class ExecutorResponseType(Enum):
    """Executor response types.
    
    CLOSED ENUM - No new members may be added.
    """
    SUCCESS = auto()
    FAILURE = auto()
    TIMEOUT = auto()
    ERROR = auto()
    REFUSED = auto()


class ExecutorStatus(Enum):
    """Executor status.
    
    CLOSED ENUM - No new members may be added.
    """
    READY = auto()
    BUSY = auto()
    OFFLINE = auto()
    ERROR = auto()
