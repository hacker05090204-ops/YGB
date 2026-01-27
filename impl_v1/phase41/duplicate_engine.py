# Phase-41: Duplicate Prevention Engine - Detection Engine
# GOVERNANCE LAYER ONLY - Deterministic duplicate detection

"""
Phase-41 Duplicate Detection Engine

Implements deterministic duplicate detection:
- Signature matching across tiers
- History checking
- Public report avoidance
- Deterministic blocking

DENY-BY-DEFAULT: Unknown or uncertain → BLOCK
"""

import hashlib
import uuid
from datetime import datetime
from typing import Optional, List, Dict

from .duplicate_types import (
    Signature,
    DuplicateCheck,
    DuplicateResult,
    HistoryEntry,
    PublicReport,
    DuplicateAuditEntry,
    SignatureTier,
    DuplicateDecision,
    BlockReason,
    SignatureSource,
    HistoryScope,
    DuplicateConfidence,
)


# =============================================================================
# SIGNATURE GENERATION
# =============================================================================

def generate_signature_hash(content: str) -> str:
    """Generate a SHA-256 hash of content for exact matching."""
    if not content:
        return ""
    return hashlib.sha256(content.encode()).hexdigest()


def generate_pattern_hash(pattern: str) -> str:
    """Generate a normalized pattern hash for pattern matching."""
    if not pattern:
        return ""
    # Normalize: lowercase, strip whitespace, remove special chars
    normalized = pattern.lower().strip()
    normalized = ''.join(c for c in normalized if c.isalnum() or c.isspace())
    return hashlib.sha256(normalized.encode()).hexdigest()[:32]


def create_signature(
    content: str,
    pattern: str,
    source: SignatureSource,
) -> Signature:
    """Create a signature from content."""
    return Signature(
        signature_id=f"SIG-{uuid.uuid4().hex[:16].upper()}",
        tier=SignatureTier.EXACT,
        hash_value=generate_signature_hash(content),
        pattern=generate_pattern_hash(pattern),
        created_at=datetime.utcnow().isoformat() + "Z",
        source=source,
    )


# =============================================================================
# SIGNATURE MATCHING
# =============================================================================

def match_exact(sig_a: str, sig_b: str) -> bool:
    """Check for exact signature match."""
    if not sig_a or not sig_b:
        return False
    return sig_a == sig_b


def match_pattern(pattern_a: str, pattern_b: str) -> bool:
    """Check for pattern match."""
    if not pattern_a or not pattern_b:
        return False
    return pattern_a == pattern_b


def calculate_similarity(sig_a: str, sig_b: str) -> float:
    """Calculate similarity between two signatures (0.0 to 1.0)."""
    if not sig_a or not sig_b:
        return 0.0
    if sig_a == sig_b:
        return 1.0
    
    # Simple character-level similarity for determinism
    matches = sum(a == b for a, b in zip(sig_a, sig_b))
    max_len = max(len(sig_a), len(sig_b))
    return matches / max_len if max_len > 0 else 0.0


def determine_confidence(similarity: float) -> DuplicateConfidence:
    """Determine confidence level from similarity score."""
    if similarity >= 1.0:
        return DuplicateConfidence.CERTAIN
    if similarity >= 0.9:
        return DuplicateConfidence.HIGH
    if similarity >= 0.7:
        return DuplicateConfidence.MEDIUM
    if similarity >= 0.5:
        return DuplicateConfidence.LOW
    return DuplicateConfidence.UNCERTAIN


# =============================================================================
# HISTORY CHECKING
# =============================================================================

def check_local_history(
    check: DuplicateCheck,
    history: List[HistoryEntry],
) -> Optional[HistoryEntry]:
    """Check local history for duplicates."""
    for entry in history:
        # Same hunter
        if entry.hunter_id != check.hunter_id:
            continue
        
        # Same target
        if entry.target_id != check.target_id:
            continue
        
        # Check signature match
        if match_exact(entry.signature.hash_value, check.finding_hash):
            return entry
        if match_pattern(entry.signature.pattern, check.finding_pattern):
            return entry
    
    return None


