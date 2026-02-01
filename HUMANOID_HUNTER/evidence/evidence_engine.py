"""
Phase-23 Evidence Engine.

This module provides evidence verification functions.

All functions are pure (no side effects).
All decisions are deny-by-default.

EVIDENCE MAY LOOK REAL.
EVIDENCE MAY BE FAKE.
GOVERNANCE NEVER ASSUMES.
"""
from .evidence_types import (
    EvidenceFormat,
    EvidenceIntegrityStatus,
    VerificationDecision,
)
from .evidence_context import (
    EvidenceEnvelope,
    EvidenceVerificationContext,
    EvidenceVerificationResult
)


def validate_evidence_schema(envelope: EvidenceEnvelope) -> bool:
    """Validate evidence schema.
    
    Args:
        envelope: Evidence envelope
        
    Returns:
        True if schema is valid
    """
    # Check required string fields
    if not envelope.evidence_id:
        return False
    if not envelope.execution_id:
        return False
    if not envelope.content_hash:
        return False
    if not envelope.timestamp:
        return False
    if not envelope.schema_version:
        return False
    
    return True


def verify_evidence_hash(envelope: EvidenceEnvelope, expected_hash: str) -> bool:
    """Verify evidence hash matches expected.
    
    Args:
        envelope: Evidence envelope
        expected_hash: Expected content hash
        
    Returns:
        True if hash matches
    """
    # Both hashes must be non-empty
    if not envelope.content_hash:
        return False
    if not expected_hash:
        return False
    
    return envelope.content_hash == expected_hash


def detect_evidence_replay(
    envelope: EvidenceEnvelope,
    known_hashes: frozenset
) -> bool:
    """Detect evidence replay attack.
    
    Args:
        envelope: Evidence envelope
        known_hashes: Set of previously seen hashes
        
    Returns:
        True if replay detected
    """
    return envelope.content_hash in known_hashes


def decide_evidence_acceptance(
    context: EvidenceVerificationContext
) -> EvidenceVerificationResult:
    """Decide evidence acceptance.
    
    Args:
        context: Verification context
        
    Returns:
        EvidenceVerificationResult
    """
    envelope = context.envelope
    
    # 1. Validate schema
    if not validate_evidence_schema(envelope):
        return EvidenceVerificationResult(
            decision=VerificationDecision.REJECT,
            integrity_status=EvidenceIntegrityStatus.INVALID,
            reason_code="EVD-001",
            reason_description="Schema validation failed"
        )
    
    # 2. Check execution ID match
    if envelope.execution_id != context.expected_execution_id:
        return EvidenceVerificationResult(
            decision=VerificationDecision.REJECT,
            integrity_status=EvidenceIntegrityStatus.INVALID,
            reason_code="EVD-002",
            reason_description="Execution ID mismatch"
        )
    
    # 3. Check format match
    if envelope.evidence_format != context.expected_format:
        return EvidenceVerificationResult(
            decision=VerificationDecision.REJECT,
            integrity_status=EvidenceIntegrityStatus.INVALID,
            reason_code="EVD-003",
            reason_description="Evidence format mismatch"
        )
    
    # 4. Detect replay
    if detect_evidence_replay(envelope, context.known_hashes):
        return EvidenceVerificationResult(
            decision=VerificationDecision.REJECT,
            integrity_status=EvidenceIntegrityStatus.REPLAY,
            reason_code="EVD-004",
            reason_description="Replay attack detected"
        )
    
    # 5. Verify hash
    if not verify_evidence_hash(envelope, context.expected_hash):
        return EvidenceVerificationResult(
            decision=VerificationDecision.REJECT,
            integrity_status=EvidenceIntegrityStatus.TAMPERED,
            reason_code="EVD-005",
            reason_description="Hash mismatch: possible tampering"
        )
    
    # All checks passed
    return EvidenceVerificationResult(
        decision=VerificationDecision.ACCEPT,
        integrity_status=EvidenceIntegrityStatus.VALID,
        reason_code="EVD-OK",
        reason_description="Evidence verified successfully"
    )
