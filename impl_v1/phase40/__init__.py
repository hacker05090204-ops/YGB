# Phase-40 Package Init
"""
Phase-40: Authority Arbitration & Conflict Resolution Engine
GOVERNANCE LAYER ONLY - Deterministic authority resolution

Authority Hierarchy: HUMAN > GOVERNANCE > GOVERNOR > INTERFACE > EXECUTOR

Exports:
- Types (enums, dataclasses)
- Authority engine
"""

from .authority_types import (
    # Enums
    AuthorityLevel,
    ConflictType,
    ResolutionRule,
    AuthorityDecision,
    OverrideReason,
    ArbitrationState,
    # Dataclasses
    AuthoritySource,
    AuthorityConflict,
    ArbitrationContext,
    ArbitrationResult,
    AuthorityAuditEntry,
)

from .authority_engine import (
    compare_authority,
    is_higher_authority,
    is_human_authority,
    is_executor_authority,
    detect_conflict,
    detect_conflicts_in_sources,
    resolve_conflict,
    arbitrate_sources,
    create_authority_audit_entry,
)

__all__ = [
    # Enums
    "AuthorityLevel",
    "ConflictType",
    "ResolutionRule",
    "AuthorityDecision",
    "OverrideReason",
    "ArbitrationState",
    # Dataclasses
    "AuthoritySource",
    "AuthorityConflict",
    "ArbitrationContext",
    "ArbitrationResult",
    "AuthorityAuditEntry",
    # Engine
    "compare_authority",
    "is_higher_authority",
    "is_human_authority",
    "is_executor_authority",
    "detect_conflict",
    "detect_conflicts_in_sources",
    "resolve_conflict",
    "arbitrate_sources",
    "create_authority_audit_entry",
]
