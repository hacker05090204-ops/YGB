"""
Phase-26 Readiness Context.

This module defines frozen dataclasses for execution readiness.

All dataclasses are frozen=True (immutable).

THIS IS A POLICY LAYER ONLY.
IT DOES NOT EXECUTE ANYTHING.
"""
from dataclasses import dataclass
from typing import Optional

from .readiness_types import ExecutionReadinessState, ReadinessDecision

# Import Phase-25 types
from HUMANOID_HUNTER.orchestration import OrchestrationIntent


@dataclass(frozen=True)
class ReadinessContext:
    """Readiness context for pre-execution gatekeeping.
    
    Immutable (frozen=True).
    
    Aggregates results from prior phases:
    - Phase-19: capability_result_accepted
    - Phase-21: sandbox_policy_allows
    - Phase-22: native_policy_accepts
    - Phase-23: evidence_verification_passed
    - Phase-25: orchestration_intent
    
    Attributes:
        orchestration_intent: Phase-25 OrchestrationIntent (must be SEALED)
        capability_result_accepted: Phase-19 capability check passed
        sandbox_policy_allows: Phase-21 sandbox allows execution
        native_policy_accepts: Phase-22 native boundary accepts
        evidence_verification_passed: Phase-23 evidence verification passed
        human_present: Whether human is present for HIGH risk
    """
    orchestration_intent: Optional[OrchestrationIntent]
    capability_result_accepted: bool
    sandbox_policy_allows: bool
    native_policy_accepts: bool
    evidence_verification_passed: bool
    human_present: bool


@dataclass(frozen=True)
class ReadinessResult:
    """Result of readiness decision.
    
    Immutable (frozen=True).
    
    Attributes:
        decision: ReadinessDecision (ALLOW, BLOCK)
        state: ExecutionReadinessState (READY, NOT_READY)
        reason: Human-readable reason for decision
    """
    decision: ReadinessDecision
    state: ExecutionReadinessState
    reason: str
