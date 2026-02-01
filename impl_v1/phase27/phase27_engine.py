"""
impl_v1 Phase-27 Instruction Synthesis Engine.

NON-AUTHORITATIVE MIRROR of governance Phase-27.
Contains PURE VALIDATION FUNCTIONS ONLY.

THIS MODULE HAS NO EXECUTION AUTHORITY.
THIS MODULE DOES NOT EXECUTE INSTRUCTIONS.
THIS MODULE DOES NOT AUTHORIZE ANYTHING.
THIS MODULE DOES NOT CREATE REAL HASHES.

VALIDATION FUNCTIONS ONLY:
- validate_instruction_id
- validate_instruction_envelope
- synthesize_instruction_metadata
- get_envelope_status
- is_envelope_valid

INVARIANTS:
- Instructions DESCRIBE intent, never authorize
- Instructions cannot mutate after creation
- Invalid or ambiguous → INVALID
- Default = INVALID

DENY-BY-DEFAULT:
- None → INVALID
- Empty → INVALID
- Invalid → INVALID
"""
import re
from typing import Optional

from .phase27_types import EnvelopeStatus
from .phase27_context import (
    InstructionEnvelope,
    SynthesisResult,
)


# Regex pattern for valid envelope ID: ENVELOPE-{8+ hex chars}
_ENVELOPE_ID_PATTERN = re.compile(r'^ENVELOPE-[a-fA-F0-9]{8,}$')

# Regex pattern for valid instruction ID: INSTRUCTION-{8+ hex chars}
_INSTRUCTION_ID_PATTERN = re.compile(r'^INSTRUCTION-[a-fA-F0-9]{8,}$')


def validate_instruction_id(instruction_id: Optional[str]) -> bool:
    """Validate an instruction ID format.
    
    Args:
        instruction_id: Instruction ID to validate
        
    Returns:
        True if valid, False otherwise
        
    Rules:
        - DENY-BY-DEFAULT
        - None → False
        - Non-string → False
        - Empty → False
        - Invalid format → False
        - Valid format → True
    """
    # DENY-BY-DEFAULT: None
    if instruction_id is None:
        return False
    
    # DENY-BY-DEFAULT: Non-string
    if not isinstance(instruction_id, str):
        return False
    
    # DENY-BY-DEFAULT: Empty
    if not instruction_id.strip():
        return False
    
    # Validate format
    return bool(_INSTRUCTION_ID_PATTERN.match(instruction_id))


def validate_instruction_envelope(
    envelope: Optional[InstructionEnvelope]
) -> bool:
    """Validate an instruction envelope.
    
    Args:
        envelope: InstructionEnvelope to validate
        
    Returns:
        True if valid, False otherwise
        
    Rules:
        - DENY-BY-DEFAULT
        - None → False
        - Missing required fields → False
        - Invalid envelope_id format → False
        - Invalid instruction_id format → False
        - Empty intent_description → False
        - Empty envelope_hash → False
        - Empty created_at → False
        - Invalid status → False
        - Empty version → False
    """
    # DENY-BY-DEFAULT: None
    if envelope is None:
        return False
    
    # Validate envelope_id format
    if not envelope.envelope_id or not isinstance(envelope.envelope_id, str):
        return False
    if not _ENVELOPE_ID_PATTERN.match(envelope.envelope_id):
        return False
    
    # Validate instruction_id format
    if not validate_instruction_id(envelope.instruction_id):
        return False
    
    # Validate intent_description
    if not envelope.intent_description or not isinstance(envelope.intent_description, str):
        return False
    if not envelope.intent_description.strip():
        return False
    
    # Validate envelope_hash
    if not envelope.envelope_hash or not isinstance(envelope.envelope_hash, str):
        return False
    if not envelope.envelope_hash.strip():
        return False
    
    # Validate created_at
    if not envelope.created_at or not isinstance(envelope.created_at, str):
        return False
    if not envelope.created_at.strip():
        return False
    
    # Validate status is EnvelopeStatus
    if not isinstance(envelope.status, EnvelopeStatus):
        return False
    
    # Validate version
    if not envelope.version or not isinstance(envelope.version, str):
        return False
    if not envelope.version.strip():
        return False
    
    return True


