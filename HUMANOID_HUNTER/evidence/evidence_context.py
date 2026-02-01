"""
Phase-23 Evidence Context.

This module defines frozen dataclasses for evidence verification.

All dataclasses are frozen=True for immutability.
"""
from dataclasses import dataclass
from typing import FrozenSet, Tuple

from .evidence_types import EvidenceFormat, EvidenceIntegrityStatus, VerificationDecision


@dataclass(frozen=True)
class EvidenceEnvelope:
    """Evidence envelope. Frozen.
    
    Attributes:
        evidence_id: Unique evidence ID
        execution_id: Associated execution ID
        evidence_format: Format of evidence
        content_hash: SHA-256 hash of content
        timestamp: ISO timestamp
        schema_version: Schema version
        required_fields: Required fields tuple
    """
    evidence_id: str
    execution_id: str
    evidence_format: EvidenceFormat
    content_hash: str
    timestamp: str
    schema_version: str
    required_fields: Tuple[str, ...]


@dataclass(frozen=True)
class EvidenceVerificationContext:
    """Evidence verification context. Frozen.
    
    Attributes:
        envelope: Evidence envelope to verify
        expected_execution_id: Expected execution ID
        expected_format: Expected format
        expected_hash: Expected content hash
        known_hashes: Known hashes for replay detection
        timestamp: Verification timestamp
    """
    envelope: EvidenceEnvelope
    expected_execution_id: str
    expected_format: EvidenceFormat
    expected_hash: str
    known_hashes: FrozenSet[str]
    timestamp: str


@dataclass(frozen=True)
class EvidenceVerificationResult:
    """Evidence verification result. Frozen.
    
    Attributes:
        decision: ACCEPT, REJECT, QUARANTINE
        integrity_status: VALID, INVALID, TAMPERED, REPLAY
        reason_code: Machine-readable code
        reason_description: Human-readable description
    """
    decision: VerificationDecision
    integrity_status: EvidenceIntegrityStatus
    reason_code: str
    reason_description: str
