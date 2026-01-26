"""
impl_v1 Phase-20 System Root Boundary Engine.

NON-AUTHORITATIVE MIRROR of governance Phase-20.
Contains PURE VALIDATION FUNCTIONS ONLY.

THIS MODULE HAS NO EXECUTION AUTHORITY.
THIS MODULE NEVER ENFORCES BOUNDARIES.
THIS MODULE NEVER MUTATES STATE.
THIS MODULE ONLY REPORTS BOUNDARY VALIDITY.

PHASE-20 IS THE ABSOLUTE ROOT BOUNDARY.
NOTHING EXISTS BELOW IT.
NOTHING BYPASSES IT.

VALIDATION FUNCTIONS ONLY:
- validate_boundary_id
- validate_system_boundary
- validate_layer_transition
- detect_boundary_violation
- evaluate_system_boundary
- get_boundary_decision

CORE RULES:
- ROOT layer is immutable
- Any bypass attempt → DENY
- Unknown layer → DENY
- Invalid order → DENY
- Multiple violations → ESCALATE
- Default = DENY

DENY-BY-DEFAULT.
"""
import re
from typing import Optional, Tuple

from .phase20_types import (
    SystemLayer,
    BoundaryViolation,
    BoundaryDecision,
)
from .phase20_context import (
    SystemBoundary,
    BoundaryEvaluationContext,
    BoundaryEvaluationResult,
)


# Regex pattern for valid boundary ID
_BOUNDARY_ID_PATTERN = re.compile(r'^BOUNDARY-[a-fA-F0-9]{8,}$')

# Layer order (from ROOT to HUMAN)
_LAYER_ORDER = (
    SystemLayer.ROOT,
    SystemLayer.GOVERNANCE,
    SystemLayer.EXECUTION,
    SystemLayer.OBSERVATION,
    SystemLayer.HUMAN,
)


def validate_boundary_id(boundary_id: Optional[str]) -> bool:
    """Validate a boundary ID format.
    
    Args:
        boundary_id: Boundary ID to validate
        
    Returns:
        True if valid, False otherwise
        
    Rules:
        - DENY-BY-DEFAULT
        - None → False
        - Empty → False
        - Invalid format → False
    """
    if boundary_id is None:
        return False
    if not isinstance(boundary_id, str):
        return False
    if not boundary_id.strip():
        return False
    return bool(_BOUNDARY_ID_PATTERN.match(boundary_id))


def validate_system_boundary(boundary: Optional[SystemBoundary]) -> Tuple[bool, Tuple[str, ...]]:
    """Validate a system boundary.
    
    Args:
        boundary: SystemBoundary to validate
        
    Returns:
        Tuple of (is_valid, reasons)
        
    Rules:
        - DENY-BY-DEFAULT
        - None → False
        - Invalid ID → False
        - Invalid layer → False
        - ROOT must be immutable
    """
    reasons: list[str] = []
    
    if boundary is None:
        return False, ("Missing system boundary",)
    
    # Validate boundary_id
    if not validate_boundary_id(boundary.boundary_id):
        reasons.append("Invalid boundary ID")
    
    # Validate layer
    if not isinstance(boundary.layer, SystemLayer):
        reasons.append("Invalid system layer")
    
    # Validate description
    if not boundary.description or not isinstance(boundary.description, str):
        reasons.append("Missing description")
    elif not boundary.description.strip():
        reasons.append("Empty description")
    
    # ROOT layer MUST be immutable
    if isinstance(boundary.layer, SystemLayer) and boundary.layer == SystemLayer.ROOT:
        if not boundary.immutable:
            reasons.append("ROOT layer must be immutable")
    
    return len(reasons) == 0, tuple(reasons)


def validate_layer_transition(
    current: Optional[SystemLayer],
    requested: Optional[SystemLayer]
) -> Tuple[bool, BoundaryViolation]:
    """Validate a layer transition.
    
    Args:
        current: Current layer
        requested: Requested layer
        
    Returns:
        Tuple of (is_valid, violation if invalid)
        
    Rules:
        - DENY-BY-DEFAULT
        - None → UNKNOWN_LAYER
        - Invalid type → UNKNOWN_LAYER
        - Transition TO ROOT → BYPASS_ATTEMPT
        - Out of order transition → ORDER_BREACH
        - Valid transition → True
    """
    if current is None:
        return False, BoundaryViolation.UNKNOWN_LAYER
    if requested is None:
        return False, BoundaryViolation.UNKNOWN_LAYER
    if not isinstance(current, SystemLayer):
        return False, BoundaryViolation.UNKNOWN_LAYER
    if not isinstance(requested, SystemLayer):
        return False, BoundaryViolation.UNKNOWN_LAYER
    
    # Transition TO ROOT is always a bypass attempt
    if requested == SystemLayer.ROOT and current != SystemLayer.ROOT:
        return False, BoundaryViolation.BYPASS_ATTEMPT
    
    # Check layer order - safe, all SystemLayer members are in _LAYER_ORDER
    current_idx = _LAYER_ORDER.index(current)
    requested_idx = _LAYER_ORDER.index(requested)
    
    # Cannot skip layers (must be adjacent or same)
    if abs(current_idx - requested_idx) > 1:
        return False, BoundaryViolation.ORDER_BREACH
    
    return True, BoundaryViolation.UNKNOWN_LAYER  # Placeholder, not used


