"""
Phase-20 Executor Context.

This module defines frozen dataclasses for executor interface.

All dataclasses are frozen=True for immutability.
"""
from dataclasses import dataclass

from .executor_types import ExecutorCommandType, ExecutorResponseType


@dataclass(frozen=True)
class ExecutorInstructionEnvelope:
    """Executor instruction envelope. Frozen.
    
    Attributes:
        instruction_id: Unique instruction ID
        execution_id: Execution ID from Phase-18
        command_type: Command to execute
        target_url: Target URL (for NAVIGATE)
        target_selector: CSS selector (for CLICK, etc.)
        timestamp: ISO timestamp
        timeout_ms: Timeout in milliseconds
    """
    instruction_id: str
    execution_id: str
    command_type: ExecutorCommandType
    target_url: str
    target_selector: str
    timestamp: str
    timeout_ms: int = 30000


@dataclass(frozen=True)
class ExecutorResponseEnvelope:
    """Executor response envelope. Frozen.
    
    Attributes:
        instruction_id: Matching instruction ID
        response_type: Response type
        evidence_hash: Evidence hash (required for SUCCESS)
        error_message: Error message (for failures)
        timestamp: ISO timestamp
    """
    instruction_id: str
    response_type: ExecutorResponseType
    evidence_hash: str
    error_message: str
    timestamp: str


@dataclass(frozen=True)
class ExecutionSafetyResult:
    """Execution safety validation result. Frozen.
    
    Attributes:
        is_safe: Whether response is safe
        reason_code: Machine-readable code
        reason_description: Human-readable description
    """
    is_safe: bool
    reason_code: str
    reason_description: str
