"""
impl_v1 Phase-27 Instruction Synthesis Context.

NON-AUTHORITATIVE MIRROR of governance Phase-27.
Contains FROZEN dataclasses only.

THIS MODULE HAS NO EXECUTION AUTHORITY.

ALL DATACLASSES ARE FROZEN (frozen=True):
- InstructionEnvelope: 7 fields
- SynthesisResult: 5 fields

IMMUTABILITY GUARANTEE:
- No mutation permitted after creation
- Attempting mutation raises FrozenInstanceError
- Instructions cannot mutate after creation
"""
from dataclasses import dataclass
from typing import Optional

from .phase27_types import EnvelopeStatus


@dataclass(frozen=True)
class InstructionEnvelope:
    """Envelope containing instruction metadata.
    
    Immutable once created.
    
    Attributes:
        envelope_id: Unique identifier for the envelope
        instruction_id: ID of the instruction
        intent_description: Human-readable description of intent
        envelope_hash: Hash of the envelope contents
        created_at: Timestamp of envelope creation (ISO-8601)
        status: Current status of the envelope
        version: Version of the envelope format
    """
    envelope_id: str
    instruction_id: str
    intent_description: str
    envelope_hash: str
    created_at: str
    status: EnvelopeStatus
    version: str


@dataclass(frozen=True)
class SynthesisResult:
    """Result of instruction synthesis validation.
    
    Immutable once created.
    
    Attributes:
        envelope_id: Link to original envelope
        status: Final status after synthesis
        is_valid: Whether the envelope is valid
        metadata_hash: Hash of synthesized metadata
        reason: Human-readable reason for result
    """
    envelope_id: str
    status: EnvelopeStatus
    is_valid: bool
    metadata_hash: str
    reason: str
