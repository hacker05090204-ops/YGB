"""
Decision Engine - Phase-06 Decision Aggregation.
REIMPLEMENTED-2026

Pure function for resolving final decisions.
No execution logic - decision resolution only.
"""

from python.phase02_actors.actors import ActorType
from python.phase03_trust.trust_zones import TrustZone
from python.phase04_validation.validation_results import ValidationResult
from python.phase05_workflow.states import is_terminal_state

from python.phase06_decision.decision_types import FinalDecision
from python.phase06_decision.decision_context import DecisionContext
from python.phase06_decision.decision_result import DecisionResult


def resolve_decision(context: DecisionContext) -> DecisionResult:
    """
    Resolve a final decision based on aggregated context.
    
    This function is PURE:
    - No side effects
    - No IO
    - No network
    - No state mutation
    - Deterministic output for same input
    
    Decision Priority Order:
    1. Terminal workflow state -> DENY (blocks everything)
    2. Workflow transition denied -> DENY
    3. HUMAN override with ALLOW validation -> ALLOW
    4. Validation ESCALATE -> ESCALATE
    5. Validation DENY -> DENY
    6. External zone -> ESCALATE
    7. All checks pass -> ALLOW
    8. Default -> DENY
    
    Args:
        context: Aggregated decision context
        
    Returns:
        DecisionResult with decision and reason
    """
    validation = context.validation_response
    transition = context.transition_response
    actor = context.actor_type
    zone = context.trust_zone
    
    # Priority 1: Terminal workflow state blocks ALL decisions (including HUMAN)
    current_state = transition.request.current_state
    if is_terminal_state(current_state):
        return DecisionResult(
            context=context,
            decision=FinalDecision.DENY,
            reason=f"Terminal workflow state {current_state.name}: no further decisions allowed"
        )
    
    # Priority 2: Workflow transition denied blocks all
    if not transition.allowed:
        return DecisionResult(
            context=context,
            decision=FinalDecision.DENY,
            reason=f"Workflow transition denied: {transition.reason}"
        )
    
    # Priority 3: HUMAN override with ALLOW
    if actor == ActorType.HUMAN and validation.result == ValidationResult.ALLOW:
        return DecisionResult(
            context=context,
            decision=FinalDecision.ALLOW,
            reason="HUMAN authority override: validation approved"
        )
    
    # Priority 4: Validation ESCALATE
    if validation.result == ValidationResult.ESCALATE:
        return DecisionResult(
            context=context,
            decision=FinalDecision.ESCALATE,
            reason=f"Validation requires escalation: {validation.reason}"
        )
    
    # Priority 5: Validation DENY
    if validation.result == ValidationResult.DENY:
        return DecisionResult(
            context=context,
            decision=FinalDecision.DENY,
            reason=f"Validation denied: {validation.reason}"
        )
    
    # Priority 6: External zone requires escalation
    if zone == TrustZone.EXTERNAL:
        return DecisionResult(
            context=context,
            decision=FinalDecision.ESCALATE,
            reason="External source requires human review"
        )
    
    # Priority 7: All checks pass (validation ALLOW + transition allowed)
    # This is the final valid path - all other cases have been handled above
    return DecisionResult(
        context=context,
        decision=FinalDecision.ALLOW,
        reason="All validation and workflow checks passed"
    )

