"""
impl_v1 Phase-26 Execution Readiness Mirror.

NON-AUTHORITATIVE MIRROR of governance Phase-26.
Contains ONLY data structures and validation logic.

THIS MODULE HAS NO EXECUTION AUTHORITY.
THIS MODULE DOES NOT START EXECUTION.
THIS MODULE ONLY EVALUATES READINESS.

CLOSED ENUMS:
- ReadinessStatus: 3 members
- ReadinessBlocker: 5 members

FROZEN DATACLASSES:
- ExecutionReadinessContext: 5 fields
- ReadinessResult: 3 fields

ENGINE FUNCTIONS (VALIDATION ONLY):
- validate_readiness_context
- evaluate_readiness
- get_readiness_status
- get_blockers
- is_execution_ready

READY REQUIRES ALL CONDITIONS TRUE.
"""
from .phase26_types import (
    ReadinessStatus,
    ReadinessBlocker,
)
from .phase26_context import (
    ExecutionReadinessContext,
    ReadinessResult,
)
from .phase26_engine import (
    validate_readiness_context,
    evaluate_readiness,
    get_readiness_status,
    get_blockers,
    is_execution_ready,
)

__all__ = [
    # Types
    "ReadinessStatus",
    "ReadinessBlocker",
    # Context
    "ExecutionReadinessContext",
    "ReadinessResult",
    # Engine
    "validate_readiness_context",
    "evaluate_readiness",
    "get_readiness_status",
    "get_blockers",
    "is_execution_ready",
]
