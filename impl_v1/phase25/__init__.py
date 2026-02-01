"""
impl_v1 Phase-25 Execution Envelope Integrity Mirror.

NON-AUTHORITATIVE MIRROR of governance Phase-25.
Contains ONLY data structures and validation logic.

THIS MODULE HAS NO EXECUTION AUTHORITY.
THIS MODULE NEVER AUTHORIZES EXECUTION.

CLOSED ENUMS:
- EnvelopeIntegrityStatus: 3 members
- IntegrityViolation: 4 members

FROZEN DATACLASSES:
- ExecutionEnvelope: 7 fields
- EnvelopeIntegrityResult: 3 fields

ENGINE FUNCTIONS (VALIDATION ONLY):
- validate_envelope_id
- validate_envelope_structure
- validate_envelope_hash
- evaluate_envelope_integrity
- is_envelope_valid

ANY HASH MISMATCH → TAMPERED.
DEFAULT = INVALID.
"""
from .phase25_types import (
    EnvelopeIntegrityStatus,
    IntegrityViolation,
)
from .phase25_context import (
    ExecutionEnvelope,
    EnvelopeIntegrityResult,
)
from .phase25_engine import (
    validate_envelope_id,
    validate_envelope_structure,
    validate_envelope_hash,
    evaluate_envelope_integrity,
    is_envelope_valid,
)

__all__ = [
    # Types
    "EnvelopeIntegrityStatus",
    "IntegrityViolation",
    # Context
    "ExecutionEnvelope",
    "EnvelopeIntegrityResult",
    # Engine
    "validate_envelope_id",
    "validate_envelope_structure",
    "validate_envelope_hash",
    "evaluate_envelope_integrity",
    "is_envelope_valid",
]
