"""
impl_v1 Phase-27 Instruction Synthesis Mirror.

NON-AUTHORITATIVE MIRROR of governance Phase-27.
Contains ONLY data structures and validation logic.

THIS MODULE HAS NO EXECUTION AUTHORITY.
THIS MODULE DOES NOT EXECUTE INSTRUCTIONS.
THIS MODULE DOES NOT AUTHORIZE ANYTHING.

CLOSED ENUMS:
- EnvelopeStatus: 3 members

FROZEN DATACLASSES:
- InstructionEnvelope: 7 fields
- SynthesisResult: 5 fields

ENGINE FUNCTIONS (VALIDATION ONLY):
- validate_instruction_id
- validate_instruction_envelope
- synthesize_instruction_metadata
- get_envelope_status
- is_envelope_valid

INSTRUCTIONS DESCRIBE INTENT.
THEY NEVER AUTHORIZE.
"""
from .phase27_types import EnvelopeStatus
from .phase27_context import (
    InstructionEnvelope,
    SynthesisResult,
)
from .phase27_engine import (
    validate_instruction_id,
    validate_instruction_envelope,
    synthesize_instruction_metadata,
    get_envelope_status,
    is_envelope_valid,
)

__all__ = [
    # Types
    "EnvelopeStatus",
    # Context
    "InstructionEnvelope",
    "SynthesisResult",
    # Engine
    "validate_instruction_id",
    "validate_instruction_envelope",
    "synthesize_instruction_metadata",
    "get_envelope_status",
    "is_envelope_valid",
]
