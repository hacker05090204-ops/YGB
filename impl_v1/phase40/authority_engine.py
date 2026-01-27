# Phase-40: Authority Arbitration & Conflict Resolution Engine
# GOVERNANCE LAYER ONLY - Deterministic authority resolution
# HUMAN > GOVERNANCE > GOVERNOR > INTERFACE > EXECUTOR

"""
Phase-40 Authority Arbitration Engine

Implements deterministic authority resolution:
- Authority hierarchy comparison
- Conflict detection
- Deterministic resolution
- Human override handling

CRITICAL INVARIANTS:
- HUMAN is always Level 4 (highest)
- DENY wins at same authority level
- EXECUTOR (Level 0) cannot self-authorize
- All resolution is deterministic
"""

import uuid
from datetime import datetime
from typing import Optional, List, Tuple

from .authority_types import (
    AuthoritySource,
    AuthorityConflict,
    ArbitrationContext,
    ArbitrationResult,
    AuthorityAuditEntry,
    AuthorityLevel,
    ConflictType,
    ResolutionRule,
    AuthorityDecision,
    OverrideReason,
    ArbitrationState,
)


# =============================================================================
# AUTHORITY COMPARISON (DETERMINISTIC)
# =============================================================================

def compare_authority(
    source_a: AuthoritySource,
    source_b: AuthoritySource
) -> int:
    """
    Compare two authority sources.
    Returns:
    - Positive if source_a has higher authority
    - Negative if source_b has higher authority
    - Zero if equal authority
    """
    return int(source_a.level) - int(source_b.level)


def is_higher_authority(
    source: AuthoritySource,
    other: AuthoritySource
) -> bool:
    """Check if source has strictly higher authority than other."""
    return compare_authority(source, other) > 0


def is_human_authority(source: AuthoritySource) -> bool:
    """Check if source is human authority."""
    return source.level == AuthorityLevel.HUMAN


def is_executor_authority(source: AuthoritySource) -> bool:
    """Check if source is executor authority (zero trust)."""
    return source.level == AuthorityLevel.EXECUTOR


# =============================================================================
# CONFLICT DETECTION
# =============================================================================

def detect_conflict(
    source_a: AuthoritySource,
    source_b: AuthoritySource
) -> Optional[AuthorityConflict]:
    """
    Detect if two authority sources conflict.
    
    Conflict occurs when:
    - Different claim types (ALLOW vs DENY) for same scope
    - Same scope with overlapping claims
    """
    
    # No conflict if same claim type
    if source_a.claim_type == source_b.claim_type:
        return None
    
    # No conflict if different scopes
    if source_a.scope != source_b.scope:
        return None
    
    # Conflict: ALLOW vs DENY for same scope
    conflict_type = ConflictType.ALLOW_VS_DENY
    
    # Check if it's human vs governor
    if (source_a.level == AuthorityLevel.HUMAN or 
        source_b.level == AuthorityLevel.HUMAN):
        conflict_type = ConflictType.HUMAN_VS_GOVERNOR
    
    # Check if both are governors
    if (source_a.level == AuthorityLevel.GOVERNOR and 
        source_b.level == AuthorityLevel.GOVERNOR):
        conflict_type = ConflictType.GOVERNOR_VS_GOVERNOR
    
    # Check for authority usurpation (executor trying to override)
    if ((source_a.level == AuthorityLevel.EXECUTOR and source_b.level > AuthorityLevel.EXECUTOR) or
        (source_b.level == AuthorityLevel.EXECUTOR and source_a.level > AuthorityLevel.EXECUTOR)):
        conflict_type = ConflictType.AUTHORITY_USURPATION
    
    return AuthorityConflict(
        conflict_id=f"CONF-{uuid.uuid4().hex[:16].upper()}",
        conflict_type=conflict_type,
        source_a=source_a,
        source_b=source_b,
        detected_at=datetime.utcnow().isoformat() + "Z"
    )


def detect_conflicts_in_sources(
    sources: List[AuthoritySource]
) -> List[AuthorityConflict]:
    """Detect all conflicts among a list of authority sources."""
    conflicts = []
    for i, source_a in enumerate(sources):
        for source_b in sources[i+1:]:
            conflict = detect_conflict(source_a, source_b)
            if conflict:
                conflicts.append(conflict)
    return conflicts


# =============================================================================
# CONFLICT RESOLUTION (DETERMINISTIC)
# =============================================================================

