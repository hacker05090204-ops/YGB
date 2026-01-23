"""
Phase-08: Evidence & Explanation Orchestration Layer
REIMPLEMENTED-2026

Composes decision results (Phase-06) with bug knowledge (Phase-07)
into structured bilingual evidence narratives.

No execution logic - narrative composition only.

Exports:
    - EvidenceStep: Enum of workflow steps
    - EvidenceNarrative: Frozen dataclass for narratives
    - compose_narrative: Compose decision + knowledge into narrative
    - get_recommendation: Get bilingual recommendations
"""

from python.phase08_evidence.evidence_steps import EvidenceStep
from python.phase08_evidence.narrative import EvidenceNarrative
from python.phase08_evidence.composer import compose_narrative, get_recommendation

__all__ = [
    "EvidenceStep",
    "EvidenceNarrative",
    "compose_narrative",
    "get_recommendation",
]
