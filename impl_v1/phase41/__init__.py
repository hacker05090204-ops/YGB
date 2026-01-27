# Phase-41 Package Init
"""
Phase-41: Duplicate Prevention Engine
GOVERNANCE LAYER ONLY - Signature-based duplicate detection

Exports types and engine functions.
"""

from .duplicate_types import (
    # Enums
    SignatureTier,
    DuplicateDecision,
    BlockReason,
    SignatureSource,
    HistoryScope,
    DuplicateConfidence,
    # Dataclasses
    Signature,
    DuplicateCheck,
    DuplicateResult,
    HistoryEntry,
    PublicReport,
    DuplicateAuditEntry,
)

from .duplicate_engine import (
    generate_signature_hash,
    generate_pattern_hash,
    create_signature,
    match_exact,
    match_pattern,
    calculate_similarity,
    determine_confidence,
    check_local_history,
    check_team_history,
    check_public_reports,
    detect_duplicate,
    create_duplicate_audit_entry,
)

__all__ = [
    # Enums
    "SignatureTier",
    "DuplicateDecision",
    "BlockReason",
    "SignatureSource",
    "HistoryScope",
    "DuplicateConfidence",
    # Dataclasses
    "Signature",
    "DuplicateCheck",
    "DuplicateResult",
    "HistoryEntry",
    "PublicReport",
    "DuplicateAuditEntry",
    # Engine
    "generate_signature_hash",
    "generate_pattern_hash",
    "create_signature",
    "match_exact",
    "match_pattern",
    "calculate_similarity",
    "determine_confidence",
    "check_local_history",
    "check_team_history",
    "check_public_reports",
    "detect_duplicate",
    "create_duplicate_audit_entry",
]