def resolve_conflict(
    conflict: AuthorityConflict,
    human_decision: Optional[str] = None
) -> ArbitrationResult:
    """
    Resolve a conflict deterministically.
    
    Resolution Rules (in order):
    1. HUMAN always wins
    2. Higher authority level wins
    3. At same level, DENY wins
    4. If still tied, first registered wins
    5. Authority usurpation → DENY the executor
    """
    
    source_a = conflict.source_a
    source_b = conflict.source_b
    
    # Rule 0: Authority usurpation → DENY executor, no compromise
    if conflict.conflict_type == ConflictType.AUTHORITY_USURPATION:
        # Find which one is the executor
        if source_a.level == AuthorityLevel.EXECUTOR:
            loser = source_a
            winner = source_b
        else:
            loser = source_b
            winner = source_a
        
        return ArbitrationResult(
            result_id=f"RES-{uuid.uuid4().hex[:16].upper()}",
            conflict_id=conflict.conflict_id,
            decision=AuthorityDecision.DENY,
            resolution_rule=ResolutionRule.HIGHER_LEVEL_WINS,
            override_reason=OverrideReason.HIGHER_LEVEL,
            winning_source_id=winner.source_id,
            losing_source_ids=(loser.source_id,),
            explanation="Executor cannot override higher authority",
            timestamp=datetime.utcnow().isoformat() + "Z"
        )
    
    # Rule 1: HUMAN always wins
    if source_a.level == AuthorityLevel.HUMAN:
        return ArbitrationResult(
            result_id=f"RES-{uuid.uuid4().hex[:16].upper()}",
            conflict_id=conflict.conflict_id,
            decision=AuthorityDecision.OVERRIDE,
            resolution_rule=ResolutionRule.HIGHER_LEVEL_WINS,
            override_reason=OverrideReason.HUMAN_EXPLICIT,
            winning_source_id=source_a.source_id,
            losing_source_ids=(source_b.source_id,),
            explanation="Human authority always takes precedence",
            timestamp=datetime.utcnow().isoformat() + "Z"
        )
    
    if source_b.level == AuthorityLevel.HUMAN:
        return ArbitrationResult(
            result_id=f"RES-{uuid.uuid4().hex[:16].upper()}",
            conflict_id=conflict.conflict_id,
            decision=AuthorityDecision.OVERRIDE,
            resolution_rule=ResolutionRule.HIGHER_LEVEL_WINS,
            override_reason=OverrideReason.HUMAN_EXPLICIT,
            winning_source_id=source_b.source_id,
            losing_source_ids=(source_a.source_id,),
            explanation="Human authority always takes precedence",
            timestamp=datetime.utcnow().isoformat() + "Z"
        )
    
    # Rule 2: Higher authority level wins
    if source_a.level > source_b.level:
        return ArbitrationResult(
            result_id=f"RES-{uuid.uuid4().hex[:16].upper()}",
            conflict_id=conflict.conflict_id,
            decision=AuthorityDecision.OVERRIDE,
            resolution_rule=ResolutionRule.HIGHER_LEVEL_WINS,
            override_reason=OverrideReason.HIGHER_LEVEL,
            winning_source_id=source_a.source_id,
            losing_source_ids=(source_b.source_id,),
            explanation=f"Level {source_a.level.name} > Level {source_b.level.name}",
            timestamp=datetime.utcnow().isoformat() + "Z"
        )
    
    if source_b.level > source_a.level:
        return ArbitrationResult(
            result_id=f"RES-{uuid.uuid4().hex[:16].upper()}",
            conflict_id=conflict.conflict_id,
            decision=AuthorityDecision.OVERRIDE,
            resolution_rule=ResolutionRule.HIGHER_LEVEL_WINS,
            override_reason=OverrideReason.HIGHER_LEVEL,
            winning_source_id=source_b.source_id,
            losing_source_ids=(source_a.source_id,),
            explanation=f"Level {source_b.level.name} > Level {source_a.level.name}",
            timestamp=datetime.utcnow().isoformat() + "Z"
        )
    
    # Rule 3: Same level - DENY wins
    if source_a.claim_type == "DENY":
        return ArbitrationResult(
            result_id=f"RES-{uuid.uuid4().hex[:16].upper()}",
            conflict_id=conflict.conflict_id,
            decision=AuthorityDecision.DENY,
            resolution_rule=ResolutionRule.DENY_WINS,
            override_reason=OverrideReason.DENY_PRECEDENCE,
            winning_source_id=source_a.source_id,
            losing_source_ids=(source_b.source_id,),
            explanation="DENY takes precedence over ALLOW at same level",
            timestamp=datetime.utcnow().isoformat() + "Z"
        )
    
    if source_b.claim_type == "DENY":
        return ArbitrationResult(
            result_id=f"RES-{uuid.uuid4().hex[:16].upper()}",
            conflict_id=conflict.conflict_id,
            decision=AuthorityDecision.DENY,
            resolution_rule=ResolutionRule.DENY_WINS,
            override_reason=OverrideReason.DENY_PRECEDENCE,
            winning_source_id=source_b.source_id,
            losing_source_ids=(source_a.source_id,),
            explanation="DENY takes precedence over ALLOW at same level",
            timestamp=datetime.utcnow().isoformat() + "Z"
        )
    
    # Rule 4: First registered wins (timestamp comparison)
    if source_a.timestamp <= source_b.timestamp:
        return ArbitrationResult(
            result_id=f"RES-{uuid.uuid4().hex[:16].upper()}",
            conflict_id=conflict.conflict_id,
            decision=AuthorityDecision.GRANT,
            resolution_rule=ResolutionRule.FIRST_REGISTERED,
            override_reason=OverrideReason.NO_OVERRIDE,
            winning_source_id=source_a.source_id,
            losing_source_ids=(source_b.source_id,),
            explanation="First registered claim wins",
            timestamp=datetime.utcnow().isoformat() + "Z"
        )
    else:
        return ArbitrationResult(
            result_id=f"RES-{uuid.uuid4().hex[:16].upper()}",
            conflict_id=conflict.conflict_id,
            decision=AuthorityDecision.GRANT,
            resolution_rule=ResolutionRule.FIRST_REGISTERED,
            override_reason=OverrideReason.NO_OVERRIDE,
            winning_source_id=source_b.source_id,
            losing_source_ids=(source_a.source_id,),
            explanation="First registered claim wins",
            timestamp=datetime.utcnow().isoformat() + "Z"
        )


