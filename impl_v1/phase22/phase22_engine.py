"""
impl_v1 Phase-22 Policy Constraint Engine.

NON-AUTHORITATIVE MIRROR of governance Phase-22.
Contains PURE VALIDATION FUNCTIONS ONLY.

THIS MODULE HAS NO EXECUTION AUTHORITY.
THIS MODULE NEVER ENFORCES POLICY.
THIS MODULE NEVER MUTATES STATE.
THIS MODULE ONLY VALIDATES POLICY CONSTRAINTS.

VALIDATION FUNCTIONS ONLY:
- validate_policy_id
- validate_policy_rule
- evaluate_policy_scope
- detect_policy_violation
- evaluate_policy
- get_policy_decision

INVARIANTS:
- Unknown policy → DENY
- Any violation → DENY
- Multiple violations → ESCALATE
- Default = DENY

DENY-BY-DEFAULT.
"""
import re
from typing import Optional, Tuple

from .phase22_types import (
    PolicyScope,
    PolicyViolation,
    PolicyDecision,
)
from .phase22_context import (
    PolicyRule,
    PolicyEvaluationContext,
    PolicyEvaluationResult,
)


# Regex pattern for valid policy ID
_POLICY_ID_PATTERN = re.compile(r'^POLICY-[a-fA-F0-9]{8,}$')


def validate_policy_id(policy_id: Optional[str]) -> bool:
    """Validate a policy ID format.
    
    Args:
        policy_id: Policy ID to validate
        
    Returns:
        True if valid, False otherwise
        
    Rules:
        - DENY-BY-DEFAULT
        - None → False
        - Empty → False
        - Invalid format → False
    """
    if policy_id is None:
        return False
    if not isinstance(policy_id, str):
        return False
    if not policy_id.strip():
        return False
    return bool(_POLICY_ID_PATTERN.match(policy_id))


def validate_policy_rule(rule: Optional[PolicyRule]) -> Tuple[bool, Tuple[str, ...]]:
    """Validate a policy rule.
    
    Args:
        rule: PolicyRule to validate
        
    Returns:
        Tuple of (is_valid, reasons)
        
    Rules:
        - DENY-BY-DEFAULT
        - None → False
        - Invalid ID → False
        - Invalid scope → False
        - Invalid severity → False
    """
    reasons: list[str] = []
    
    if rule is None:
        return False, ("Missing policy rule",)
    
    # Validate policy_id
    if not validate_policy_id(rule.policy_id):
        reasons.append("Invalid policy ID")
    
    # Validate scope
    if not isinstance(rule.scope, PolicyScope):
        reasons.append("Invalid policy scope")
    
    # Validate description
    if not rule.description or not isinstance(rule.description, str):
        reasons.append("Missing description")
    elif not rule.description.strip():
        reasons.append("Empty description")
    
    # Validate severity (1-10)
    if not isinstance(rule.severity, int):
        reasons.append("Invalid severity type")
    elif rule.severity < 1 or rule.severity > 10:
        reasons.append("Severity must be 1-10")
    
    return len(reasons) == 0, tuple(reasons)


def evaluate_policy_scope(
    context: Optional[PolicyEvaluationContext],
    rule: Optional[PolicyRule]
) -> bool:
    """Evaluate if context scope matches rule scope.
    
    Args:
        context: Evaluation context
        rule: Policy rule
        
    Returns:
        True if scopes match, False otherwise
        
    Rules:
        - DENY-BY-DEFAULT
        - None context → False
        - None rule → False
        - Scope mismatch → False
    """
    if context is None:
        return False
    if rule is None:
        return False
    if not isinstance(context.scope, PolicyScope):
        return False
    if not isinstance(rule.scope, PolicyScope):
        return False
    return context.scope == rule.scope


