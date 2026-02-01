"""
impl_v1 Phase-30 Response Context.

NON-AUTHORITATIVE MIRROR of governance Phase-30.
Contains FROZEN dataclasses only.

THIS MODULE HAS NO EXECUTION AUTHORITY.

ALL DATACLASSES ARE FROZEN (frozen=True):
- ExecutorRawResponse: 6 fields
- NormalizedExecutionResult: 7 fields

IMMUTABILITY GUARANTEE:
- No mutation permitted after creation
- Attempting mutation raises FrozenInstanceError
"""
from dataclasses import dataclass
from typing import Optional

from .phase30_types import ExecutorResponseType, ResponseDecision


@dataclass(frozen=True)
class ExecutorRawResponse:
    """Raw response from an executor.
    
    Captured as-is without interpretation.
    
    Attributes:
        response_id: Unique identifier for this response
        executor_id: ID of the executor that produced this response
        response_type: Type of response (from closed enum)
        raw_data: Opaque bytes (never parsed by this module)
        timestamp: ISO-8601 format timestamp
        elapsed_ms: Execution time in milliseconds
    """
    response_id: str
    executor_id: str
    response_type: ExecutorResponseType
    raw_data: bytes
    timestamp: str
    elapsed_ms: int


@dataclass(frozen=True)
class NormalizedExecutionResult:
    """Normalized execution result after validation.
    
    Immutable once created.
    
    Attributes:
        result_id: Unique identifier for this result
        response_id: Link to original raw response
        response_type: Validated response type
        decision: Decision for this response
        confidence: Confidence score (0.0 to < 1.0, never 1.0 without human)
        reason: Human-readable reason for decision
        requires_human: Whether human review is required
    """
    result_id: str
    response_id: str
    response_type: ExecutorResponseType
    decision: ResponseDecision
    confidence: float
    reason: str
    requires_human: bool
