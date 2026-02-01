"""
EvidenceStep enum - Phase-08 Evidence Orchestration.
REIMPLEMENTED-2026

Closed enum for evidence workflow steps.
"""

from enum import Enum


class EvidenceStep(Enum):
    """
    Closed enum representing evidence workflow steps.
    
    Steps:
        DISCOVERY: Initial bug discovery phase
        VALIDATION: Validation check phase
        DECISION: Decision made (allow/deny/escalate)
        EXPLANATION: Detailed explanation phase
        RECOMMENDATION: Final recommendation phase
    """
    DISCOVERY = "discovery"
    VALIDATION = "validation"
    DECISION = "decision"
    EXPLANATION = "explanation"
    RECOMMENDATION = "recommendation"