def detect_policy_violation(
    context: Optional[PolicyEvaluationContext],
    rule: Optional[PolicyRule]
) -> Tuple[PolicyViolation, ...]:
    """Detect policy violations.
    
    Args:
        context: Evaluation context
        rule: Policy rule
        
    Returns:
        Tuple of detected violations
        
    Rules:
        - DENY-BY-DEFAULT
        - None context → UNKNOWN_POLICY
        - None rule → UNKNOWN_POLICY
        - Scope mismatch → OUT_OF_SCOPE
        - Enforced + no conditions → CONDITION_UNMET
    """
    violations: list[PolicyViolation] = []
    
    if context is None:
        return (PolicyViolation.UNKNOWN_POLICY,)
    
    if rule is None:
        return (PolicyViolation.UNKNOWN_POLICY,)
    
    # Check scope match
    if not evaluate_policy_scope(context, rule):
        violations.append(PolicyViolation.OUT_OF_SCOPE)
    
    # Check conditions if rule is enforced
    if rule.enforced:
        if not context.conditions or len(context.conditions) == 0:
            violations.append(PolicyViolation.CONDITION_UNMET)
    
    # Check requested action
    if not context.requested_action or not isinstance(context.requested_action, str):
        violations.append(PolicyViolation.FORBIDDEN_ACTION)
    elif not context.requested_action.strip():
        violations.append(PolicyViolation.FORBIDDEN_ACTION)
    
    return tuple(violations)


def evaluate_policy(
    context: Optional[PolicyEvaluationContext],
    rule: Optional[PolicyRule]
) -> PolicyEvaluationResult:
    """Evaluate policy for context and rule.
    
    Args:
        context: Evaluation context
        rule: Policy rule
        
    Returns:
        PolicyEvaluationResult with decision
        
    Rules:
        - DENY-BY-DEFAULT
        - None context → DENY
        - None rule → DENY
        - Unknown policy → DENY
        - Any violation → DENY
        - Multiple violations → ESCALATE
        - All valid → ALLOW
    """
    # DENY-BY-DEFAULT: None context
    if context is None:
        return PolicyEvaluationResult(
            decision=PolicyDecision.DENY,
            violations=(PolicyViolation.UNKNOWN_POLICY,),
            reasons=("Missing evaluation context",)
        )
    
    # DENY-BY-DEFAULT: None rule
    if rule is None:
        return PolicyEvaluationResult(
            decision=PolicyDecision.DENY,
            violations=(PolicyViolation.UNKNOWN_POLICY,),
            reasons=("Missing policy rule",)
        )
    
    # Validate rule
    is_valid_rule, rule_reasons = validate_policy_rule(rule)
    if not is_valid_rule:
        return PolicyEvaluationResult(
            decision=PolicyDecision.DENY,
            violations=(PolicyViolation.UNKNOWN_POLICY,),
            reasons=rule_reasons
        )
    
    # Detect violations
    violations = detect_policy_violation(context, rule)
    
    if len(violations) == 0:
        # No violations → ALLOW
        return PolicyEvaluationResult(
            decision=PolicyDecision.ALLOW,
            violations=(),
            reasons=()
        )
    elif len(violations) == 1:
        # Single violation → DENY
        return PolicyEvaluationResult(
            decision=PolicyDecision.DENY,
            violations=violations,
            reasons=("Policy violation detected",)
        )
    else:
        # Multiple violations → ESCALATE
        return PolicyEvaluationResult(
            decision=PolicyDecision.ESCALATE,
            violations=violations,
            reasons=("Multiple policy violations - requires review",)
        )


def get_policy_decision(
    result: Optional[PolicyEvaluationResult]
) -> PolicyDecision:
    """Get policy decision from result.
    
    Args:
        result: PolicyEvaluationResult
        
    Returns:
        PolicyDecision
        
    Rules:
        - DENY-BY-DEFAULT
        - None → DENY
        - Invalid decision type → DENY
        - Valid → result's decision
    """
    if result is None:
        return PolicyDecision.DENY
    if not isinstance(result.decision, PolicyDecision):
        return PolicyDecision.DENY
    return result.decision
