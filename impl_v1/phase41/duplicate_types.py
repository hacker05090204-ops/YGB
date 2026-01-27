# Phase-41: Duplicate Prevention Engine - Types
# GOVERNANCE LAYER ONLY - No execution
# Implements signature-based duplicate detection

"""
Phase-41 defines governance types for duplicate prevention.
This module implements:
- Signature tier enums (CLOSED)
- Duplicate detection dataclasses (frozen=True)

DENY-BY-DEFAULT: Unknown signatures → BLOCK
"""

from dataclasses import dataclass
from enum import Enum
from typing import Optional, List, Tuple


# =============================================================================
# CLOSED ENUMS - Signature Types
# =============================================================================

class SignatureTier(Enum):
    """
    CLOSED ENUM - 4 members
    Signature matching tiers from most to least specific.
    """
    EXACT = "EXACT"           # Exact hash match
    PATTERN = "PATTERN"       # Pattern-based match
    SEMANTIC = "SEMANTIC"     # Semantic similarity
    PUBLIC = "PUBLIC"         # Known public report


class DuplicateDecision(Enum):
    """
    CLOSED ENUM - 5 members
    Decisions for duplicate detection.
    """
    ALLOW = "ALLOW"           # No duplicate found
    BLOCK = "BLOCK"           # Duplicate detected, block
    WARN = "WARN"             # Possible duplicate, warn
    ESCALATE = "ESCALATE"     # Uncertain, human decides
    PENDING = "PENDING"       # Analysis in progress


class BlockReason(Enum):
    """
    CLOSED ENUM - 8 members
    Reasons for blocking due to duplication.
    """
    EXACT_MATCH = "EXACT_MATCH"
    PATTERN_MATCH = "PATTERN_MATCH"
    PUBLIC_REPORT = "PUBLIC_REPORT"
    RECENT_SUBMISSION = "RECENT_SUBMISSION"
    SELF_DUPLICATE = "SELF_DUPLICATE"
    TEAM_DUPLICATE = "TEAM_DUPLICATE"
    PLATFORM_DUPLICATE = "PLATFORM_DUPLICATE"
    UNKNOWN_BLOCK = "UNKNOWN_BLOCK"


class SignatureSource(Enum):
    """
    CLOSED ENUM - 5 members
    Sources of signature data.
    """
    LOCAL_HISTORY = "LOCAL_HISTORY"
    TEAM_HISTORY = "TEAM_HISTORY"
    PLATFORM_API = "PLATFORM_API"
    PUBLIC_DISCLOSURE = "PUBLIC_DISCLOSURE"
    MANUAL_ENTRY = "MANUAL_ENTRY"


class HistoryScope(Enum):
    """
    CLOSED ENUM - 4 members
    Scope of history to check.
    """
    SELF_ONLY = "SELF_ONLY"
    TEAM = "TEAM"
    PLATFORM = "PLATFORM"
    GLOBAL = "GLOBAL"


class DuplicateConfidence(Enum):
    """
    CLOSED ENUM - 5 members
    Confidence levels for duplicate detection.
    """
    CERTAIN = "CERTAIN"       # 100% duplicate
    HIGH = "HIGH"             # 90%+ match
    MEDIUM = "MEDIUM"         # 70-89% match
    LOW = "LOW"               # 50-69% match
    UNCERTAIN = "UNCERTAIN"   # <50% match


# =============================================================================
# FROZEN DATACLASSES
# =============================================================================

@dataclass(frozen=True)
class Signature:
    """
    Frozen dataclass for a finding signature.
    """
    signature_id: str
    tier: SignatureTier
    hash_value: str
    pattern: str
    created_at: str
    source: SignatureSource


@dataclass(frozen=True)
class DuplicateCheck:
    """
    Frozen dataclass for a duplicate check request.
    """
    check_id: str
    finding_hash: str
    finding_pattern: str
    target_id: str
    hunter_id: str
    scope: HistoryScope
    timestamp: str


@dataclass(frozen=True)
class DuplicateResult:
    """
    Frozen dataclass for duplicate check result.
    """
    check_id: str
    decision: DuplicateDecision
    confidence: DuplicateConfidence
    block_reason: Optional[BlockReason]
    matching_signature_id: Optional[str]
    explanation: str


@dataclass(frozen=True)
class HistoryEntry:
    """
    Frozen dataclass for a history entry.
    """
    entry_id: str
    signature: Signature
    target_id: str
    hunter_id: str
    submitted_at: str
    status: str  # "SUBMITTED", "ACCEPTED", "REJECTED"


@dataclass(frozen=True)
class PublicReport:
    """
    Frozen dataclass for a public disclosure.
    """
    report_id: str
    cve_id: Optional[str]
    disclosure_date: str
    signature_pattern: str
    source_url: str


@dataclass(frozen=True)
class DuplicateAuditEntry:
    """
    Frozen dataclass for duplicate check audit.
    """
    audit_id: str
    check_id: str
    decision: DuplicateDecision
    block_reason: Optional[BlockReason]
    confidence: DuplicateConfidence
    timestamp: str
