"""
HUMANOID_HUNTER Evidence — Native Evidence Integrity & Verification

Phase-23 implementation.

Evidence may look real.
Evidence may be fake.
Governance NEVER assumes.
"""
from .evidence_types import (
    EvidenceFormat,
    EvidenceIntegrityStatus,
    VerificationDecision,
    VALID_FORMATS
)
from .evidence_context import (
    EvidenceEnvelope,
    EvidenceVerificationContext,
    EvidenceVerificationResult
)
from .evidence_engine import (
    validate_evidence_schema,
    verify_evidence_hash,
    detect_evidence_replay,
    decide_evidence_acceptance
)

__all__ = [
    # Enums
    "EvidenceFormat",
    "EvidenceIntegrityStatus",
    "VerificationDecision",
    # Constants
    "VALID_FORMATS",
    # Dataclasses
    "EvidenceEnvelope",
    "EvidenceVerificationContext",
    "EvidenceVerificationResult",
    # Functions
    "validate_evidence_schema",
    "verify_evidence_hash",
    "detect_evidence_replay",
    "decide_evidence_acceptance",
]
