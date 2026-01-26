"""
impl_v1 Phase-21 System Invariant Context.

NON-AUTHORITATIVE MIRROR of governance Phase-21.
Contains FROZEN dataclasses only.

THIS MODULE HAS NO EXECUTION AUTHORITY.

ALL DATACLASSES ARE FROZEN (frozen=True):
- SystemInvariant: 5 fields
- InvariantEvaluationContext: 3 fields
- InvariantEvaluationResult: 3 fields
"""
from dataclasses import dataclass
from typing import Tuple

from .phase21_types import (
    InvariantScope,
    InvariantViolation,
    InvariantDecision,
)


@dataclass(frozen=True)
class SystemInvariant:
    """A system invariant definition.
    
    Immutable once created.
    
    Attributes:
        invariant_id: Unique identifier for the invariant
        scope: Scope of the invariant
        description: Human-readable description
        enforced: Whether the invariant is enforced
        severity: Severity level (1-10)
    """
    invariant_id: str
    scope: InvariantScope
    description: str
    enforced: bool
    severity: int


@dataclass(frozen=True)
class InvariantEvaluationContext:
    """Context for invariant evaluation.
    
    Immutable once created.
    
    Attributes:
        scope: Scope being evaluated
        observed_state: Tuple of observed state strings
        prior_results: Tuple of prior result strings
    """
    scope: InvariantScope
    observed_state: Tuple[str, ...]
    prior_results: Tuple[str, ...]


@dataclass(frozen=True)
class InvariantEvaluationResult:
    """Result of invariant evaluation.
    
    Immutable once created.
    
    Attributes:
        decision: Final decision
        violations: Tuple of violations
        reasons: Tuple of reason strings
    """
    decision: InvariantDecision
    violations: Tuple[InvariantViolation, ...]
    reasons: Tuple[str, ...]
