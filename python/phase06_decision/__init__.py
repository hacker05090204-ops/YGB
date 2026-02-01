"""
Phase-06: Decision Aggregation & Authority Resolution
REIMPLEMENTED-2026

Aggregates validation, workflow, actor, and trust zone inputs
into a single FinalDecision (ALLOW, DENY, ESCALATE).

No execution logic - decision recommendations only.

Exports:
    - FinalDecision: Enum of decision outcomes
    - DecisionContext: Frozen dataclass for input aggregation
    - DecisionResult: Frozen dataclass for decision output
    - resolve_decision: Pure function for decision resolution
"""

from python.phase06_decision.decision_types import FinalDecision
from python.phase06_decision.decision_context import DecisionContext
from python.phase06_decision.decision_result import DecisionResult
from python.phase06_decision.decision_engine import resolve_decision

__all__ = [
    "FinalDecision",
    "DecisionContext",
    "DecisionResult",
    "resolve_decision",
]
