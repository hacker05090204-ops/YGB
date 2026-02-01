"""
impl_v1 Phase-25 Execution Envelope Integrity Types.

NON-AUTHORITATIVE MIRROR of governance Phase-25.
Contains CLOSED enums only.

THIS MODULE HAS NO EXECUTION AUTHORITY.
THIS MODULE NEVER AUTHORIZES EXECUTION.

CLOSED ENUMS:
- EnvelopeIntegrityStatus: 3 members (VALID, INVALID, TAMPERED)
- IntegrityViolation: 4 members

ANY STRUCTURAL ANOMALY → INVALID.
ANY HASH MISMATCH → TAMPERED.
DEFAULT = INVALID.
"""
from enum import Enum, auto


class EnvelopeIntegrityStatus(Enum):
    """Status of envelope integrity.
    
    CLOSED ENUM - Exactly 3 members. No additions permitted.
    
    States:
    - VALID: Envelope integrity verified
    - INVALID: Envelope structure invalid
    - TAMPERED: Envelope has been tampered with
    """
    VALID = auto()
    INVALID = auto()
    TAMPERED = auto()


class IntegrityViolation(Enum):
    """Types of integrity violations.
    
    CLOSED ENUM - Exactly 4 members. No additions permitted.
    
    Violations:
    - HASH_MISMATCH: Payload hash does not match
    - MISSING_FIELDS: Required fields are missing
    - ORDER_VIOLATION: Field order violated
    - UNKNOWN_VERSION: Unknown envelope version
    """
    HASH_MISMATCH = auto()
    MISSING_FIELDS = auto()
    ORDER_VIOLATION = auto()
    UNKNOWN_VERSION = auto()
