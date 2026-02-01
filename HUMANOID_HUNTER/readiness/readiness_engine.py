"""
Phase-26 Readiness Engine.

This module provides execution readiness functions.

All functions are pure (no side effects).
All decisions are deny-by-default.

THIS IS A POLICY LAYER ONLY.
IT DOES NOT EXECUTE ANYTHING.

CORE RULES:
- Readiness decides IF execution may occur
- Execution never decides readiness
- Missing dependency → BLOCK
- Unsealed intent → BLOCK
- HIGH risk + no human → BLOCK
- Any ambiguity → BLOCK
"""
from .readiness_types import ExecutionReadinessState, ReadinessDecision
from .readiness_context import ReadinessContext, ReadinessResult

# Import Phase-25 types
from HUMANOID_HUNTER.orchestration import OrchestrationIntentState

# Import Phase-24 types
from HUMANOID_HUNTER.planning import PlanRiskLevel


def validate_readiness_inputs(context: ReadinessContext) -> bool:
    """Validate all readiness inputs are present and valid.
    
    Args:
        context: ReadinessContext with all dependency results
        
    Returns:
        True if all inputs are valid, False otherwise
        
    Rules:
        - None intent → False
        - Any dependency not accepted → False
    """
    # None intent → BLOCK
    if context.orchestration_intent is None:
        return False
    
    # Check all dependencies
    if not context.capability_result_accepted:
        return False
    
    if not context.sandbox_policy_allows:
        return False
    
    if not context.native_policy_accepts:
        return False
    
    if not context.evidence_verification_passed:
        return False
    
    return True


def evaluate_execution_readiness(context: ReadinessContext) -> ReadinessResult:
    """Evaluate if execution is ready.
    
    Args:
        context: ReadinessContext with all dependency results
        
    Returns:
        ReadinessResult with decision, state, and reason
        
    Rules:
        1. Invalid inputs → BLOCK
        2. Unsealed intent → BLOCK
        3. HIGH risk + no human → BLOCK
        4. All clear → ALLOW
    """
    # 1. Validate inputs
    if not validate_readiness_inputs(context):
        # Determine specific reason
        if context.orchestration_intent is None:
            reason = "Intent is None"
        elif not context.capability_result_accepted:
            reason = "Capability not accepted"
        elif not context.sandbox_policy_allows:
            reason = "Sandbox policy does not allow"
        elif not context.native_policy_accepts:
            reason = "Native policy does not accept"
        else:
            reason = "Evidence verification not passed"
        
        return ReadinessResult(
            decision=ReadinessDecision.BLOCK,
            state=ExecutionReadinessState.NOT_READY,
            reason=reason
        )
    
    intent = context.orchestration_intent
    
    # 2. Must be SEALED
    if intent.state != OrchestrationIntentState.SEALED:
        return ReadinessResult(
            decision=ReadinessDecision.BLOCK,
            state=ExecutionReadinessState.NOT_READY,
            reason=f"Intent not sealed (state: {intent.state.name})"
        )
    
    # 3. Check risk level - HIGH requires human
    max_risk = _get_max_risk_level(intent)
    if max_risk == PlanRiskLevel.HIGH and not context.human_present:
        return ReadinessResult(
            decision=ReadinessDecision.BLOCK,
            state=ExecutionReadinessState.NOT_READY,
            reason="HIGH risk requires human presence"
        )
    
    # 4. All checks passed → ALLOW
    return ReadinessResult(
        decision=ReadinessDecision.ALLOW,
        state=ExecutionReadinessState.READY,
        reason="Execution readiness confirmed"
    )


def _get_max_risk_level(intent) -> PlanRiskLevel:
    """Get maximum risk level from intent's execution plan.
    
    Args:
        intent: OrchestrationIntent
        
    Returns:
        Maximum PlanRiskLevel
    """
    plan = intent.execution_plan
    if not plan.steps:
        return PlanRiskLevel.LOW
    
    max_risk = PlanRiskLevel.LOW
    for step in plan.steps:
        if step.risk_level.value > max_risk.value:
            max_risk = step.risk_level
    
    return max_risk


def decide_readiness(context: ReadinessContext) -> ReadinessResult:
    """Make final readiness decision.
    
    Args:
        context: ReadinessContext with all dependency results
        
    Returns:
        ReadinessResult with decision, state, and reason
        
    DENY-BY-DEFAULT: Any unclear condition → BLOCK
    """
    return evaluate_execution_readiness(context)
