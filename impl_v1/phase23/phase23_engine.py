"""
impl_v1 Phase-23 Evidence Integrity Engine.

NON-AUTHORITATIVE MIRROR of governance Phase-23.
Contains PURE VALIDATION FUNCTIONS ONLY.

THIS MODULE HAS NO EXECUTION AUTHORITY.
THIS MODULE NEVER RECORDS EVIDENCE.
THIS MODULE NEVER COMPUTES REAL HASHES (compare only).

VALIDATION FUNCTIONS ONLY:
- validate_evidence_id
- validate_evidence_format
- validate_payload_hash
- detect_replay
- verify_evidence_integrity
- get_verification_decision

INVARIANTS:
- Hash mismatch → TAMPERED
- Replay detected → REPLAYED
- Any ambiguity → ESCALATE
- Default = REJECT

DENY-BY-DEFAULT.
"""
import re
from typing import Optional, Set

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


# Regex pattern for valid evidence ID
_EVIDENCE_ID_PATTERN = re.compile(r'^EVIDENCE-[a-fA-F0-9]{8,}$')


def validate_evidence_id(evidence_id: Optional[str]) -> bool:
    """Validate an evidence ID format.
    
    Args:
        evidence_id: Evidence ID to validate
        
    Returns:
        True if valid, False otherwise
        
    Rules:
        - DENY-BY-DEFAULT
        - None → False
        - Empty → False
        - Invalid format → False
    """
    if evidence_id is None:
        return False
    if not isinstance(evidence_id, str):
        return False
    if not evidence_id.strip():
        return False
    return bool(_EVIDENCE_ID_PATTERN.match(evidence_id))


def validate_evidence_format(
    envelope: Optional[EvidenceEnvelope],
    expected_format: Optional[EvidenceFormat]
) -> bool:
    """Validate evidence format matches expected.
    
    Args:
        envelope: Evidence envelope
        expected_format: Expected format
        
    Returns:
        True if format matches, False otherwise
        
    Rules:
        - DENY-BY-DEFAULT
        - None envelope → False
        - None expected → False
        - Format mismatch → False
    """
    if envelope is None:
        return False
    if expected_format is None:
        return False
    if not isinstance(envelope.format, EvidenceFormat):
        return False
    return envelope.format == expected_format


