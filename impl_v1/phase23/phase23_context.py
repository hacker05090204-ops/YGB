"""
impl_v1 Phase-23 Evidence Integrity Context.

NON-AUTHORITATIVE MIRROR of governance Phase-23.
Contains FROZEN dataclasses only.

THIS MODULE HAS NO EXECUTION AUTHORITY.

ALL DATACLASSES ARE FROZEN (frozen=True):
- EvidenceEnvelope: 7 fields
- EvidenceVerificationContext: 3 fields
- EvidenceVerificationResult: 3 fields
"""
from dataclasses import dataclass
from typing import Tuple

from .phase23_types import (
    EvidenceFormat,
    EvidenceIntegrityStatus,
    VerificationDecision,
)


@dataclass(frozen=True)
class EvidenceEnvelope:
    """Envelope containing evidence metadata.
    
    Immutable once created.
    
    Attributes:
        evidence_id: Unique identifier for the evidence
        format: Format of the evidence payload
        payload_hash: Hash of the payload
        prior_hash: Hash of prior evidence in chain
        timestamp: Timestamp of evidence creation (ISO-8601)
        source: Source of the evidence
        version: Version of the evidence format
    """
    evidence_id: str
    format: EvidenceFormat
    payload_hash: str
    prior_hash: str
    timestamp: str
    source: str
    version: str


@dataclass(frozen=True)
class EvidenceVerificationContext:
    """Context for evidence verification.
    
    Immutable once created.
    
    Attributes:
        expected_format: Expected format of evidence
        expected_source: Expected source of evidence
        allow_replay: Whether replay is allowed
    """
    expected_format: EvidenceFormat
    expected_source: str
    allow_replay: bool


@dataclass(frozen=True)
class EvidenceVerificationResult:
    """Result of evidence verification.
    
    Immutable once created.
    
    Attributes:
        status: Integrity status
        decision: Verification decision
        reasons: Tuple of reason strings
    """
    status: EvidenceIntegrityStatus
    decision: VerificationDecision
    reasons: Tuple[str, ...]