def check_team_history(
    check: DuplicateCheck,
    history: List[HistoryEntry],
    team_ids: List[str],
) -> Optional[HistoryEntry]:
    """Check team history for duplicates."""
    for entry in history:
        # Must be team member
        if entry.hunter_id not in team_ids:
            continue
        
        # Same target
        if entry.target_id != check.target_id:
            continue
        
        # Check signature match
        if match_exact(entry.signature.hash_value, check.finding_hash):
            return entry
    
    return None


def check_public_reports(
    check: DuplicateCheck,
    public_reports: List[PublicReport],
) -> Optional[PublicReport]:
    """Check public disclosures for duplicates."""
    for report in public_reports:
        if match_pattern(report.signature_pattern, check.finding_pattern):
            return report
    
    return None


# =============================================================================
# DUPLICATE DETECTION ENGINE
# =============================================================================

def detect_duplicate(
    check: DuplicateCheck,
    local_history: List[HistoryEntry] = None,
    team_history: List[HistoryEntry] = None,
    team_ids: List[str] = None,
    public_reports: List[PublicReport] = None,
) -> DuplicateResult:
    """
    Detect duplicates deterministically.
    
    Check Order:
    1. Local history (self-duplicate)
    2. Team history (team-duplicate)
    3. Public reports (public-duplicate)
    
    DENY-BY-DEFAULT: Any match → BLOCK
    """
    local_history = local_history or []
    team_history = team_history or []
    team_ids = team_ids or []
    public_reports = public_reports or []
    
    # Check 1: Local history
    local_match = check_local_history(check, local_history)
    if local_match:
        return DuplicateResult(
            check_id=check.check_id,
            decision=DuplicateDecision.BLOCK,
            confidence=DuplicateConfidence.CERTAIN,
            block_reason=BlockReason.SELF_DUPLICATE,
            matching_signature_id=local_match.signature.signature_id,
            explanation="Self-duplicate: You have already submitted this finding",
        )
    
    # Check 2: Team history
    if check.scope in [HistoryScope.TEAM, HistoryScope.PLATFORM, HistoryScope.GLOBAL]:
        team_match = check_team_history(check, team_history, team_ids)
        if team_match:
            return DuplicateResult(
                check_id=check.check_id,
                decision=DuplicateDecision.BLOCK,
                confidence=DuplicateConfidence.HIGH,
                block_reason=BlockReason.TEAM_DUPLICATE,
                matching_signature_id=team_match.signature.signature_id,
                explanation="Team duplicate: A team member has already submitted this",
            )
    
    # Check 3: Public reports
    public_match = check_public_reports(check, public_reports)
    if public_match:
        return DuplicateResult(
            check_id=check.check_id,
            decision=DuplicateDecision.BLOCK,
            confidence=DuplicateConfidence.HIGH,
            block_reason=BlockReason.PUBLIC_REPORT,
            matching_signature_id=public_match.report_id,
            explanation=f"Public disclosure: CVE {public_match.cve_id or 'N/A'}",
        )
    
    # No duplicates found
    return DuplicateResult(
        check_id=check.check_id,
        decision=DuplicateDecision.ALLOW,
        confidence=DuplicateConfidence.CERTAIN,
        block_reason=None,
        matching_signature_id=None,
        explanation="No duplicates detected",
    )


# =============================================================================
# AUDIT LOGGING
# =============================================================================

def create_duplicate_audit_entry(
    result: DuplicateResult,
) -> DuplicateAuditEntry:
    """Create an audit entry for a duplicate check."""
    return DuplicateAuditEntry(
        audit_id=f"DAUD-{uuid.uuid4().hex[:16].upper()}",
        check_id=result.check_id,
        decision=result.decision,
        block_reason=result.block_reason,
        confidence=result.confidence,
        timestamp=datetime.utcnow().isoformat() + "Z",
    )
