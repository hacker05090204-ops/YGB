"""
DecisionResult dataclass - Phase-06 Decision Aggregation.
REIMPLEMENTED-2026

Frozen dataclass representing the result of decision resolution.
No execution logic - result only.
"""

from dataclasses import dataclass

from python.phase06_decision.decision_types import FinalDecision
from python.phase06_decision.decision_context import DecisionContext


@dataclass(frozen=True)
class DecisionResult:
    """
    Immutable result of decision resolution.
    
    Attributes:
        context: The original decision context
        decision: The final decision (ALLOW, DENY, or ESCALATE)
        reason: Non-empty explanation for the decision
    """
    context: DecisionContext
    decision: FinalDecision
    reason: str