def detect_boundary_violation(
    context: Optional[BoundaryEvaluationContext],
    boundary: Optional[SystemBoundary]
) -> Tuple[BoundaryViolation, ...]:
    """Detect boundary violations.
    
    Args:
        context: Evaluation context
        boundary: System boundary
        
    Returns:
        Tuple of detected violations
        
    Rules:
        - DENY-BY-DEFAULT
        - None context → UNDEFINED_ROOT
        - None boundary → UNDEFINED_ROOT
        - Invalid transition → detected violation
        - Enforced + bypass → BYPASS_ATTEMPT
    """
    violations: list[BoundaryViolation] = []
    
    if context is None:
        return (BoundaryViolation.UNDEFINED_ROOT,)
    
    if boundary is None:
        return (BoundaryViolation.UNDEFINED_ROOT,)
    
    # Validate layer transition
    is_valid, violation = validate_layer_transition(
        context.current_layer,
        context.requested_layer
    )
    if not is_valid:
        violations.append(violation)
    
    # Check boundary enforcement
    if boundary.enforced:
        # If trying to transition away from ROOT, it's a bypass attempt
        if context.current_layer == SystemLayer.ROOT:
            if context.requested_layer != SystemLayer.ROOT:
                if BoundaryViolation.BYPASS_ATTEMPT not in violations:
                    violations.append(BoundaryViolation.BYPASS_ATTEMPT)
    
    return tuple(violations)


def evaluate_system_boundary(
    context: Optional[BoundaryEvaluationContext],
    boundary: Optional[SystemBoundary]
) -> BoundaryEvaluationResult:
    """Evaluate system boundary.
    
    Args:
        context: Evaluation context
        boundary: System boundary
        
    Returns:
        BoundaryEvaluationResult with decision
        
    Rules:
        - DENY-BY-DEFAULT
        - None context → DENY
        - None boundary → DENY
        - Invalid boundary → DENY
        - Any violation → DENY
        - Multiple violations → ESCALATE
        - All valid → ALLOW
    """
    # DENY-BY-DEFAULT: None context
    if context is None:
        return BoundaryEvaluationResult(
            decision=BoundaryDecision.DENY,
            violations=(BoundaryViolation.UNDEFINED_ROOT,),
            reasons=("Missing evaluation context",)
        )
    
    # DENY-BY-DEFAULT: None boundary
    if boundary is None:
        return BoundaryEvaluationResult(
            decision=BoundaryDecision.DENY,
            violations=(BoundaryViolation.UNDEFINED_ROOT,),
            reasons=("Missing system boundary",)
        )
    
    # Validate boundary
    is_valid, reasons = validate_system_boundary(boundary)
    if not is_valid:
        return BoundaryEvaluationResult(
            decision=BoundaryDecision.DENY,
            violations=(BoundaryViolation.UNDEFINED_ROOT,),
            reasons=reasons
        )
    
    # Detect violations
    violations = detect_boundary_violation(context, boundary)
    
    if len(violations) == 0:
        # No violations → ALLOW
        return BoundaryEvaluationResult(
            decision=BoundaryDecision.ALLOW,
            violations=(),
            reasons=()
        )
    elif len(violations) == 1:
        # Single violation → DENY
        return BoundaryEvaluationResult(
            decision=BoundaryDecision.DENY,
            violations=violations,
            reasons=("Boundary violation detected",)
        )
    else:
        # Multiple violations → ESCALATE
        return BoundaryEvaluationResult(
            decision=BoundaryDecision.ESCALATE,
            violations=violations,
            reasons=("Multiple boundary violations - requires review",)
        )


def get_boundary_decision(
    result: Optional[BoundaryEvaluationResult]
) -> BoundaryDecision:
    """Get boundary decision from result.
    
    Args:
        result: BoundaryEvaluationResult
        
    Returns:
        BoundaryDecision
        
    Rules:
        - DENY-BY-DEFAULT
        - None → DENY
        - Invalid decision type → DENY
        - Valid → result's decision
    """
    if result is None:
        return BoundaryDecision.DENY
    if not isinstance(result.decision, BoundaryDecision):
        return BoundaryDecision.DENY
    return result.decision
