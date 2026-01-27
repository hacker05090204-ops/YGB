# Phase-40: Authority Arbitration & Conflict Resolution Engine - Types
# GOVERNANCE LAYER ONLY - Authority hierarchy and conflict resolution
# Implements deterministic authority precedence

"""
Phase-40 defines the governance types for authority arbitration.
This module implements:
- Authority hierarchy enums (CLOSED)
- Conflict resolution enums (CLOSED)  
- Arbitration dataclasses (frozen=True)

HUMAN > GOVERNANCE > GOVERNOR > INTERFACE > EXECUTOR
"""

from dataclasses import dataclass
from enum import Enum, IntEnum
from typing import Optional, List


# =============================================================================
# AUTHORITY HIERARCHY (IMMUTABLE - IntEnum for ordering)
# =============================================================================

class AuthorityLevel(IntEnum):
    """
    CLOSED ENUM - 5 members
    Authority levels from highest to lowest.
    IntEnum for natural ordering: higher number = higher authority.
    
    HUMAN > GOVERNANCE > GOVERNOR > INTERFACE > EXECUTOR
    """
    EXECUTOR = 0     # Zero trust - cannot self-authorize
    INTERFACE = 1    # Low trust - transport layer
    GOVERNOR = 2     # Medium trust - governance layer
    GOVERNANCE = 3   # High trust - governance rules
    HUMAN = 4        # Absolute trust - ultimate authority


class ConflictType(Enum):
    """
    CLOSED ENUM - 8 members
    Types of authority conflicts.
    """
    GOVERNOR_VS_GOVERNOR = "GOVERNOR_VS_GOVERNOR"
    HUMAN_VS_GOVERNOR = "HUMAN_VS_GOVERNOR"
    ALLOW_VS_DENY = "ALLOW_VS_DENY"
    RACE_CONDITION = "RACE_CONDITION"
    OVERLAPPING_SCOPE = "OVERLAPPING_SCOPE"
    PRECEDENCE_AMBIGUITY = "PRECEDENCE_AMBIGUITY"
    AUTHORITY_USURPATION = "AUTHORITY_USURPATION"
    UNKNOWN_CONFLICT = "UNKNOWN_CONFLICT"


class ResolutionRule(Enum):
    """
    CLOSED ENUM - 7 members
    Rules for resolving conflicts.
    """
    HIGHER_LEVEL_WINS = "HIGHER_LEVEL_WINS"   # Authority hierarchy
    DENY_WINS = "DENY_WINS"                   # At same level
    FIRST_REGISTERED = "FIRST_REGISTERED"     # Timestamp order
    EXPLICIT_WINS = "EXPLICIT_WINS"           # Explicit over implicit
    HUMAN_DECIDES = "HUMAN_DECIDES"           # Escalate
    ABORT_ALL = "ABORT_ALL"                   # Safety-critical
    SAFETY_WINS = "SAFETY_WINS"               # Safety over productivity


class AuthorityDecision(Enum):
    """
    CLOSED ENUM - 5 members
    Decisions from authority arbitration.
    """
    GRANT = "GRANT"        # Authority confirmed
    DENY = "DENY"          # Authority rejected
    ESCALATE = "ESCALATE"  # Human must decide
    OVERRIDE = "OVERRIDE"  # Higher authority overrules
    ABORT = "ABORT"        # Safety abort


class OverrideReason(Enum):
    """
    CLOSED ENUM - 6 members
    Reasons for authority override.
    """
    HIGHER_LEVEL = "HIGHER_LEVEL"
    SAFETY_CONCERN = "SAFETY_CONCERN"
    HUMAN_EXPLICIT = "HUMAN_EXPLICIT"
    DENY_PRECEDENCE = "DENY_PRECEDENCE"
    GOVERNANCE_RULE = "GOVERNANCE_RULE"
    NO_OVERRIDE = "NO_OVERRIDE"


class ArbitrationState(Enum):
    """
    CLOSED ENUM - 6 members
    States of arbitration process.
    """
    PENDING = "PENDING"
    ANALYZING = "ANALYZING"
    RESOLVED = "RESOLVED"
    ESCALATED = "ESCALATED"
    ABORTED = "ABORTED"
    TIMEOUT = "TIMEOUT"


# =============================================================================
# FROZEN DATACLASSES
# =============================================================================

@dataclass(frozen=True)
class AuthoritySource:
    """
    Frozen dataclass representing an authority claim.
    """
    source_id: str
    level: AuthorityLevel
    claim_type: str  # "ALLOW" or "DENY"
    scope: str
    timestamp: str
    context_hash: str


@dataclass(frozen=True)
class AuthorityConflict:
    """
    Frozen dataclass representing a detected conflict.
    """
    conflict_id: str
    conflict_type: ConflictType
    source_a: AuthoritySource
    source_b: AuthoritySource
    detected_at: str


@dataclass(frozen=True)
class ArbitrationContext:
    """
    Frozen dataclass for arbitration context.
    """
    context_id: str
    conflicting_sources: tuple  # Tuple of AuthoritySource
    scope: str
    timestamp: str
    human_override_requested: bool


@dataclass(frozen=True)
class ArbitrationResult:
    """
    Frozen dataclass for arbitration outcome.
    """
    result_id: str
    conflict_id: str
    decision: AuthorityDecision
    resolution_rule: ResolutionRule
    override_reason: OverrideReason
    winning_source_id: Optional[str]
    losing_source_ids: tuple
    explanation: str
    timestamp: str


@dataclass(frozen=True)
class AuthorityAuditEntry:
    """
    Frozen dataclass for authority audit entries.
    """
    audit_id: str
    conflict_id: str
    sources_involved: tuple
    decision: AuthorityDecision
    resolution_rule: ResolutionRule
    human_involved: bool
    timestamp: str
