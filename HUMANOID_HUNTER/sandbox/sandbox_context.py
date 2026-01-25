"""
Phase-21 Sandbox Context.

This module defines frozen dataclasses for sandbox & fault isolation.

All dataclasses are frozen=True for immutability.
"""
from dataclasses import dataclass

from .sandbox_types import ExecutionFaultType, SandboxDecision, RetryPolicy


@dataclass(frozen=True)
class SandboxContext:
    """Sandbox context. Frozen.
    
    Attributes:
        execution_id: Execution ID from Phase-18
        instruction_id: Instruction ID from Phase-20
        attempt_number: Current attempt number (1-indexed)
        max_retries: Maximum retries allowed
        timeout_ms: Timeout in milliseconds
        timestamp: ISO timestamp
    """
    execution_id: str
    instruction_id: str
    attempt_number: int
    max_retries: int
    timeout_ms: int
    timestamp: str


@dataclass(frozen=True)
class FaultReport:
    """Fault report. Frozen.
    
    Attributes:
        fault_id: Unique fault ID
        execution_id: Execution ID
        fault_type: Type of fault
        fault_message: Fault message
        occurred_at: ISO timestamp
        attempt_number: Attempt when fault occurred
    """
    fault_id: str
    execution_id: str
    fault_type: ExecutionFaultType
    fault_message: str
    occurred_at: str
    attempt_number: int


@dataclass(frozen=True)
class SandboxDecisionResult:
    """Sandbox decision result. Frozen.
    
    Attributes:
        decision: TERMINATE, RETRY, ESCALATE
        retry_policy: Applicable retry policy
        reason_code: Machine-readable code
        reason_description: Human-readable description
    """
    decision: SandboxDecision
    retry_policy: RetryPolicy
    reason_code: str
    reason_description: str
