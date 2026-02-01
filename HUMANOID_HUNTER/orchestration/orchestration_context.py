"""
Phase-25 Orchestration Context.

This module defines frozen dataclasses for orchestration binding.

All dataclasses are frozen=True (immutable).

THIS IS A POLICY LAYER ONLY.
IT DOES NOT EXECUTE ANYTHING.
"""
from dataclasses import dataclass
from typing import FrozenSet, Tuple, Optional

from .orchestration_types import OrchestrationIntentState, OrchestrationDecision

# Import Phase-24 types
from HUMANOID_HUNTER.planning import ExecutionPlan, PlanValidationResult


@dataclass(frozen=True)
class OrchestrationIntent:
    """Sealed orchestration intent.
    
    Immutable (frozen=True).
    
    Attributes:
        intent_id: Unique intent identifier
        execution_plan: Phase-24 ExecutionPlan
        capability_snapshot: Phase-19 capability snapshot
        evidence_requirements: Phase-23 evidence requirements
        created_at: Logical timestamp (not wall-clock)
        state: Intent state (DRAFT, SEALED, REJECTED)
    """
    intent_id: str
    execution_plan: ExecutionPlan
    capability_snapshot: FrozenSet
    evidence_requirements: FrozenSet
    created_at: str
    state: OrchestrationIntentState


@dataclass(frozen=True)
class OrchestrationContext:
    """Orchestration context for decisions.
    
    Immutable (frozen=True).
    
    Attributes:
        plan_validation_result: Phase-24 validation result
        human_present: Whether human is present
        prior_decisions: Prior orchestration decisions
    """
    plan_validation_result: PlanValidationResult
    human_present: bool
    prior_decisions: Tuple


@dataclass(frozen=True)
class OrchestrationResult:
    """Result of orchestration decision.
    
    Immutable (frozen=True).
    
    Attributes:
        decision: OrchestrationDecision (ACCEPT, REJECT)
        reason: Human-readable reason for decision
    """
    decision: OrchestrationDecision
    reason: str
