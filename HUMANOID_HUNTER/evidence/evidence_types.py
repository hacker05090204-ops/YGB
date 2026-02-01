"""
Phase-23 Evidence Types.

This module defines enums for evidence verification.

CLOSED ENUMS - No new members may be added.
"""
from enum import Enum, auto


class EvidenceFormat(Enum):
    """Evidence formats.
    
    CLOSED ENUM - No new members may be added.
    """
    JSON = auto()
    BINARY = auto()
    SCREENSHOT = auto()


class EvidenceIntegrityStatus(Enum):
    """Evidence integrity status.
    
    CLOSED ENUM - No new members may be added.
    """
    VALID = auto()
    INVALID = auto()
    TAMPERED = auto()
    REPLAY = auto()


class VerificationDecision(Enum):
    """Verification decisions.
    
    CLOSED ENUM - No new members may be added.
    """
    ACCEPT = auto()
    REJECT = auto()
    QUARANTINE = auto()


# Known valid formats
VALID_FORMATS = frozenset({
    EvidenceFormat.JSON,
    EvidenceFormat.BINARY,
    EvidenceFormat.SCREENSHOT,
})
