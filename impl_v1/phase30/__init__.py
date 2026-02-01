"""
impl_v1 Phase-30 Response Governance Mirror.

NON-AUTHORITATIVE MIRROR of governance Phase-30.
Contains ONLY data structures and validation logic.

THIS MODULE HAS NO EXECUTION AUTHORITY.
THIS MODULE DOES NOT EXECUTE RESPONSES.
THIS MODULE DOES NOT MODIFY STATE.

CLOSED ENUMS:
- ExecutorResponseType: 5 members
- ResponseDecision: 3 members

FROZEN DATACLASSES:
- ExecutorRawResponse: 6 fields
- NormalizedExecutionResult: 7 fields

ENGINE FUNCTIONS (VALIDATION ONLY):
- validate_executor_response
- normalize_response
- evaluate_response_trust
- decide_response_outcome

EXECUTOR OUTPUT IS DATA, NOT TRUTH.
GOVERNANCE DECIDES.
"""
from .phase30_types import (
    ExecutorResponseType,
    ResponseDecision,
)
from .phase30_context import (
    ExecutorRawResponse,
    NormalizedExecutionResult,
)
from .phase30_engine import (
    validate_executor_response,
    normalize_response,
    evaluate_response_trust,
    decide_response_outcome,
)

__all__ = [
    # Types
    "ExecutorResponseType",
    "ResponseDecision",
    # Context
    "ExecutorRawResponse",
    "NormalizedExecutionResult",
    # Engine
    "validate_executor_response",
    "normalize_response",
    "evaluate_response_trust",
    "decide_response_outcome",
]
