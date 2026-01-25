"""
Phase-27 Instruction Types.

This module defines enums for instruction synthesis.

CLOSED ENUMS - No new members may be added.

THIS IS A POLICY LAYER ONLY.
IT DOES NOT EXECUTE ANYTHING.
"""
from enum import Enum, auto


class InstructionType(Enum):
    """Instruction types.
    
    CLOSED ENUM - No new members may be added.
    """
    NAVIGATE = auto()
    CLICK = auto()
    TYPE = auto()
    WAIT = auto()
    SCROLL = auto()
    SCREENSHOT = auto()


class InstructionStatus(Enum):
    """Instruction envelope status.
    
    CLOSED ENUM - No new members may be added.
    """
    CREATED = auto()
    SEALED = auto()
    REJECTED = auto()
