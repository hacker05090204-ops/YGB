"""
Phase-15 Contract Context.

This module defines frozen dataclasses for contract validation.

All dataclasses are frozen=True for immutability.
"""
from dataclasses import dataclass
from typing import Optional

from .contract_types import RequestType, ValidationStatus


@dataclass(frozen=True)
class FrontendRequest:
    """Validated frontend request.
    
    All fields are immutable after creation.
    
    Attributes:
        request_id: Unique request identifier
        bug_id: Bug being queried
        target_id: Target identifier
        request_type: Type of request
        timestamp: ISO timestamp
        session_id: Optional session ID
        user_context: Optional user context
        notes: Optional notes
    """
    request_id: str
    bug_id: str
    target_id: str
    request_type: RequestType
    timestamp: str
    session_id: Optional[str] = None
    user_context: Optional[str] = None
    notes: Optional[str] = None


@dataclass(frozen=True)
class ContractValidationResult:
    """Immutable validation result.
    
    Attributes:
        status: VALID or DENIED
        is_valid: True if valid
        reason_code: Machine-readable reason
        reason_description: Human-readable reason
        request: Validated request if valid
        denied_fields: Fields that caused denial
    """
    status: ValidationStatus
    is_valid: bool
    reason_code: str
    reason_description: str
    request: Optional[FrontendRequest] = None
    denied_fields: tuple = ()