# =============================================================================
# MULTI-SOURCE ARBITRATION
# =============================================================================

def arbitrate_sources(
    sources: List[AuthoritySource],
    context: Optional[ArbitrationContext] = None
) -> Tuple[AuthorityDecision, Optional[str], List[ArbitrationResult]]:
    """
    Arbitrate among multiple authority sources.
    
    Returns:
    - Final decision (GRANT, DENY, ESCALATE, ABORT)
    - Winning source ID (if any)
    - List of all arbitration results
    """
    
    if not sources:
        return AuthorityDecision.DENY, None, []
    
    if len(sources) == 1:
        source = sources[0]
        if source.level == AuthorityLevel.EXECUTOR:
            # Executor cannot self-authorize
            return AuthorityDecision.DENY, None, []
        if source.claim_type == "DENY":
            return AuthorityDecision.DENY, source.source_id, []
        return AuthorityDecision.GRANT, source.source_id, []
    
    # Detect all conflicts
    conflicts = detect_conflicts_in_sources(sources)
    
    if not conflicts:
        # No conflicts - check if any source is DENY
        for source in sources:
            if source.claim_type == "DENY":
                return AuthorityDecision.DENY, source.source_id, []
        
        # Find highest authority source
        highest = max(sources, key=lambda s: s.level)
        return AuthorityDecision.GRANT, highest.source_id, []
    
    # Resolve all conflicts
    results = []
    winning_source_id = None
    
    for conflict in conflicts:
        result = resolve_conflict(conflict)
        results.append(result)
        
        # Track overall winner
        if result.decision in [AuthorityDecision.GRANT, AuthorityDecision.OVERRIDE]:
            winning_source_id = result.winning_source_id
        elif result.decision == AuthorityDecision.DENY:
            winning_source_id = result.winning_source_id
    
    # Determine final decision
    # If any result is DENY, overall is DENY
    for result in results:
        if result.decision == AuthorityDecision.DENY:
            return AuthorityDecision.DENY, result.winning_source_id, results
    
    # If any result is ABORT, overall is ABORT
    for result in results:
        if result.decision == AuthorityDecision.ABORT:
            return AuthorityDecision.ABORT, None, results
    
    return AuthorityDecision.GRANT, winning_source_id, results


# =============================================================================
# AUDIT LOGGING
# =============================================================================

def create_authority_audit_entry(
    conflict: AuthorityConflict,
    result: ArbitrationResult,
    human_involved: bool = False
) -> AuthorityAuditEntry:
    """Create an audit entry for an authority arbitration event."""
    return AuthorityAuditEntry(
        audit_id=f"AAUD-{uuid.uuid4().hex[:16].upper()}",
        conflict_id=conflict.conflict_id,
        sources_involved=(conflict.source_a.source_id, conflict.source_b.source_id),
        decision=result.decision,
        resolution_rule=result.resolution_rule,
        human_involved=human_involved,
        timestamp=datetime.utcnow().isoformat() + "Z"
    )
