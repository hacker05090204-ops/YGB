"""
impl_v1 Phase-27 Instruction Synthesis Types.

NON-AUTHORITATIVE MIRROR of governance Phase-27.
Contains CLOSED enums only.

THIS MODULE HAS NO EXECUTION AUTHORITY.
THIS MODULE DOES NOT EXECUTE INSTRUCTIONS.
THIS MODULE DOES NOT AUTHORIZE ANYTHING.

CLOSED ENUMS:
- EnvelopeStatus: 3 members (CREATED, VALIDATED, INVALID)

INSTRUCTIONS DESCRIBE INTENT.
THEY NEVER AUTHORIZE.
"""
from enum import Enum, auto


class EnvelopeStatus(Enum):
    """Status of an instruction envelope.
    
    CLOSED ENUM - Exactly 3 members. No additions permitted.
    
    States:
    - CREATED: Envelope has been created
    - VALIDATED: Envelope has been validated
    - INVALID: Envelope is invalid
    """
    CREATED = auto()
    VALIDATED = auto()
    INVALID = auto()
