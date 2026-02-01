"""
Phase-13 Readiness Engine.

This module provides readiness checking and handoff decision logic.

All functions are pure (no side effects).
All dataclasses are frozen=True for immutability.
"""
from dataclasses import dataclass

from python.phase12_evidence.evidence_types import ConfidenceLevel, EvidenceState
from .handoff_types import ReadinessState, HumanPresence, BugSeverity, TargetType
from .handoff_context import HandoffContext


@dataclass(frozen=True)
class HandoffDecision:
    """Immutable handoff decision result.
    
    Attributes:
        bug_id: Bug that was evaluated
        readiness: Readiness state
        human_presence: Required human presence
        can_proceed: Whether handoff is allowed
        is_blocked: Whether handoff is blocked
        reason_code: Machine-readable reason
        reason_description: Human-readable reason
        blockers: Tuple of active blockers
    """
    bug_id: str
    readiness: ReadinessState
    human_presence: HumanPresence
    can_proceed: bool
    is_blocked: bool
    reason_code: str
    reason_description: str
    blockers: tuple


def check_readiness(context: HandoffContext) -> ReadinessState:
    """Determine readiness state for browser handoff.
    
    Decision table:
    | Confidence | Consistency | Review | Blockers | → Readiness |
    |------------|-------------|--------|----------|-------------|
    | LOW | Any | Any | Any | NOT_READY |
    | MEDIUM | Any | Any | Any | NOT_READY |
    | HIGH | INCONSISTENT | Any | Any | NOT_READY |
    | HIGH | UNVERIFIED | Any | Any | NOT_READY |
    | HIGH | RAW | Any | Any | REVIEW_REQUIRED |
    | HIGH | CONSISTENT | NO | Any | REVIEW_REQUIRED |
    | HIGH | CONSISTENT | YES | YES | NOT_READY |
    | HIGH | CONSISTENT | YES | NO | READY_FOR_BROWSER |
    | HIGH | REPLAYABLE | YES | NO | READY_FOR_BROWSER |
    
    Args:
        context: HandoffContext with bug details
        
    Returns:
        ReadinessState
    """
    # RD-001: LOW confidence → NOT_READY
    if context.confidence == ConfidenceLevel.LOW:
        return ReadinessState.NOT_READY
    
    # RD-002: MEDIUM confidence → NOT_READY
    if context.confidence == ConfidenceLevel.MEDIUM:
        return ReadinessState.NOT_READY
    
    # Now we know confidence is HIGH
    
    # RD-003: INCONSISTENT → NOT_READY
    if context.consistency_state == EvidenceState.INCONSISTENT:
        return ReadinessState.NOT_READY
    
    # RD-004: UNVERIFIED → NOT_READY
    if context.consistency_state == EvidenceState.UNVERIFIED:
        return ReadinessState.NOT_READY
    
    # RD-005: RAW → REVIEW_REQUIRED
    if context.consistency_state == EvidenceState.RAW:
        return ReadinessState.REVIEW_REQUIRED
    
    # RD-006: CONSISTENT but no human review → REVIEW_REQUIRED
    if context.consistency_state == EvidenceState.CONSISTENT:
        if not context.human_review_completed:
            return ReadinessState.REVIEW_REQUIRED
        
        # RD-007: Has blockers → NOT_READY
        if context.has_active_blockers:
            return ReadinessState.NOT_READY
        
        # RD-008: All good → READY_FOR_BROWSER
        return ReadinessState.READY_FOR_BROWSER
    
    # RD-009: REPLAYABLE + reviewed + no blockers → READY_FOR_BROWSER
    if context.consistency_state == EvidenceState.REPLAYABLE:
        if not context.human_review_completed:
            return ReadinessState.REVIEW_REQUIRED
        
        if context.has_active_blockers:
            return ReadinessState.NOT_READY
        
        return ReadinessState.READY_FOR_BROWSER
    
    # Deny-by-default: Unknown → NOT_READY
    return ReadinessState.NOT_READY  # pragma: no cover