def validate_payload_hash(
    envelope: Optional[EvidenceEnvelope],
    expected_hash: Optional[str]
) -> bool:
    """Validate payload hash matches expected.
    
    THIS FUNCTION COMPARES HASHES ONLY.
    THIS FUNCTION NEVER COMPUTES HASHES.
    
    Args:
        envelope: Evidence envelope
        expected_hash: Expected hash value
        
    Returns:
        True if hash matches, False otherwise
        
    Rules:
        - DENY-BY-DEFAULT
        - None envelope → False
        - None expected_hash → False
        - Hash mismatch → False
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


def detect_replay(
    envelope: Optional[EvidenceEnvelope],
    seen_hashes: Optional[Set[str]]
) -> bool:
    """Detect if evidence is a replay.
    
    Args:
        envelope: Evidence envelope
        seen_hashes: Set of previously seen payload hashes
        
    Returns:
        True if replay detected, False otherwise
        
    Rules:
        - DENY-BY-DEFAULT (treats None as replay-risk)
        - None envelope → True (unsafe)
        - None seen_hashes → False (no history to check)
        - Hash in seen_hashes → True (replay)
    """
    if envelope is None:
        return True  # Treat None as unsafe
    if seen_hashes is None:
        return False  # No history, can't detect replay
    if not isinstance(seen_hashes, set):
        return False  # Invalid type, can't check
    if not envelope.payload_hash:
        return True  # Missing hash is suspicious
    return envelope.payload_hash in seen_hashes


def verify_evidence_integrity(
    envelope: Optional[EvidenceEnvelope],
    context: Optional[EvidenceVerificationContext],
    expected_hash: Optional[str] = None,
    seen_hashes: Optional[Set[str]] = None
) -> EvidenceVerificationResult:
    """Verify evidence integrity.
    
    Args:
        envelope: Evidence envelope to verify
        context: Verification context
        expected_hash: Expected payload hash
        seen_hashes: Set of previously seen hashes
        
    Returns:
        EvidenceVerificationResult with status and decision
        
    Rules:
        - DENY-BY-DEFAULT → REJECT
        - None envelope → INVALID, REJECT
        - Invalid ID → INVALID, REJECT
        - Format mismatch → INVALID, REJECT
        - Source mismatch → INVALID, ESCALATE
        - Hash mismatch → TAMPERED, REJECT
        - Replay detected (not allowed) → REPLAYED, REJECT
        - Replay detected (allowed) → VALID, ACCEPT
        - All valid → VALID, ACCEPT
    """
    reasons: list[str] = []
    
    # DENY-BY-DEFAULT: None envelope
    if envelope is None:
        return EvidenceVerificationResult(
            status=EvidenceIntegrityStatus.INVALID,
            decision=VerificationDecision.REJECT,
            reasons=("Missing evidence envelope",)
        )
    
    # DENY-BY-DEFAULT: None context
    if context is None:
        return EvidenceVerificationResult(
            status=EvidenceIntegrityStatus.INVALID,
            decision=VerificationDecision.REJECT,
            reasons=("Missing verification context",)
        )
    
    # Validate evidence_id
    if not validate_evidence_id(envelope.evidence_id):
        reasons.append("Invalid evidence ID")
    
    # Validate timestamp
    if not envelope.timestamp or not isinstance(envelope.timestamp, str):
        reasons.append("Invalid timestamp")
    elif not envelope.timestamp.strip():
        reasons.append("Empty timestamp")
    
    # Validate version
    if not envelope.version or not isinstance(envelope.version, str):
        reasons.append("Invalid version")
    elif not envelope.version.strip():
        reasons.append("Empty version")
    
    # Validate format
    if not validate_evidence_format(envelope, context.expected_format):
        reasons.append("Format mismatch")
    
    # Validate source
    if envelope.source != context.expected_source:
        # Source mismatch is ambiguous → ESCALATE
        return EvidenceVerificationResult(
            status=EvidenceIntegrityStatus.INVALID,
            decision=VerificationDecision.ESCALATE,
            reasons=tuple(reasons + ["Source mismatch - requires review"])
        )
    
    # If basic validation failed, REJECT
    if reasons:
        return EvidenceVerificationResult(
            status=EvidenceIntegrityStatus.INVALID,
            decision=VerificationDecision.REJECT,
            reasons=tuple(reasons)
        )
    
    # Validate hash if expected_hash provided
    if expected_hash is not None:
        if not validate_payload_hash(envelope, expected_hash):
            return EvidenceVerificationResult(
                status=EvidenceIntegrityStatus.TAMPERED,
                decision=VerificationDecision.REJECT,
                reasons=("Hash mismatch - evidence tampered",)
            )
    
    # Check for replay
    is_replay = detect_replay(envelope, seen_hashes)
    if is_replay:
        if context.allow_replay:
            return EvidenceVerificationResult(
                status=EvidenceIntegrityStatus.VALID,
                decision=VerificationDecision.ACCEPT,
                reasons=("Replay detected but allowed",)
            )
        else:
            return EvidenceVerificationResult(
                status=EvidenceIntegrityStatus.REPLAYED,
                decision=VerificationDecision.REJECT,
                reasons=("Replay detected - evidence already processed",)
            )
    
    # All checks passed
    return EvidenceVerificationResult(
        status=EvidenceIntegrityStatus.VALID,
        decision=VerificationDecision.ACCEPT,
        reasons=()
    )


def get_verification_decision(
    result: Optional[EvidenceVerificationResult]
) -> VerificationDecision:
    """Get verification decision from result.
    
    Args:
        result: Verification result
        
    Returns:
        VerificationDecision
        
    Rules:
        - DENY-BY-DEFAULT → REJECT
        - None → REJECT
        - Invalid decision type → REJECT
        - Valid → result's decision
    """
    if result is None:
        return VerificationDecision.REJECT
    if not isinstance(result.decision, VerificationDecision):
        return VerificationDecision.REJECT
    return result.decision
