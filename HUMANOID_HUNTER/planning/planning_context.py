"""
Phase-24 Planning Context.

This module defines frozen dataclasses for execution plans.

All dataclasses are frozen=True (immutable).

THIS IS A POLICY LAYER ONLY.
IT DOES NOT EXECUTE ANYTHING.
"""
from dataclasses import dataclass
from typing import FrozenSet

from .planning_types import PlannedActionType, PlanRiskLevel, PlanValidationDecision


@dataclass(frozen=True)
class ActionPlanStep:
    """Single action plan step.
    
    Immutable (frozen=True).
    
    Attributes:
        step_id: Unique step identifier
        action_type: Type of action (PlannedActionType)
        parameters: Action parameters (dict)
        risk_level: Risk level (PlanRiskLevel)
    """
    step_id: str
    action_type: PlannedActionType
    parameters: dict
    risk_level: PlanRiskLevel

    def __hash__(self):
        """Hash for frozen dataclass with dict field."""
        return hash((
            self.step_id,
            self.action_type,
            tuple(sorted(self.parameters.items())),
            self.risk_level
        ))


@dataclass(frozen=True)
class ExecutionPlan:
    """Complete execution plan.
    
    Immutable (frozen=True).
    
    Attributes:
        plan_id: Unique plan identifier
        steps: Tuple of ActionPlanStep (immutable)
    """
    plan_id: str
    steps: tuple  # tuple[ActionPlanStep, ...]


@dataclass(frozen=True)
class PlanValidationContext:
    """Validation context for plan decisions.
    
    Immutable (frozen=True).
    
    Attributes:
        plan: ExecutionPlan to validate
        allowed_capabilities: Frozenset of allowed PlannedActionType
        human_present: Whether a human is present for approval
    """
    plan: ExecutionPlan
    allowed_capabilities: FrozenSet[PlannedActionType]
    human_present: bool


@dataclass(frozen=True)
class PlanValidationResult:
    """Result of plan validation.
    
    Immutable (frozen=True).
    
    Attributes:
        decision: PlanValidationDecision (ACCEPT, REJECT, REQUIRES_HUMAN)
        max_risk: Maximum risk level in plan
        reason: Human-readable reason for decision
    """
    decision: PlanValidationDecision
    max_risk: PlanRiskLevel
    reason: str
