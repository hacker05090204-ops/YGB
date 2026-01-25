"""
Phase-22 Native Context.

This module defines frozen dataclasses for native runtime isolation.

All dataclasses are frozen=True for immutability.
"""
from dataclasses import dataclass

from .native_types import NativeProcessState, NativeExitReason, IsolationDecision


@dataclass(frozen=True)
class NativeExecutionContext:
    """Native execution context. Frozen.
    
    Attributes:
        execution_id: Execution ID
        process_id: Native process ID
        command_hash: Hash of the command
        timeout_ms: Timeout in milliseconds
        timestamp: ISO timestamp
    """
    execution_id: str
    process_id: str
    command_hash: str
    timeout_ms: int
    timestamp: str


@dataclass(frozen=True)
class NativeExecutionResult:
    """Native execution result. Frozen.
    
    Attributes:
        execution_id: Execution ID
        process_state: Final process state
        exit_reason: Exit reason
        exit_code: OS exit code
        evidence_hash: Evidence hash (REQUIRED for ACCEPT)
        output_hash: Output hash
        duration_ms: Execution duration
    """
    execution_id: str
    process_state: NativeProcessState
    exit_reason: NativeExitReason
    exit_code: int
    evidence_hash: str
    output_hash: str
    duration_ms: int


@dataclass(frozen=True)
class IsolationDecisionResult:
    """Isolation decision result. Frozen.
    
    Attributes:
        decision: ACCEPT, REJECT, QUARANTINE
        reason_code: Machine-readable code
        reason_description: Human-readable description
    """
    decision: IsolationDecision
    reason_code: str
    reason_description: str