def determine_human_presence(
    readiness: ReadinessState,
    context: HandoffContext
) -> HumanPresence:
    """Determine required human presence level.
    
    Decision table:
    | Readiness | Severity | Target | → HumanPresence |
    |-----------|----------|--------|-----------------|
    | NOT_READY | Any | Any | BLOCKING |
    | REVIEW_REQUIRED | Any | Any | REQUIRED |
    | READY | CRITICAL | Any | REQUIRED |
    | READY | HIGH | PRODUCTION | REQUIRED |
    | READY | HIGH | STAGING/DEV/SANDBOX | OPTIONAL |
    | READY | MEDIUM | Any | OPTIONAL |
    | READY | LOW | Any | OPTIONAL |
    
    Args:
        readiness: ReadinessState from check_readiness
        context: HandoffContext with bug details
        
    Returns:
        HumanPresence
    """
    # HP-001: NOT_READY → BLOCKING
    if readiness == ReadinessState.NOT_READY:
        return HumanPresence.BLOCKING
    
    # HP-002: REVIEW_REQUIRED → REQUIRED
    if readiness == ReadinessState.REVIEW_REQUIRED:
        return HumanPresence.REQUIRED
    
    # Now readiness is READY_FOR_BROWSER
    
    # HP-003: CRITICAL → REQUIRED
    if context.severity == BugSeverity.CRITICAL:
        return HumanPresence.REQUIRED
    
    # HP-004: HIGH + PRODUCTION → REQUIRED
    if context.severity == BugSeverity.HIGH:
        if context.target_type == TargetType.PRODUCTION:
            return HumanPresence.REQUIRED
        # HP-005/006/007: HIGH + non-PRODUCTION → OPTIONAL
        return HumanPresence.OPTIONAL
    
    # HP-008: MEDIUM → OPTIONAL
    if context.severity == BugSeverity.MEDIUM:
        return HumanPresence.OPTIONAL
    
    # HP-009: LOW → OPTIONAL
    if context.severity == BugSeverity.LOW:
        return HumanPresence.OPTIONAL
    
    # Deny-by-default: Unknown → REQUIRED
    return HumanPresence.REQUIRED  # pragma: no cover


def is_blocked(context: HandoffContext) -> bool:
    """Check if handoff is blocked.
    
    Args:
        context: HandoffContext with bug details
        
    Returns:
        True if handoff is blocked
    """
    return context.has_active_blockers


def make_handoff_decision(context: HandoffContext) -> HandoffDecision:
    """Make complete handoff decision.
    
    Args:
        context: HandoffContext with bug details
        
    Returns:
        HandoffDecision with full evaluation
    """
    readiness = check_readiness(context)
    human_presence = determine_human_presence(readiness, context)
    blocked = is_blocked(context)
    
    # Determine blockers list
    blockers: list[str] = []
    if blocked:
        blockers.append("ACTIVE_BLOCKER")
    
    # Determine if can proceed
    can_proceed = False
    reason_code = "HD-001"
    reason_description = "Not ready"
    
    # HD-001: NOT_READY → cannot proceed
    if readiness == ReadinessState.NOT_READY:
        reason_code = "HD-001"
        reason_description = "Not ready - cannot proceed"
        can_proceed = False
    
    # HD-002: REVIEW_REQUIRED → cannot proceed
    elif readiness == ReadinessState.REVIEW_REQUIRED:
        reason_code = "HD-002"
        reason_description = "Review required - cannot proceed"
        can_proceed = False
    
    # HD-003: BLOCKING presence → cannot proceed
    # This is defensive - BLOCKING only occurs when NOT_READY, caught above
    elif human_presence == HumanPresence.BLOCKING:  # pragma: no cover
        reason_code = "HD-003"
        reason_description = "Human blocking - cannot proceed"
        can_proceed = False
    
    # HD-004: REQUIRED but not confirmed → cannot proceed
    elif human_presence == HumanPresence.REQUIRED and not context.human_confirmed:
        reason_code = "HD-004"
        reason_description = "Human required but not confirmed"
        can_proceed = False
    
    # HD-005: REQUIRED and confirmed → can proceed
    elif human_presence == HumanPresence.REQUIRED and context.human_confirmed:
        reason_code = "HD-005"
        reason_description = "Human confirmed - can proceed"
        can_proceed = True
    
    # HD-006: OPTIONAL → can proceed
    elif human_presence == HumanPresence.OPTIONAL:
        reason_code = "HD-006"
        reason_description = "Human optional - can proceed"
        can_proceed = True
    
    return HandoffDecision(
        bug_id=context.bug_id,
        readiness=readiness,
        human_presence=human_presence,
        can_proceed=can_proceed,
        is_blocked=not can_proceed,
        reason_code=reason_code,
        reason_description=reason_description,
        blockers=tuple(blockers)
    )
