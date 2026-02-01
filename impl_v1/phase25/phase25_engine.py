"""
impl_v1 Phase-25 Execution Envelope Integrity Engine.

NON-AUTHORITATIVE MIRROR of governance Phase-25.
Contains PURE VALIDATION FUNCTIONS ONLY.

THIS MODULE HAS NO EXECUTION AUTHORITY.
THIS MODULE NEVER AUTHORIZES EXECUTION.

VALIDATION FUNCTIONS ONLY:
- validate_envelope_id
- validate_envelope_structure
- validate_envelope_hash
- evaluate_envelope_integrity
- is_envelope_valid

INVARIANTS:
- Any structural anomaly → INVALID
- Any hash mismatch → TAMPERED
- Default = INVALID

DENY-BY-DEFAULT:
- None → INVALID
- Invalid → INVALID
"""
import re
from typing import Optional, Tuple

from .phase25_types import EnvelopeIntegrityStatus, IntegrityViolation
from .phase25_context import (
    ExecutionEnvelope,
    EnvelopeIntegrityResult,
)


# Regex patterns for valid IDs
_ENVELOPE_ID_PATTERN = re.compile(r'^ENVELOPE-[a-fA-F0-9]{8,}$')
_INSTRUCTION_ID_PATTERN = re.compile(r'^INSTRUCTION-[a-fA-F0-9]{8,}$')
_INTENT_ID_PATTERN = re.compile(r'^INTENT-[a-fA-F0-9]{8,}$')
_AUTHORIZATION_ID_PATTERN = re.compile(r'^AUTHORIZATION-[a-fA-F0-9]{8,}$')

# Valid envelope versions
_VALID_VERSIONS = frozenset({"1.0", "1.1", "2.0"})


def validate_envelope_id(envelope_id: Optional[str]) -> bool:
    """Validate an envelope ID format.
    
    Args:
        envelope_id: Envelope ID to validate
        
    Returns:
        True if valid, False otherwise
        
    Rules:
        - DENY-BY-DEFAULT
        - None → False
        - Empty → False
        - Invalid format → False
    """
    if envelope_id is None:
        return False
    if not isinstance(envelope_id, str):
        return False
    if not envelope_id.strip():
        return False
    return bool(_ENVELOPE_ID_PATTERN.match(envelope_id))


def validate_envelope_structure(
    envelope: Optional[ExecutionEnvelope]
) -> Tuple[bool, Tuple[IntegrityViolation, ...]]:
    """Validate envelope structure.
    
    Args:
        envelope: ExecutionEnvelope to validate
        
    Returns:
        Tuple of (is_valid, violations)
        
    Rules:
        - DENY-BY-DEFAULT
        - None → False with MISSING_FIELDS
        - Invalid IDs → False with MISSING_FIELDS
        - Unknown version → False with UNKNOWN_VERSION
    """
    violations: list[IntegrityViolation] = []
    
    if envelope is None:
        return False, (IntegrityViolation.MISSING_FIELDS,)
    
    # Validate envelope_id
    if not validate_envelope_id(envelope.envelope_id):
        violations.append(IntegrityViolation.MISSING_FIELDS)
    
    # Validate instruction_id
    if not envelope.instruction_id or not isinstance(envelope.instruction_id, str):
        violations.append(IntegrityViolation.MISSING_FIELDS)
    elif not _INSTRUCTION_ID_PATTERN.match(envelope.instruction_id):
        violations.append(IntegrityViolation.MISSING_FIELDS)
    
    # Validate intent_id
    if not envelope.intent_id or not isinstance(envelope.intent_id, str):
        if IntegrityViolation.MISSING_FIELDS not in violations:
            violations.append(IntegrityViolation.MISSING_FIELDS)
    elif not _INTENT_ID_PATTERN.match(envelope.intent_id):
        if IntegrityViolation.MISSING_FIELDS not in violations:
            violations.append(IntegrityViolation.MISSING_FIELDS)
    
    # Validate authorization_id
    if not envelope.authorization_id or not isinstance(envelope.authorization_id, str):
        if IntegrityViolation.MISSING_FIELDS not in violations:
            violations.append(IntegrityViolation.MISSING_FIELDS)
    elif not _AUTHORIZATION_ID_PATTERN.match(envelope.authorization_id):
        if IntegrityViolation.MISSING_FIELDS not in violations:
            violations.append(IntegrityViolation.MISSING_FIELDS)
    
    # Validate version
    if not envelope.version or not isinstance(envelope.version, str):
        violations.append(IntegrityViolation.UNKNOWN_VERSION)
    elif envelope.version not in _VALID_VERSIONS:
        violations.append(IntegrityViolation.UNKNOWN_VERSION)
    
    # Validate payload_hash
    if not envelope.payload_hash or not isinstance(envelope.payload_hash, str):
        if IntegrityViolation.MISSING_FIELDS not in violations:
            violations.append(IntegrityViolation.MISSING_FIELDS)
    elif not envelope.payload_hash.strip():
        if IntegrityViolation.MISSING_FIELDS not in violations:
            violations.append(IntegrityViolation.MISSING_FIELDS)
    
    # Validate created_at
    if not envelope.created_at or not isinstance(envelope.created_at, str):
        if IntegrityViolation.MISSING_FIELDS not in violations:
            violations.append(IntegrityViolation.MISSING_FIELDS)
    elif not envelope.created_at.strip():
        if IntegrityViolation.MISSING_FIELDS not in violations:
            violations.append(IntegrityViolation.MISSING_FIELDS)
    
    return len(violations) == 0, tuple(violations)


