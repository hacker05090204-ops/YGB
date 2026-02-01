"""
impl_v1 Phase-21 System Invariant Engine.

NON-AUTHORITATIVE MIRROR of governance Phase-21.
Contains PURE VALIDATION FUNCTIONS ONLY.

THIS MODULE HAS NO EXECUTION AUTHORITY.
THIS MODULE NEVER ENFORCES INVARIANTS.
THIS MODULE NEVER MUTATES STATE.
THIS MODULE ONLY REPORTS INVARIANT STATUS.

VALIDATION FUNCTIONS ONLY:
- validate_invariant_id
- validate_system_invariant
- evaluate_invariant_scope
- detect_invariant_violation
- evaluate_invariants
- get_invariant_decision

INVARIANTS:
- Unknown invariant → FAIL
- Any violation → FAIL
- Multiple violations → ESCALATE
- Default = FAIL

DENY-BY-DEFAULT.
"""
import re
from typing import Optional, Tuple

from .phase21_types import (
    InvariantScope,
    InvariantViolation,
    InvariantDecision,
)
from .phase21_context import (
    SystemInvariant,
    InvariantEvaluationContext,
    InvariantEvaluationResult,
)


# Regex pattern for valid invariant ID
_INVARIANT_ID_PATTERN = re.compile(r'^INVARIANT-[a-fA-F0-9]{8,}$')


def validate_invariant_id(invariant_id: Optional[str]) -> bool:
    """Validate an invariant ID format.
    
    Args:
        invariant_id: Invariant ID to validate
        
    Returns:
        True if valid, False otherwise
        
    Rules:
        - DENY-BY-DEFAULT
        - None → False
        - Empty → False
        - Invalid format → False
    """
    if invariant_id is None:
        return False
    if not isinstance(invariant_id, str):
        return False
    if not invariant_id.strip():
        return False
    return bool(_INVARIANT_ID_PATTERN.match(invariant_id))


