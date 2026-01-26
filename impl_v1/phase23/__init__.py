"""
impl_v1 Phase-23 Evidence Integrity Mirror.

NON-AUTHORITATIVE MIRROR of governance Phase-23.
THIS MODULE NEVER RECORDS EVIDENCE.
THIS MODULE NEVER COMPUTES REAL HASHES.
"""
from .phase23_types import (
    EvidenceFormat,
    EvidenceIntegrityStatus,
    VerificationDecision,
)
from .phase23_context import (
    EvidenceEnvelope,
    EvidenceVerificationContext,
    EvidenceVerificationResult,
)
from .phase23_engine import (
    validate_evidence_id,
    validate_evidence_format,
    validate_payload_hash,
    detect_replay,
    verify_evidence_integrity,
    get_verification_decision,
)

__all__ = [
    "EvidenceFormat",
    "EvidenceIntegrityStatus",
    "VerificationDecision",
    "EvidenceEnvelope",
    "EvidenceVerificationContext",
    "EvidenceVerificationResult",
    "validate_evidence_id",
    "validate_evidence_format",
    "validate_payload_hash",
    "detect_replay",
    "verify_evidence_integrity",
    "get_verification_decision",
]
