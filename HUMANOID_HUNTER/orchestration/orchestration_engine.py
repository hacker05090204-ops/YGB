"""
Phase-25 Orchestration Engine.

This module provides orchestration binding functions.

All functions are pure (no side effects).
All decisions are deny-by-default.

THIS IS A POLICY LAYER ONLY.
IT DOES NOT EXECUTE ANYTHING.

CORE RULES:
- Orchestration binds plans to intent
- Once sealed, intent is immutable
- Missing evidence → REJECT
- Missing human for HIGH risk → REJECT
- Unknown input → REJECT
"""
from typing import Optional, FrozenSet

from .orchestration_types import OrchestrationIntentState, OrchestrationDecision
from .orchestration_context import (
    OrchestrationIntent,
    OrchestrationContext,
    OrchestrationResult
)

# Import Phase-24 types
from HUMANOID_HUNTER.planning import (
    ExecutionPlan,
    PlanValidationResult,
    PlanValidationDecision,
    PlanRiskLevel
)


def bind_plan_to_intent(
    plan: ExecutionPlan,
    validation_result: PlanValidationResult,
    capability_snapshot: FrozenSet,
    evidence_requirements: FrozenSet,
    intent_id: str,
    created_at: str
) -> Optional[OrchestrationIntent]:
    """Bind a validated plan to an orchestration intent.
    
    Args:
        plan: Phase-24 ExecutionPlan
        validation_result: Phase-24 validation result
        capability_snapshot: Phase-19 capability snapshot
        evidence_requirements: Phase-23 evidence requirements
        intent_id: Unique intent identifier
        created_at: Logical timestamp
        
    Returns:
        OrchestrationIntent in DRAFT state, or None if plan not ACCEPTED
        
    Rules:
        - Only ACCEPTED plans can be bound
        - REJECTED or REQUIRES_HUMAN → return None
    """
    # Only ACCEPTED plans can be bound
    if validation_result.decision != PlanValidationDecision.ACCEPT:
        return None
    
    return OrchestrationIntent(
        intent_id=intent_id,
        execution_plan=plan,
        capability_snapshot=capability_snapshot,
        evidence_requirements=evidence_requirements,
        created_at=created_at,
        state=OrchestrationIntentState.DRAFT
    )


def seal_orchestration_intent(
    intent: Optional[OrchestrationIntent]
) -> Optional[OrchestrationIntent]:
    """Seal an orchestration intent.
    
    Args:
        intent: OrchestrationIntent to seal
        
    Returns:
        New OrchestrationIntent with SEALED state, or None if cannot seal
        
    Rules:
        - None → None
        - DRAFT → SEALED
        - SEALED → same intent (already sealed)
        - REJECTED → None
    """
    if intent is None:
        return None
    
    if intent.state == OrchestrationIntentState.REJECTED:
        return None
    
    if intent.state == OrchestrationIntentState.SEALED:
        return intent
    
    # Create new sealed intent (dataclass is frozen)
    return OrchestrationIntent(
        intent_id=intent.intent_id,
        execution_plan=intent.execution_plan,
        capability_snapshot=intent.capability_snapshot,
        evidence_requirements=intent.evidence_requirements,
        created_at=intent.created_at,
        state=OrchestrationIntentState.SEALED
    )


def decide_orchestration(
    intent: Optional[OrchestrationIntent],
    context: OrchestrationContext
) -> OrchestrationResult:
    """Make orchestration decision.
    
    Args:
        intent: Sealed OrchestrationIntent
        context: OrchestrationContext with validation result, human presence
        
    Returns:
        OrchestrationResult with decision and reason
        
    Decision Rules:
        1. None intent → REJECT
        2. Not SEALED → REJECT
        3. Empty evidence requirements → REJECT
        4. HIGH risk + no human → REJECT
        5. Otherwise → ACCEPT
        
    DENY-BY-DEFAULT: Any unclear condition → REJECT
    """
    # 1. None intent → REJECT
    if intent is None:
        return OrchestrationResult(
            decision=OrchestrationDecision.REJECT,
            reason="Intent is None"
        )
    
    # 2. Not SEALED → REJECT
    if intent.state != OrchestrationIntentState.SEALED:
        return OrchestrationResult(
            decision=OrchestrationDecision.REJECT,
            reason=f"Intent not sealed (state: {intent.state.name})"
        )
    
    # 3. Empty evidence requirements → REJECT
    if not intent.evidence_requirements:
        return OrchestrationResult(
            decision=OrchestrationDecision.REJECT,
            reason="Evidence requirements are empty"
        )
    
    # 4. HIGH risk + no human → REJECT
    plan_result = context.plan_validation_result
    if plan_result.max_risk == PlanRiskLevel.HIGH and not context.human_present:
        return OrchestrationResult(
            decision=OrchestrationDecision.REJECT,
            reason="HIGH risk requires human presence"
        )
    
    # 5. All checks passed → ACCEPT
    return OrchestrationResult(
        decision=OrchestrationDecision.ACCEPT,
        reason="Orchestration accepted"
    )
