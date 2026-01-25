"""
Phase-12 Evidence Consistency, Replay & Confidence Governance.

This module provides backend governance logic for:
- Evidence consistency verification
- Replay readiness assessment
- Confidence level assignment

This is a PURE BACKEND module - NO browser, NO execution.

Exports:
    Enums:
        EvidenceState: Evidence state (RAW, CONSISTENT, INCONSISTENT, REPLAYABLE, UNVERIFIED)
        ConfidenceLevel: Confidence level (LOW, MEDIUM, HIGH)
    
    Dataclasses (all frozen=True):
        EvidenceSource: Single evidence source
        EvidenceBundle: Bundle of evidence sources
        ConsistencyResult: Result of consistency check
        ReplayReadiness: Result of replay check
        ConfidenceAssignment: Assigned confidence with reasons
    
    Functions:
        check_consistency: Check evidence consistency
        check_replay_readiness: Check replay readiness
        sources_match: Check if sources match
        assign_confidence: Assign confidence level
        evaluate_evidence: Full evaluation pipeline
"""
from .evidence_types import EvidenceState, ConfidenceLevel
from .evidence_context import EvidenceSource, EvidenceBundle
from .consistency_engine import (
    ConsistencyResult,
    ReplayReadiness,
    check_consistency,
    check_replay_readiness,
    sources_match
)
from .confidence_engine import (
    ConfidenceAssignment,
    assign_confidence,
    evaluate_evidence
)

__all__ = [
    # Enums
    "EvidenceState",
    "ConfidenceLevel",
    # Dataclasses
    "EvidenceSource",
    "EvidenceBundle",
    "ConsistencyResult",
    "ReplayReadiness",
    "ConfidenceAssignment",
    # Functions
    "check_consistency",
    "check_replay_readiness",
    "sources_match",
    "assign_confidence",
    "evaluate_evidence",
]
