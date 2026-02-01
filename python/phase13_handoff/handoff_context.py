"""
Phase-13 Handoff Context.

This module defines frozen dataclasses for handoff data structures.

All dataclasses are frozen=True for immutability.
"""
from dataclasses import dataclass

from python.phase12_evidence.evidence_types import ConfidenceLevel, EvidenceState
from .handoff_types import BugSeverity, TargetType


@dataclass(frozen=True)
class HandoffContext:
    """Immutable context for handoff decision.
    
    Attributes:
        bug_id: Unique bug identifier
        confidence: ConfidenceLevel from Phase-12
        consistency_state: EvidenceState from Phase-12
        human_review_completed: Whether human has reviewed
        severity: Bug severity level
        target_type: Target environment type
        has_active_blockers: Whether blockers exist
        human_confirmed: Whether human has confirmed
    """
    bug_id: str
    confidence: ConfidenceLevel
    consistency_state: EvidenceState
    human_review_completed: bool
    severity: BugSeverity
    target_type: TargetType
    has_active_blockers: bool
    human_confirmed: bool
