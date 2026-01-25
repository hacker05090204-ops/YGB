"""
Phase-24 Execution Orchestration & Deterministic Action Planning.

This module provides execution plan governance.

THIS IS A POLICY LAYER ONLY.
IT DOES NOT EXECUTE BROWSERS.
IT DOES NOT INVOKE SUBPROCESSES.
IT DOES NOT MAKE NETWORK CALLS.

CORE PRINCIPLES:
- Planning is authority
- Execution is untrusted
- If a plan cannot be proven safe, it must never exist

Exports:
    Enums (CLOSED):
        PlannedActionType: CLICK, TYPE, NAVIGATE, WAIT, SCREENSHOT, SCROLL, UPLOAD
        PlanRiskLevel: LOW, MEDIUM, HIGH, CRITICAL
        PlanValidationDecision: ACCEPT, REJECT, REQUIRES_HUMAN
    
    Dataclasses (all frozen=True):
        ActionPlanStep: Single action step
        ExecutionPlan: Complete plan
        PlanValidationContext: Validation context
        PlanValidationResult: Validation result
    
    Functions (pure, deterministic):
        validate_plan_structure: Validate plan structure
        validate_plan_capabilities: Validate capabilities
        validate_plan_risk: Determine max risk
        decide_plan_acceptance: Make final decision
"""
from .planning_types import (
    PlannedActionType,
    PlanRiskLevel,
    PlanValidationDecision
)
from .planning_context import (
    ActionPlanStep,
    ExecutionPlan,
    PlanValidationContext,
    PlanValidationResult
)
from .planning_engine import (
    validate_plan_structure,
    validate_plan_capabilities,
    validate_plan_risk,
    decide_plan_acceptance
)

__all__ = [
    # Enums
    "PlannedActionType",
    "PlanRiskLevel",
    "PlanValidationDecision",
    # Dataclasses
    "ActionPlanStep",
    "ExecutionPlan",
    "PlanValidationContext",
    "PlanValidationResult",
    # Functions
    "validate_plan_structure",
    "validate_plan_capabilities",
    "validate_plan_risk",
    "decide_plan_acceptance",
]
