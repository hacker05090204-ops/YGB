"""
impl_v1 Phase-23 Evidence Integrity Types.

NON-AUTHORITATIVE MIRROR of governance Phase-23.
Contains CLOSED enums only.

THIS MODULE HAS NO EXECUTION AUTHORITY.
THIS MODULE NEVER RECORDS EVIDENCE.
THIS MODULE NEVER COMPUTES REAL HASHES.

CLOSED ENUMS:
- EvidenceFormat: 3 members (JSON, BINARY, TEXT)
- EvidenceIntegrityStatus: 4 members (VALID, INVALID, TAMPERED, REPLAYED)
- VerificationDecision: 3 members (ACCEPT, REJECT, ESCALATE)

DEFAULT = REJECT.
"""
from enum import Enum, auto


class EvidenceFormat(Enum):
    """Format of evidence payload.
    
    CLOSED ENUM - Exactly 3 members. No additions permitted.
    """
    JSON = auto()
    BINARY = auto()
    TEXT = auto()


class EvidenceIntegrityStatus(Enum):
    """Status of evidence integrity.
    
    CLOSED ENUM - Exactly 4 members. No additions permitted.
    
    States:
    - VALID: Evidence integrity verified
    - INVALID: Evidence structure invalid
    - TAMPERED: Evidence has been tampered with
    - REPLAYED: Evidence is a replay of prior evidence
    """
    VALID = auto()
    INVALID = auto()
    TAMPERED = auto()
    REPLAYED = auto()


class VerificationDecision(Enum):
    """Decision from evidence verification.
    
    CLOSED ENUM - Exactly 3 members. No additions permitted.
    
    Decisions:
    - ACCEPT: Evidence is accepted
    - REJECT: Evidence is rejected
    - ESCALATE: Evidence requires human review
    """
    ACCEPT = auto()
    REJECT = auto()
    ESCALATE = auto()
