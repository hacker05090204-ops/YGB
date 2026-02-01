"""
impl_v1 Phase-25 Execution Envelope Integrity Context.

NON-AUTHORITATIVE MIRROR of governance Phase-25.
Contains FROZEN dataclasses only.

THIS MODULE HAS NO EXECUTION AUTHORITY.

ALL DATACLASSES ARE FROZEN (frozen=True):
- ExecutionEnvelope: 7 fields
- EnvelopeIntegrityResult: 3 fields

IMMUTABILITY GUARANTEE:
- No mutation permitted after creation
- Attempting mutation raises FrozenInstanceError
"""
from dataclasses import dataclass
from typing import Tuple

from .phase25_types import EnvelopeIntegrityStatus, IntegrityViolation


@dataclass(frozen=True)
class ExecutionEnvelope:
    """Envelope containing execution metadata.
    
    Immutable once created.
    
    Attributes:
        envelope_id: Unique identifier for the envelope
        instruction_id: ID of the instruction
        intent_id: ID of the intent
        authorization_id: ID of the authorization
        version: Envelope version
        payload_hash: Hash of the payload
        created_at: Timestamp of creation (ISO-8601)
    """
    envelope_id: str
    instruction_id: str
    intent_id: str
    authorization_id: str
    version: str
    payload_hash: str
    created_at: str


@dataclass(frozen=True)
class EnvelopeIntegrityResult:
    """Result of envelope integrity evaluation.
    
    Immutable once created.
    
    Attributes:
        status: Final integrity status
        violations: Tuple of violations (empty if VALID)
        evaluated_at: Timestamp of evaluation (ISO-8601)
    """
    status: EnvelopeIntegrityStatus
    violations: Tuple[IntegrityViolation, ...]
    evaluated_at: str
