"""
Phase-30 Response Context.

This module defines frozen dataclasses for executor response governance.

All dataclasses are frozen=True (immutable).

THIS IS A POLICY LAYER ONLY.
IT DOES NOT EXECUTE ANYTHING.
"""
from dataclasses import dataclass
from typing import Any

from .response_types import ExecutorResponseType, ResponseDecision


@dataclass(frozen=True)
class ExecutorRawResponse:
    """Raw executor response.
    
    Frozen=True - Cannot be modified after creation.
    
    Attributes:
        executor_id: Identifier of the executor
        instruction_hash: Hash of the instruction that was executed
        raw_payload: Opaque response data (never parsed by governance)
        reported_status: What the executor claims happened
    """
    executor_id: str
    instruction_hash: str
    raw_payload: Any
    reported_status: ExecutorResponseType


@dataclass(frozen=True)
class NormalizedExecutionResult:
    """Normalized execution result.
    
    Frozen=True - Cannot be modified after creation.
    
    Attributes:
        decision: ResponseDecision (ACCEPT, REJECT, ESCALATE)
        reason: Human-readable reason for the decision
        confidence_score: Confidence in the decision (0.0 <= x < 1.0)
            NEVER reaches 1.0 without human confirmation
    """
    decision: ResponseDecision
    reason: str
    confidence_score: float
