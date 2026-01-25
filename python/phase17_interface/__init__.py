"""
Phase-17 Browser Execution Interface Contract.

This module provides interface contract validation.

THIS IS AN INTERFACE CONTRACT LAYER ONLY.
IT DOES NOT EXECUTE BROWSERS.
IT DOES NOT INVOKE SUBPROCESSES.
IT DOES NOT MAKE NETWORK CALLS.

Exports:
    Enums:
        ActionType: NAVIGATE, CLICK, FILL, SCREENSHOT, EXTRACT
        ResponseStatus: SUCCESS, FAILURE, TIMEOUT
        ContractStatus: VALID, DENIED
    
    Dataclasses (all frozen=True):
        ExecutionRequest: Request to executor
        ExecutionResponse: Response from executor
        ContractValidationResult: Validation result
    
    Functions:
        validate_execution_request: Validate request
        validate_execution_response: Validate response
        verify_success_has_evidence: Verify SUCCESS has proof
"""
from .interface_types import (
    ActionType,
    ResponseStatus,
    ContractStatus,
    VALID_ACTION_TYPES,
    VALID_RESPONSE_STATUSES,
    REQUIRED_REQUEST_FIELDS,
    OPTIONAL_REQUEST_FIELDS,
    FORBIDDEN_REQUEST_FIELDS,
    REQUIRED_RESPONSE_FIELDS,
    OPTIONAL_RESPONSE_FIELDS,
    FORBIDDEN_RESPONSE_FIELDS
)
from .interface_context import (
    ExecutionRequest,
    ExecutionResponse,
    ContractValidationResult
)
from .interface_engine import (
    validate_execution_request,
    validate_execution_response,
    verify_success_has_evidence
)

__all__ = [
    # Enums
    "ActionType",
    "ResponseStatus",
    "ContractStatus",
    # Dataclasses
    "ExecutionRequest",
    "ExecutionResponse",
    "ContractValidationResult",
    # Constants
    "VALID_ACTION_TYPES",
    "VALID_RESPONSE_STATUSES",
    "REQUIRED_REQUEST_FIELDS",
    "OPTIONAL_REQUEST_FIELDS",
    "FORBIDDEN_REQUEST_FIELDS",
    "REQUIRED_RESPONSE_FIELDS",
    "OPTIONAL_RESPONSE_FIELDS",
    "FORBIDDEN_RESPONSE_FIELDS",
    # Functions
    "validate_execution_request",
    "validate_execution_response",
    "verify_success_has_evidence",
]
