"""
Phase-17 Interface Context.

This module defines frozen dataclasses for interface contract.

All dataclasses are frozen=True for immutability.
"""
from dataclasses import dataclass
from typing import Optional

from .interface_types import ActionType, ResponseStatus, ContractStatus


@dataclass(frozen=True)
class ExecutionRequest:
    """Request sent to executor. Frozen.
    
    Attributes:
        request_id: Unique request ID
        bug_id: Bug identifier
        target_id: Target identifier
        action_type: Action to perform
        timestamp: ISO timestamp
        execution_permission: Must be "ALLOWED"
        parameters: Optional action-specific parameters
        timeout_seconds: Execution timeout
        session_id: Optional session ID
    """
    request_id: str
    bug_id: str
    target_id: str
    action_type: ActionType
    timestamp: str
    execution_permission: str
    parameters: Optional[dict] = None
    timeout_seconds: int = 300
    session_id: Optional[str] = None


@dataclass(frozen=True)
class ExecutionResponse:
    """Response from executor (untrusted). Frozen.
    
    Attributes:
        request_id: Matching request ID
        status: SUCCESS, FAILURE, TIMEOUT
        timestamp: Response timestamp
        evidence_hash: Hash of evidence (required for SUCCESS)
        error_code: Error code if failure
        error_message: Error message
        execution_time_ms: Execution duration
    """
    request_id: str
    status: ResponseStatus
    timestamp: str
    evidence_hash: Optional[str] = None
    error_code: Optional[str] = None
    error_message: Optional[str] = None
    execution_time_ms: Optional[int] = None


@dataclass(frozen=True)
class ContractValidationResult:
    """Result of contract validation. Frozen.
    
    Attributes:
        status: VALID or DENIED
        is_valid: True if valid
        reason_code: Machine-readable reason
        reason_description: Human-readable reason
        denied_fields: Fields that caused denial
    """
    status: ContractStatus
    is_valid: bool
    reason_code: str
    reason_description: str
    denied_fields: tuple = ()
