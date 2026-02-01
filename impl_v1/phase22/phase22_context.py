"""
impl_v1 Phase-22 Policy Constraint Context.

NON-AUTHORITATIVE MIRROR of governance Phase-22.
Contains FROZEN dataclasses only.

THIS MODULE HAS NO EXECUTION AUTHORITY.

ALL DATACLASSES ARE FROZEN (frozen=True):
- PolicyRule: 5 fields
- PolicyEvaluationContext: 3 fields
- PolicyEvaluationResult: 3 fields
"""
from dataclasses import dataclass
from typing import Tuple

from .phase22_types import (
    PolicyScope,
    PolicyViolation,
    PolicyDecision,
)


@dataclass(frozen=True)
class PolicyRule:
    """A policy rule definition.
    
    Immutable once created.
    
    Attributes:
        policy_id: Unique identifier for the policy
        scope: Scope of the policy
        description: Human-readable description
        enforced: Whether the policy is enforced
        severity: Severity level (1-10)
    """
    policy_id: str
    scope: PolicyScope
    description: str
    enforced: bool
    severity: int


@dataclass(frozen=True)
class PolicyEvaluationContext:
    """Context for policy evaluation.
    
    Immutable once created.
    
    Attributes:
        scope: Scope of the requested action
        requested_action: The action being requested
        conditions: Tuple of condition strings
    """
    scope: PolicyScope
    requested_action: str
    conditions: Tuple[str, ...]


@dataclass(frozen=True)
class PolicyEvaluationResult:
    """Result of policy evaluation.
    
    Immutable once created.
    
    Attributes:
        decision: Final decision
        violations: Tuple of violations
        reasons: Tuple of reason strings
    """
    decision: PolicyDecision
    violations: Tuple[PolicyViolation, ...]
    reasons: Tuple[str, ...]
