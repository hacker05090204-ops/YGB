"""
impl_v1 Phase-20 System Root Boundary Mirror.

NON-AUTHORITATIVE MIRROR of governance Phase-20.
THIS MODULE NEVER ENFORCES BOUNDARIES.
THIS MODULE ONLY DEFINES WHAT THE SYSTEM IS.

PHASE-20 IS THE ABSOLUTE ROOT BOUNDARY.
NOTHING EXISTS BELOW IT.
NOTHING BYPASSES IT.
"""
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
from .phase20_engine import (
    validate_boundary_id,
    validate_system_boundary,
    validate_layer_transition,
    detect_boundary_violation,
    evaluate_system_boundary,
    get_boundary_decision,
)

__all__ = [
    "SystemLayer",
    "BoundaryViolation",
    "BoundaryDecision",
    "SystemBoundary",
    "BoundaryEvaluationContext",
    "BoundaryEvaluationResult",
    "validate_boundary_id",
    "validate_system_boundary",
    "validate_layer_transition",
    "detect_boundary_violation",
    "evaluate_system_boundary",
    "get_boundary_decision",
]
