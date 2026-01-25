"""
Phase-19 Capability Engine.

This module provides capability governance functions.

All functions are pure (no side effects).
All decisions are deny-by-default.

THIS IS A POLICY LAYER ONLY.
IT DOES NOT EXECUTE ANYTHING.
"""
from .capability_types import (
    BrowserActionType,
    ActionRiskLevel,
    CapabilityDecision,
    DEFAULT_RISK_CLASSIFICATION,
    FORBIDDEN_ACTIONS,
    VALID_EXECUTION_STATES,
    TERMINAL_STATES
)
from .capability_context import (
    BrowserCapabilityPolicy,
    ActionRequestContext,
    CapabilityDecisionResult
)


def classify_action_risk(action_type: BrowserActionType) -> ActionRiskLevel:
    """Classify action risk level.
    
    Args:
        action_type: The browser action type
        
    Returns:
        ActionRiskLevel for the action
    """
    return DEFAULT_RISK_CLASSIFICATION.get(action_type, ActionRiskLevel.FORBIDDEN)


def is_action_allowed(
    action_type: BrowserActionType,
    policy: BrowserCapabilityPolicy
) -> bool:
    """Check if action is allowed by policy.
    
    Args:
        action_type: The action type
        policy: The capability policy
        
    Returns:
        True if action is in policy's allowed_actions
    """
    return action_type in policy.allowed_actions


def validate_action_against_policy(
    action_type: BrowserActionType,
    policy: BrowserCapabilityPolicy,
    execution_state: str
) -> bool:
    """Validate action against policy and state.
    
    Args:
        action_type: The action type
        policy: The capability policy
        execution_state: Current execution state
        
    Returns:
        True if action is valid
    """
    # Terminal states → denied
    if execution_state in TERMINAL_STATES:
        return False
    
    # Forbidden actions → always denied
    if action_type in FORBIDDEN_ACTIONS:
        return False
    
    # Action must be in policy
    if action_type not in policy.allowed_actions:
        return False
    
    return True


def decide_capability(context: ActionRequestContext) -> CapabilityDecisionResult:
    """Decide capability for action request.
    
    Args:
        context: Action request context
        
    Returns:
        CapabilityDecisionResult
    """
    action_type = context.action_type
    execution_state = context.execution_state
    risk_level = classify_action_risk(action_type)
    
    # FORBIDDEN actions → always DENIED
    if risk_level == ActionRiskLevel.FORBIDDEN:
        return CapabilityDecisionResult(
            decision=CapabilityDecision.DENIED,
            reason_code="CAP-001",
            reason_description=f"Action {action_type.name} is FORBIDDEN",
            action_type=action_type,
            risk_level=risk_level
        )
    
    # COMPLETED state → DENIED
    if execution_state == "COMPLETED":
        return CapabilityDecisionResult(
            decision=CapabilityDecision.DENIED,
            reason_code="CAP-002",
            reason_description="Execution is COMPLETED",
            action_type=action_type,
            risk_level=risk_level
        )
    
    # ESCALATED state → HUMAN_REQUIRED
    if execution_state == "ESCALATED":
        return CapabilityDecisionResult(
            decision=CapabilityDecision.HUMAN_REQUIRED,
            reason_code="CAP-003",
            reason_description="Execution is ESCALATED",
            action_type=action_type,
            risk_level=risk_level
        )
    
    # Unknown state → DENIED
    if execution_state not in VALID_EXECUTION_STATES:
        return CapabilityDecisionResult(
            decision=CapabilityDecision.DENIED,
            reason_code="CAP-004",
            reason_description=f"Unknown state: {execution_state}",
            action_type=action_type,
            risk_level=risk_level
        )
    
    # HIGH risk → HUMAN_REQUIRED
    if risk_level == ActionRiskLevel.HIGH:
        return CapabilityDecisionResult(
            decision=CapabilityDecision.HUMAN_REQUIRED,
            reason_code="CAP-005",
            reason_description=f"HIGH risk action: {action_type.name}",
            action_type=action_type,
            risk_level=risk_level
        )
    
    # MEDIUM risk → ALLOWED (with validation context)
    if risk_level == ActionRiskLevel.MEDIUM:
        return CapabilityDecisionResult(
            decision=CapabilityDecision.ALLOWED,
            reason_code="CAP-OK",
            reason_description=f"MEDIUM risk action allowed: {action_type.name}",
            action_type=action_type,
            risk_level=risk_level
        )
    
    # LOW risk → ALLOWED
    # Note: All ActionRiskLevel values are covered above
    # This branch handles LOW risk (the only remaining case)
    return CapabilityDecisionResult(
        decision=CapabilityDecision.ALLOWED,
        reason_code="CAP-OK",
        reason_description=f"LOW risk action allowed: {action_type.name}",
        action_type=action_type,
        risk_level=risk_level
    )
