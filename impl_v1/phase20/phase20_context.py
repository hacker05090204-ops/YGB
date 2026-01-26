"""
impl_v1 Phase-20 System Root Boundary Context.

NON-AUTHORITATIVE MIRROR of governance Phase-20.
Contains FROZEN dataclasses only.

THIS MODULE HAS NO EXECUTION AUTHORITY.

ALL DATACLASSES ARE FROZEN (frozen=True):
- SystemBoundary: 5 fields
- BoundaryEvaluationContext: 3 fields
- BoundaryEvaluationResult: 3 fields
"""
from dataclasses import dataclass
from typing import Tuple

from .phase20_types import (
    SystemLayer,
    BoundaryViolation,
    BoundaryDecision,
)


@dataclass(frozen=True)
class SystemBoundary:
    """A system boundary definition.
    
    Immutable once created.
    
    Attributes:
        boundary_id: Unique identifier for the boundary
        layer: Layer of the boundary
        description: Human-readable description
        immutable: Whether the boundary is immutable (ROOT must be True)
        enforced: Whether the boundary is enforced
    """
    boundary_id: str
    layer: SystemLayer
    description: str
    immutable: bool
    enforced: bool


@dataclass(frozen=True)
class BoundaryEvaluationContext:
    """Context for boundary evaluation.
    
    Immutable once created.
    
    Attributes:
        current_layer: Current system layer
        requested_layer: Requested target layer
        prior_decisions: Tuple of prior decision strings
    """
    current_layer: SystemLayer
    requested_layer: SystemLayer
    prior_decisions: Tuple[str, ...]


@dataclass(frozen=True)
class BoundaryEvaluationResult:
    """Result of boundary evaluation.
    
    Immutable once created.
    
    Attributes:
        decision: Final decision
        violations: Tuple of violations
        reasons: Tuple of reason strings
    """
    decision: BoundaryDecision
    violations: Tuple[BoundaryViolation, ...]
    reasons: Tuple[str, ...]
