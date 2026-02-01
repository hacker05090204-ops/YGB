"""
impl_v1 Phase-22 Policy Constraint Types.

NON-AUTHORITATIVE MIRROR of governance Phase-22.
Contains CLOSED enums only.

THIS MODULE HAS NO EXECUTION AUTHORITY.
THIS MODULE NEVER ENFORCES POLICY.
THIS MODULE ONLY VALIDATES POLICY CONSTRAINTS.

CLOSED ENUMS:
- PolicyScope: 4 members (EXECUTION, EVIDENCE, AUTHORIZATION, HUMAN)
- PolicyViolation: 4 members
- PolicyDecision: 3 members (ALLOW, DENY, ESCALATE)

DEFAULT = DENY.
"""
from enum import Enum, auto


class PolicyScope(Enum):
    """Scope of policy application.
    
    CLOSED ENUM - Exactly 4 members. No additions permitted.
    """
    EXECUTION = auto()
    EVIDENCE = auto()
    AUTHORIZATION = auto()
    HUMAN = auto()


class PolicyViolation(Enum):
    """Types of policy violations.
    
    CLOSED ENUM - Exactly 4 members. No additions permitted.
    
    Violations:
    - FORBIDDEN_ACTION: Action is explicitly forbidden
    - OUT_OF_SCOPE: Action is outside policy scope
    - CONDITION_UNMET: Required condition not met
    - UNKNOWN_POLICY: Policy is unknown
    """
    FORBIDDEN_ACTION = auto()
    OUT_OF_SCOPE = auto()
    CONDITION_UNMET = auto()
    UNKNOWN_POLICY = auto()


class PolicyDecision(Enum):
    """Decision from policy evaluation.
    
    CLOSED ENUM - Exactly 3 members. No additions permitted.
    
    Decisions:
    - ALLOW: Action is allowed
    - DENY: Action is denied
    - ESCALATE: Action requires human review
    """
    ALLOW = auto()
    DENY = auto()
    ESCALATE = auto()
