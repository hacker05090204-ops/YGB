"""
HUMANOID_HUNTER Native — Runtime Boundary & OS Isolation Contract

Phase-22 implementation.

Native code may run.
Native code may fail.
Native code may lie.
Governance NEVER does.
"""
from .native_types import (
    NativeProcessState,
    NativeExitReason,
    IsolationDecision,
    TERMINAL_STATES,
    INVALID_STATES
)
from .native_context import (
    NativeExecutionContext,
    NativeExecutionResult,
    IsolationDecisionResult
)
from .native_engine import (
    classify_native_exit,
    is_native_result_valid,
    evaluate_isolation_result,
    decide_native_outcome
)

__all__ = [
    # Enums
    "NativeProcessState",
    "NativeExitReason",
    "IsolationDecision",
    # Constants
    "TERMINAL_STATES",
    "INVALID_STATES",
    # Dataclasses
    "NativeExecutionContext",
    "NativeExecutionResult",
    "IsolationDecisionResult",
    # Functions
    "classify_native_exit",
    "is_native_result_valid",
    "evaluate_isolation_result",
    "decide_native_outcome",
]
