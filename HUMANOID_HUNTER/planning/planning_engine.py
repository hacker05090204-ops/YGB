"""
Phase-24 Planning Engine.

This module provides plan validation functions.

All functions are pure (no side effects).
All decisions are deny-by-default.

THIS IS A POLICY LAYER ONLY.
IT DOES NOT EXECUTE ANYTHING.

CORE RULES:
- Plans are immutable
- Plans cannot include forbidden actions
- HIGH-risk steps require human checkpoint
- CRITICAL-risk → REJECT always
- Unknown actions → REJECT
- Empty plan → REJECT
- Duplicate step IDs → REJECT
"""
from .planning_types import PlannedActionType, PlanRiskLevel, PlanValidationDecision
from .planning_context import (
    ActionPlanStep,
    ExecutionPlan,
    PlanValidationContext,
    PlanValidationResult
)


def validate_plan_structure(plan: ExecutionPlan) -> bool:
    """Validate plan structure.
    
    Args:
        plan: ExecutionPlan to validate
        
    Returns:
        True if structure is valid, False otherwise
        
    Rules:
        - Empty plan → False
        - Empty plan_id → False
        - Duplicate step IDs → False
    """
    # Empty plan_id → REJECT
    if not plan.plan_id:
        return False
    
    # Empty steps → REJECT
    if not plan.steps:
        return False
    
    # Check for duplicate step IDs
    step_ids = set()
    for step in plan.steps:
        if step.step_id in step_ids:
            return False  # Duplicate!
        step_ids.add(step.step_id)
    
    return True


def validate_plan_capabilities(
    plan: ExecutionPlan,
    allowed_capabilities: frozenset
) -> bool:
    """Validate plan capabilities against allowed actions.
    
    Args:
        plan: ExecutionPlan to validate
        allowed_capabilities: Frozenset of allowed PlannedActionType
        
    Returns:
        True if all actions are allowed, False otherwise
        
    Rules:
        - Any action not in allowed → False
        - Empty allowed set → False for any plan with steps
    """
    # Empty plan → trivially valid for capabilities
    if not plan.steps:
        return True
    
    # Check each step's action type
    for step in plan.steps:
        if step.action_type not in allowed_capabilities:
            return False
    
    return True


def validate_plan_risk(plan: ExecutionPlan) -> PlanRiskLevel:
    """Determine maximum risk level across plan steps.
    
    Args:
        plan: ExecutionPlan to analyze
        
    Returns:
        Maximum PlanRiskLevel found in plan
        
    Rules:
        - Empty plan → LOW (no risk, but will be rejected by structure)
        - Returns highest risk level found
    """
    if not plan.steps:
        return PlanRiskLevel.LOW
    
    max_risk = PlanRiskLevel.LOW
    
    for step in plan.steps:
        if step.risk_level.value > max_risk.value:
            max_risk = step.risk_level
    
    return max_risk


def decide_plan_acceptance(context: PlanValidationContext) -> PlanValidationResult:
    """Make final acceptance decision for plan.
    
    Args:
        context: PlanValidationContext with plan, capabilities, human_present
        
    Returns:
        PlanValidationResult with decision, max_risk, reason
        
    Decision Rules:
        1. Invalid structure → REJECT
        2. Forbidden action → REJECT
        3. CRITICAL risk → REJECT (always)
        4. HIGH risk + no human → REQUIRES_HUMAN
        5. HIGH risk + human → ACCEPT
        6. MEDIUM/LOW risk → ACCEPT
        
    DENY-BY-DEFAULT: If any condition is unclear → REJECT
    """
    plan = context.plan
    allowed = context.allowed_capabilities
    human_present = context.human_present
    
    # 1. Validate structure
    if not validate_plan_structure(plan):
        # Determine specific reason
        if not plan.plan_id:
            reason = "Empty plan_id"
        elif not plan.steps:
            reason = "Empty steps"
        else:
            reason = "Duplicate step IDs"
        
        return PlanValidationResult(
            decision=PlanValidationDecision.REJECT,
            max_risk=PlanRiskLevel.LOW,
            reason=reason
        )
    
    # 2. Validate capabilities
    if not validate_plan_capabilities(plan, allowed):
        # Find the first forbidden action
        forbidden_action = None
        for step in plan.steps:
            if step.action_type not in allowed:
                forbidden_action = step.action_type
                break
        
        return PlanValidationResult(
            decision=PlanValidationDecision.REJECT,
            max_risk=validate_plan_risk(plan),
            reason=f"Action {forbidden_action.name if forbidden_action else 'UNKNOWN'} not allowed"
        )
    
    # 3. Calculate max risk
    max_risk = validate_plan_risk(plan)
    
    # 4. CRITICAL → REJECT always
    if max_risk == PlanRiskLevel.CRITICAL:
        return PlanValidationResult(
            decision=PlanValidationDecision.REJECT,
            max_risk=max_risk,
            reason="CRITICAL risk - plan cannot be proven safe"
        )
    
    # 5. HIGH risk
    if max_risk == PlanRiskLevel.HIGH:
        if not human_present:
            return PlanValidationResult(
                decision=PlanValidationDecision.REQUIRES_HUMAN,
                max_risk=max_risk,
                reason="HIGH risk requires human approval"
            )
        else:
            return PlanValidationResult(
                decision=PlanValidationDecision.ACCEPT,
                max_risk=max_risk,
                reason="HIGH risk - human approved"
            )
    
    # 6. MEDIUM/LOW → ACCEPT
    return PlanValidationResult(
        decision=PlanValidationDecision.ACCEPT,
        max_risk=max_risk,
        reason=f"{max_risk.name} risk - plan accepted"
    )
