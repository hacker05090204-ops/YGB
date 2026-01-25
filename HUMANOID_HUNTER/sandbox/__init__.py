"""
HUMANOID_HUNTER Sandbox — Runtime Sandbox & Fault Isolation

Phase-21 implementation.

Execution may fail.
The system must NEVER.
"""
from .sandbox_types import (
    ExecutionFaultType,
    SandboxDecision,
    RetryPolicy,
    FAULT_RETRY_POLICY,
    RETRYABLE_FAULTS,
    DEFAULT_MAX_RETRIES
)
from .sandbox_context import (
    SandboxContext,
    FaultReport,
    SandboxDecisionResult
)
from .sandbox_engine import (
    classify_fault,
    is_retry_allowed,
    enforce_retry_limit,
    decide_sandbox_outcome
)

__all__ = [
    # Enums
    "ExecutionFaultType",
    "SandboxDecision",
    "RetryPolicy",
    # Constants
    "FAULT_RETRY_POLICY",
    "RETRYABLE_FAULTS",
    "DEFAULT_MAX_RETRIES",
    # Dataclasses
    "SandboxContext",
    "FaultReport",
    "SandboxDecisionResult",
    # Functions
    "classify_fault",
    "is_retry_allowed",
    "enforce_retry_limit",
    "decide_sandbox_outcome",
]