def validate_envelope_hash(
    envelope: Optional[ExecutionEnvelope],
    expected_hash: Optional[str]
) -> bool:
    """Validate envelope payload hash.
    
    Args:
        envelope: ExecutionEnvelope to validate
        expected_hash: Expected hash value
        
    Returns:
        True if hash matches, False otherwise
        
    Rules:
        - DENY-BY-DEFAULT
        - None envelope → False
        - None expected_hash → False
        - Mismatch → False
    """
    if envelope is None:
        return False
    if expected_hash is None:
        return False
    if not isinstance(expected_hash, str):
        return False
    if not expected_hash.strip():
        return False
    if not envelope.payload_hash:
        return False
    return envelope.payload_hash == expected_hash


def evaluate_envelope_integrity(
    envelope: Optional[ExecutionEnvelope],
    expected_hash: Optional[str] = None,
    timestamp: str = ""
) -> EnvelopeIntegrityResult:
    """Evaluate envelope integrity.
    
    Args:
        envelope: ExecutionEnvelope to evaluate
        expected_hash: Expected hash for comparison (optional)
        timestamp: Timestamp of evaluation
        
    Returns:
        EnvelopeIntegrityResult with evaluation outcome
        
    Rules:
        - DENY-BY-DEFAULT → INVALID
        - None envelope → INVALID
        - Structure violations → INVALID
        - Hash mismatch → TAMPERED
        - All valid → VALID
    """
    if envelope is None:
        return EnvelopeIntegrityResult(
            status=EnvelopeIntegrityStatus.INVALID,
            violations=(IntegrityViolation.MISSING_FIELDS,),
            evaluated_at=timestamp
        )
    
    # Validate structure
    is_valid_structure, violations = validate_envelope_structure(envelope)
    
    if not is_valid_structure:
        return EnvelopeIntegrityResult(
            status=EnvelopeIntegrityStatus.INVALID,
            violations=violations,
            evaluated_at=timestamp
        )
    
    # Check hash if expected_hash provided
    if expected_hash is not None:
        if not validate_envelope_hash(envelope, expected_hash):
            return EnvelopeIntegrityResult(
                status=EnvelopeIntegrityStatus.TAMPERED,
                violations=(IntegrityViolation.HASH_MISMATCH,),
                evaluated_at=timestamp
            )
    
    # All checks passed
    return EnvelopeIntegrityResult(
        status=EnvelopeIntegrityStatus.VALID,
        violations=(),
        evaluated_at=timestamp
    )


def is_envelope_valid(result: Optional[EnvelopeIntegrityResult]) -> bool:
    """Check if envelope is valid.
    
    Args:
        result: EnvelopeIntegrityResult to check
        
    Returns:
        True only if VALID, False otherwise
        
    Rules:
        - DENY-BY-DEFAULT
        - None → False
        - INVALID → False
        - TAMPERED → False
        - VALID → True
    """
    if result is None:
        return False
    if not isinstance(result.status, EnvelopeIntegrityStatus):
        return False
    return result.status == EnvelopeIntegrityStatus.VALID
