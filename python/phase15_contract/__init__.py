"""
Phase-15 Frontend ↔ Backend Contract Authority.

This module provides contract validation for frontend requests.

The backend has ABSOLUTE AUTHORITY over critical fields.
Frontend cannot set confidence, severity, readiness, etc.

Exports:
    Enums:
        RequestType: Allowed request types (STATUS_CHECK, READINESS_CHECK, FULL_EVALUATION)
        ValidationStatus: Validation status (VALID, DENIED)
    
    Dataclasses (all frozen=True):
        FrontendRequest: Validated frontend request
        ContractValidationResult: Validation result
    
    Constants:
        REQUIRED_FIELDS: Required field names
        OPTIONAL_FIELDS: Optional field names
        ALLOWED_FIELDS: All allowed field names
        FORBIDDEN_FIELDS: Backend-only field names
        VALID_REQUEST_TYPES: Valid request type values
    
    Functions:
        validate_required_fields: Validate required fields
        validate_forbidden_fields: Check for forbidden fields
        validate_request_type: Validate request type enum
        validate_unexpected_fields: Check for unexpected fields
        validate_contract: Full contract validation
"""
from .contract_types import (
    RequestType,
    ValidationStatus,
    REQUIRED_FIELDS,
    OPTIONAL_FIELDS,
    ALLOWED_FIELDS,
    FORBIDDEN_FIELDS,
    VALID_REQUEST_TYPES
)
from .contract_context import FrontendRequest, ContractValidationResult
from .validation_engine import (
    validate_required_fields,
    validate_forbidden_fields,
    validate_request_type,
    validate_unexpected_fields,
    validate_contract
)

__all__ = [
    # Enums
    "RequestType",
    "ValidationStatus",
    # Dataclasses
    "FrontendRequest",
    "ContractValidationResult",
    # Constants
    "REQUIRED_FIELDS",
    "OPTIONAL_FIELDS",
    "ALLOWED_FIELDS",
    "FORBIDDEN_FIELDS",
    "VALID_REQUEST_TYPES",
    # Functions
    "validate_required_fields",
    "validate_forbidden_fields",
    "validate_request_type",
    "validate_unexpected_fields",
    "validate_contract",
]
