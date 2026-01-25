"""
HUMANOID_HUNTER — Browser Executor Adapter & Safety Harness

Phase-20 implementation.

This is an INTERFACE LAYER ONLY.
It does NOT execute browsers.
"""
from .interface.executor_types import (
    ExecutorCommandType,
    ExecutorResponseType,
    ExecutorStatus
)
from .interface.executor_context import (
    ExecutorInstructionEnvelope,
    ExecutorResponseEnvelope,
    ExecutionSafetyResult
)
from .interface.executor_adapter import (
    build_executor_instruction,
    validate_executor_response,
    enforce_executor_safety
)

__all__ = [
    # Enums
    "ExecutorCommandType",
    "ExecutorResponseType",
    "ExecutorStatus",
    # Dataclasses
    "ExecutorInstructionEnvelope",
    "ExecutorResponseEnvelope",
    "ExecutionSafetyResult",
    # Functions
    "build_executor_instruction",
    "validate_executor_response",
    "enforce_executor_safety",
]