def synthesize_instruction_metadata(
    envelope: Optional[InstructionEnvelope]
) -> SynthesisResult:
    """Synthesize metadata for an instruction envelope.
    
    Args:
        envelope: InstructionEnvelope to synthesize
        
    Returns:
        SynthesisResult with synthesis outcome
        
    Rules:
        - DENY-BY-DEFAULT → INVALID
        - None envelope → INVALID
        - Invalid envelope → INVALID
        - INVALID status → INVALID
        - Valid envelope → VALIDATED
    """
    # DENY-BY-DEFAULT: None envelope
    if envelope is None:
        return SynthesisResult(
            envelope_id="",
            status=EnvelopeStatus.INVALID,
            is_valid=False,
            metadata_hash="",
            reason="Envelope is None - defaulting to INVALID"
        )
    
    # DENY-BY-DEFAULT: Invalid envelope
    if not validate_instruction_envelope(envelope):
        return SynthesisResult(
            envelope_id=envelope.envelope_id if envelope.envelope_id else "",
            status=EnvelopeStatus.INVALID,
            is_valid=False,
            metadata_hash="",
            reason="Envelope is invalid - defaulting to INVALID"
        )
    
    # Check if envelope status is already INVALID
    if envelope.status == EnvelopeStatus.INVALID:
        return SynthesisResult(
            envelope_id=envelope.envelope_id,
            status=EnvelopeStatus.INVALID,
            is_valid=False,
            metadata_hash="",
            reason="Envelope status is INVALID"
        )
    
    # Valid envelope → VALIDATED
    # Note: We just copy the envelope_hash as metadata_hash
    # This module does NOT compute real hashes
    return SynthesisResult(
        envelope_id=envelope.envelope_id,
        status=EnvelopeStatus.VALIDATED,
        is_valid=True,
        metadata_hash=envelope.envelope_hash,
        reason="Envelope synthesized successfully"
    )


def get_envelope_status(
    envelope: Optional[InstructionEnvelope]
) -> EnvelopeStatus:
    """Get the status of an instruction envelope.
    
    Args:
        envelope: InstructionEnvelope to check
        
    Returns:
        EnvelopeStatus of the envelope
        
    Rules:
        - DENY-BY-DEFAULT → INVALID
        - None → INVALID
        - Invalid envelope → INVALID
        - Valid envelope → envelope's status
    """
    # DENY-BY-DEFAULT: None
    if envelope is None:
        return EnvelopeStatus.INVALID
    
    # DENY-BY-DEFAULT: Invalid envelope
    if not validate_instruction_envelope(envelope):
        return EnvelopeStatus.INVALID
    
    return envelope.status


def is_envelope_valid(result: Optional[SynthesisResult]) -> bool:
    """Check if a synthesis result indicates a valid envelope.
    
    Args:
        result: SynthesisResult to check
        
    Returns:
        True if envelope is valid, False otherwise
        
    Rules:
        - DENY-BY-DEFAULT
        - None → False
        - Invalid status type → False
        - INVALID status → False
        - is_valid False → False
        - VALIDATED + is_valid True → True
    """
    # DENY-BY-DEFAULT: None
    if result is None:
        return False
    
    # DENY-BY-DEFAULT: Invalid status type
    if not isinstance(result.status, EnvelopeStatus):
        return False
    
    # DENY-BY-DEFAULT: INVALID status
    if result.status == EnvelopeStatus.INVALID:
        return False
    
    # Check is_valid flag
    if not isinstance(result.is_valid, bool):
        return False
    
    return result.is_valid