def validate_system_invariant(invariant: Optional[SystemInvariant]) -> Tuple[bool, Tuple[str, ...]]:
    """Validate a system invariant.
    
    Args:
        invariant: SystemInvariant to validate
        
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
    
    if invariant is None:
        return False, ("Missing system invariant",)
    
    # Validate invariant_id
    if not validate_invariant_id(invariant.invariant_id):
        reasons.append("Invalid invariant ID")
    
    # Validate scope
    if not isinstance(invariant.scope, InvariantScope):
        reasons.append("Invalid invariant scope")
    
    # Validate description
    if not invariant.description or not isinstance(invariant.description, str):
        reasons.append("Missing description")
    elif not invariant.description.strip():
        reasons.append("Empty description")
    
    # Validate severity (1-10)
    if not isinstance(invariant.severity, int):
        reasons.append("Invalid severity type")
    elif invariant.severity < 1 or invariant.severity > 10:
        reasons.append("Severity must be 1-10")
    
    return len(reasons) == 0, tuple(reasons)


def evaluate_invariant_scope(
    context: Optional[InvariantEvaluationContext],
    invariant: Optional[SystemInvariant]
) -> bool:
    """Evaluate if context scope matches invariant scope.
    
    Args:
        context: Evaluation context
        invariant: System invariant
        
    Returns:
        True if scopes match or invariant is GLOBAL, False otherwise
        
    Rules:
        - DENY-BY-DEFAULT
        - None context → False
        - None invariant → False
        - GLOBAL scope → True (matches all)
        - Scope mismatch → False
    """
    if context is None:
        return False
    if invariant is None:
        return False
    if not isinstance(context.scope, InvariantScope):
        return False
    if not isinstance(invariant.scope, InvariantScope):
        return False
    # GLOBAL scope matches all
    if invariant.scope == InvariantScope.GLOBAL:
        return True
    return context.scope == invariant.scope


def detect_invariant_violation(
    context: Optional[InvariantEvaluationContext],
    invariant: Optional[SystemInvariant]
) -> Tuple[InvariantViolation, ...]:
    """Detect invariant violations.
    
    Args:
        context: Evaluation context
        invariant: System invariant
        
    Returns:
        Tuple of detected violations
        
    Rules:
        - DENY-BY-DEFAULT
        - None context → UNKNOWN_INVARIANT
        - None invariant → UNKNOWN_INVARIANT
        - Scope mismatch → STATE_INCONSISTENT
        - Enforced + no state → MISSING_PRECONDITION
        - Enforced + no prior → BROKEN_CHAIN
    """
    violations: list[InvariantViolation] = []
    
    if context is None:
        return (InvariantViolation.UNKNOWN_INVARIANT,)
    
    if invariant is None:
        return (InvariantViolation.UNKNOWN_INVARIANT,)
    
    # Check scope match
    if not evaluate_invariant_scope(context, invariant):
        violations.append(InvariantViolation.STATE_INCONSISTENT)
    
    # Check observed state if invariant is enforced
    if invariant.enforced:
        if not context.observed_state or len(context.observed_state) == 0:
            violations.append(InvariantViolation.MISSING_PRECONDITION)
        if not context.prior_results or len(context.prior_results) == 0:
            violations.append(InvariantViolation.BROKEN_CHAIN)
    
    return tuple(violations)


def evaluate_invariants(
    context: Optional[InvariantEvaluationContext],
    invariant: Optional[SystemInvariant]
) -> InvariantEvaluationResult:
    """Evaluate invariants for context.
    
    Args:
        context: Evaluation context
        invariant: System invariant
        
    Returns:
        InvariantEvaluationResult with decision
        
    Rules:
        - DENY-BY-DEFAULT → FAIL
        - None context → FAIL
        - None invariant → FAIL
        - Unknown invariant → FAIL
        - Any violation → FAIL
        - Multiple violations → ESCALATE
        - All valid → PASS
    """
    # DENY-BY-DEFAULT: None context
    if context is None:
        return InvariantEvaluationResult(
            decision=InvariantDecision.FAIL,
            violations=(InvariantViolation.UNKNOWN_INVARIANT,),
            reasons=("Missing evaluation context",)
        )
    
    # DENY-BY-DEFAULT: None invariant
    if invariant is None:
        return InvariantEvaluationResult(
            decision=InvariantDecision.FAIL,
            violations=(InvariantViolation.UNKNOWN_INVARIANT,),
            reasons=("Missing system invariant",)
        )
    
    # Validate invariant
    is_valid, reasons = validate_system_invariant(invariant)
    if not is_valid:
        return InvariantEvaluationResult(
            decision=InvariantDecision.FAIL,
            violations=(InvariantViolation.UNKNOWN_INVARIANT,),
            reasons=reasons
        )
    
    # Detect violations
    violations = detect_invariant_violation(context, invariant)
    
    if len(violations) == 0:
        # No violations → PASS
        return InvariantEvaluationResult(
            decision=InvariantDecision.PASS,
            violations=(),
            reasons=()
        )
    elif len(violations) == 1:
        # Single violation → FAIL
        return InvariantEvaluationResult(
            decision=InvariantDecision.FAIL,
            violations=violations,
            reasons=("Invariant violation detected",)
        )
    else:
        # Multiple violations → ESCALATE
        return InvariantEvaluationResult(
            decision=InvariantDecision.ESCALATE,
            violations=violations,
            reasons=("Multiple invariant violations - requires review",)
        )


def get_invariant_decision(
    result: Optional[InvariantEvaluationResult]
) -> InvariantDecision:
    """Get invariant decision from result.
    
    Args:
        result: InvariantEvaluationResult
        
    Returns:
        InvariantDecision
        
    Rules:
        - DENY-BY-DEFAULT → FAIL
        - None → FAIL
        - Invalid decision type → FAIL
        - Valid → result's decision
    """
    if result is None:
        return InvariantDecision.FAIL
    if not isinstance(result.decision, InvariantDecision):
        return InvariantDecision.FAIL
    return result.decision
