# AMSE: Adaptive Method Synthesis Engine - Types
"""
CRITICAL MODULE: Method synthesis when all known methods fail.

CONSTRAINTS:
- Explainable
- Scoped
- Logged
- Testable
- Human visible (NO silent autonomy)

Each method defines:
- Preconditions
- Assumptions
- Applicability
- Failure modes
- Confidence score
"""

from dataclasses import dataclass
from enum import Enum
from typing import List, Optional, Tuple


class MethodState(Enum):
    """CLOSED ENUM - 6 members"""
    PROPOSED = "PROPOSED"
    PENDING_HUMAN = "PENDING_HUMAN"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    EXECUTING = "EXECUTING"
    COMPLETED = "COMPLETED"


class MethodConfidence(Enum):
    """CLOSED ENUM - 5 members"""
    VERY_HIGH = "VERY_HIGH"   # 90%+ success expected
    HIGH = "HIGH"             # 70-89%
    MEDIUM = "MEDIUM"         # 50-69%
    LOW = "LOW"               # 30-49%
    EXPERIMENTAL = "EXPERIMENTAL"  # <30%


class SynthesisReason(Enum):
    """CLOSED ENUM - 5 members"""
    ALL_METHODS_FAILED = "ALL_METHODS_FAILED"
    NO_APPLICABLE_METHOD = "NO_APPLICABLE_METHOD"
    METHOD_DEPRECATED = "METHOD_DEPRECATED"
    CONTEXT_NOVEL = "CONTEXT_NOVEL"
    USER_REQUESTED = "USER_REQUESTED"


class FailureMode(Enum):
    """CLOSED ENUM - 8 members"""
    FALSE_POSITIVE = "FALSE_POSITIVE"
    FALSE_NEGATIVE = "FALSE_NEGATIVE"
    TIMEOUT = "TIMEOUT"
    RESOURCE_EXHAUSTION = "RESOURCE_EXHAUSTION"
    SCOPE_VIOLATION = "SCOPE_VIOLATION"
    LOGIC_ERROR = "LOGIC_ERROR"
    DEPENDENCY_FAILURE = "DEPENDENCY_FAILURE"
    UNKNOWN = "UNKNOWN"


class ApplicabilityScope(Enum):
    """CLOSED ENUM - 4 members"""
    SINGLE_TARGET = "SINGLE_TARGET"
    TARGET_CLASS = "TARGET_CLASS"
    GLOBAL = "GLOBAL"
    EXPERIMENTAL = "EXPERIMENTAL"


@dataclass(frozen=True)
class MethodPrecondition:
    """Frozen dataclass for method preconditions."""
    precondition_id: str
    description: str
    required: bool
    verifiable: bool


@dataclass(frozen=True)
class MethodAssumption:
    """Frozen dataclass for method assumptions."""
    assumption_id: str
    description: str
    confidence: MethodConfidence


@dataclass(frozen=True)
class SynthesizedMethod:
    """
    Frozen dataclass for a synthesized method.
    CRITICAL: All fields must be populated for human review.
    """
    method_id: str
    name: str
    description: str
    reason: SynthesisReason
    preconditions: tuple  # tuple of MethodPrecondition
    assumptions: tuple    # tuple of MethodAssumption
    applicability: ApplicabilityScope
    failure_modes: tuple  # tuple of FailureMode
    confidence: MethodConfidence
    state: MethodState
    created_at: str
    human_reviewed: bool
    human_reviewer_id: Optional[str]


@dataclass(frozen=True)
class MethodExecutionPlan:
    """Frozen dataclass for method execution plan."""
    plan_id: str
    method_id: str
    steps: tuple  # tuple of step descriptions
    estimated_duration: int  # seconds
    resource_requirements: tuple
    rollback_steps: tuple


@dataclass(frozen=True)
class MethodAuditEntry:
    """Frozen dataclass for method synthesis audit."""
    audit_id: str
    method_id: str
    event_type: str  # "PROPOSED", "APPROVED", "REJECTED", "EXECUTED"
    actor_id: str
    timestamp: str
    details: str
