"""
EvidenceNarrative dataclass - Phase-08 Evidence Orchestration.
REIMPLEMENTED-2026

Frozen dataclass for evidence narratives with bilingual support.
"""

from dataclasses import dataclass

from python.phase06_decision.decision_types import FinalDecision
from python.phase07_knowledge.bug_types import BugType
from python.phase08_evidence.evidence_steps import EvidenceStep


@dataclass(frozen=True)
class EvidenceNarrative:
    """
    Frozen dataclass for evidence narratives.
    
    Composes decision results with bug knowledge into
    a structured bilingual narrative.
    """
    step: EvidenceStep
    decision: FinalDecision
    bug_type: BugType
    title_en: str
    title_hi: str
    summary_en: str
    summary_hi: str
    recommendation_en: str
    recommendation_hi: str
