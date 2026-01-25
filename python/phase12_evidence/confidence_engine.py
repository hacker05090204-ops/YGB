"""
Phase-12 Confidence Engine.

This module provides confidence level assignment logic.

All functions are pure (no side effects).
All dataclasses are frozen=True for immutability.
"""
from dataclasses import dataclass

from .evidence_types import EvidenceState, ConfidenceLevel
from .evidence_context import EvidenceBundle
from .consistency_engine import (
    ConsistencyResult,
    ReplayReadiness,
    check_consistency,
    check_replay_readiness
)


@dataclass(frozen=True)
class ConfidenceAssignment:
    """Immutable confidence level assignment.
    
    Attributes:
        bundle_id: Bundle that was evaluated
        level: Assigned confidence level
        consistency_state: State from consistency check
        is_replayable: From replay check
        reason_code: Machine-readable reason
        reason_description: Human-readable reason
        requires_human_review: Whether human must review
    """
    bundle_id: str
    level: ConfidenceLevel
    consistency_state: EvidenceState
    is_replayable: bool
    reason_code: str
    reason_description: str
    requires_human_review: bool


def assign_confidence(
    consistency: ConsistencyResult,
    replay: ReplayReadiness
) -> ConfidenceAssignment:
    """Assign confidence level based on consistency and replay.
    
    Decision table:
    | Consistency State | Replayable | → Confidence | Code | Human Review |
    |-------------------|------------|--------------|------|--------------|
    | UNVERIFIED | Any | LOW | CF-001 | YES |
    | RAW | NO | LOW | CF-002 | NO |
    | RAW | YES | MEDIUM | CF-003 | NO |
    | INCONSISTENT | Any | LOW | CF-004 | YES |
    | CONSISTENT | NO | MEDIUM | CF-005 | NO |
    | CONSISTENT | YES | HIGH | CF-006 | YES |
    | REPLAYABLE | YES | HIGH | CF-007 | YES |
    
    Args:
        consistency: ConsistencyResult from check_consistency
        replay: ReplayReadiness from check_replay_readiness
        
    Returns:
        ConfidenceAssignment with level and reason
    """
    state = consistency.state
    is_replayable = replay.is_replayable
    
    # CF-001: UNVERIFIED → LOW, needs human review
    if state == EvidenceState.UNVERIFIED:
        return ConfidenceAssignment(
            bundle_id=consistency.bundle_id,
            level=ConfidenceLevel.LOW,
            consistency_state=state,
            is_replayable=is_replayable,
            reason_code="CF-001",
            reason_description="Low confidence - unverified",
            requires_human_review=True
        )
    
    # CF-004: INCONSISTENT → LOW, needs human review
    if state == EvidenceState.INCONSISTENT:
        return ConfidenceAssignment(
            bundle_id=consistency.bundle_id,
            level=ConfidenceLevel.LOW,
            consistency_state=state,
            is_replayable=is_replayable,
            reason_code="CF-004",
            reason_description="Low confidence - inconsistent",
            requires_human_review=True
        )
    
    # CF-002/CF-003: RAW
    if state == EvidenceState.RAW:
        if is_replayable:
            # CF-003: RAW + replayable → MEDIUM
            return ConfidenceAssignment(
                bundle_id=consistency.bundle_id,
                level=ConfidenceLevel.MEDIUM,
                consistency_state=state,
                is_replayable=is_replayable,
                reason_code="CF-003",
                reason_description="Medium confidence - replayable raw",
                requires_human_review=False
            )
        else:
            # CF-002: RAW + not replayable → LOW
            return ConfidenceAssignment(
                bundle_id=consistency.bundle_id,
                level=ConfidenceLevel.LOW,
                consistency_state=state,
                is_replayable=is_replayable,
                reason_code="CF-002",
                reason_description="Low confidence - raw",
                requires_human_review=False
            )
    
    # CF-005/CF-006: CONSISTENT
    if state == EvidenceState.CONSISTENT:
        if is_replayable:
            # CF-006: CONSISTENT + replayable → HIGH
            return ConfidenceAssignment(
                bundle_id=consistency.bundle_id,
                level=ConfidenceLevel.HIGH,
                consistency_state=state,
                is_replayable=is_replayable,
                reason_code="CF-006",
                reason_description="High confidence - replayable",
                requires_human_review=True
            )
        else:
            # CF-005: CONSISTENT + not replayable → MEDIUM
            return ConfidenceAssignment(
                bundle_id=consistency.bundle_id,
                level=ConfidenceLevel.MEDIUM,
                consistency_state=state,
                is_replayable=is_replayable,
                reason_code="CF-005",
                reason_description="Medium confidence - consistent",
                requires_human_review=False
            )
    
    # CF-007: REPLAYABLE → HIGH
    if state == EvidenceState.REPLAYABLE:
        return ConfidenceAssignment(
            bundle_id=consistency.bundle_id,
            level=ConfidenceLevel.HIGH,
            consistency_state=state,
            is_replayable=True,
            reason_code="CF-007",
            reason_description="High confidence - fully verified",
            requires_human_review=True
        )
    
    # Deny-by-default: Unknown state → LOW with review
    # This is defensive code - all valid EvidenceState values are handled above
    return ConfidenceAssignment(  # pragma: no cover
        bundle_id=consistency.bundle_id,
        level=ConfidenceLevel.LOW,
        consistency_state=state,
        is_replayable=is_replayable,
        reason_code="CF-000",
        reason_description="Unknown state - denied",
        requires_human_review=True
    )


def evaluate_evidence(bundle: EvidenceBundle) -> ConfidenceAssignment:
    """Full evaluation: consistency + replay + confidence.
    
    This is the main entry point for evidence evaluation.
    
    Args:
        bundle: Evidence bundle to evaluate
        
    Returns:
        ConfidenceAssignment with full evaluation
    """
    consistency = check_consistency(bundle)
    replay = check_replay_readiness(bundle)
    return assign_confidence(consistency, replay)
