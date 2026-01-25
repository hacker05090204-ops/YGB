"""
Phase-15 Validation Engine.

This module provides contract validation logic.

All functions are pure (no side effects).
All validation is deny-by-default.
"""
from typing import Optional

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


def validate_required_fields(payload: dict) -> ContractValidationResult:
    """Validate all required fields are present and non-empty.
    
    Args:
        payload: Request payload dict
        
    Returns:
        ContractValidationResult
    """
    if not payload:
        return ContractValidationResult(
            status=ValidationStatus.DENIED,
            is_valid=False,
            reason_code="NULL_PAYLOAD",
            reason_description="Payload is null or empty"
        )
    
    # Check each required field
    for field in REQUIRED_FIELDS:
        if field not in payload:
            return ContractValidationResult(
                status=ValidationStatus.DENIED,
                is_valid=False,
                reason_code=f"MISSING_{field.upper()}",
                reason_description=f"Required field '{field}' is missing"
            )
        
        value = payload[field]
        if not value or (isinstance(value, str) and not value.strip()):
            return ContractValidationResult(
                status=ValidationStatus.DENIED,
                is_valid=False,
                reason_code=f"EMPTY_{field.upper()}",
                reason_description=f"Required field '{field}' is empty"
            )
    
    return ContractValidationResult(
        status=ValidationStatus.VALID,
        is_valid=True,
        reason_code="REQUIRED_FIELDS_VALID",
        reason_description="All required fields present"
    )


def validate_forbidden_fields(payload: dict) -> ContractValidationResult:
    """Check for any forbidden fields in payload.
    
    Forbidden fields are backend-only and cannot be set by frontend.
    
    Args:
        payload: Request payload dict
        
    Returns:
        ContractValidationResult
    """
    if not payload:
        return ContractValidationResult(
            status=ValidationStatus.DENIED,
            is_valid=False,
            reason_code="NULL_PAYLOAD",
            reason_description="Payload is null or empty"
        )
    
    # Check for any forbidden fields
    found_forbidden = []
    for field in payload.keys():
        if field in FORBIDDEN_FIELDS:
            found_forbidden.append(field)
    
    if found_forbidden:
        return ContractValidationResult(
            status=ValidationStatus.DENIED,
            is_valid=False,
            reason_code="FORBIDDEN_FIELD_DETECTED",
            reason_description=f"Forbidden fields: {', '.join(found_forbidden)}",
            denied_fields=tuple(found_forbidden)
        )
    
    return ContractValidationResult(
        status=ValidationStatus.VALID,
        is_valid=True,
        reason_code="NO_FORBIDDEN_FIELDS",
        reason_description="No forbidden fields detected"
    )


def validate_request_type(payload: dict) -> ContractValidationResult:
    """Validate request_type is in allowed list.
    
    Args:
        payload: Request payload dict
        
    Returns:
        ContractValidationResult
    """
    if not payload or "request_type" not in payload:
        return ContractValidationResult(
            status=ValidationStatus.DENIED,
            is_valid=False,
            reason_code="MISSING_REQUEST_TYPE",
            reason_description="request_type is missing"
        )
    
    request_type = payload["request_type"]
    
    if request_type not in VALID_REQUEST_TYPES:
        return ContractValidationResult(
            status=ValidationStatus.DENIED,
            is_valid=False,
            reason_code="INVALID_REQUEST_TYPE",
            reason_description=f"Invalid request_type: {request_type}"
        )
    
    return ContractValidationResult(
        status=ValidationStatus.VALID,
        is_valid=True,
        reason_code="VALID_REQUEST_TYPE",
        reason_description="request_type is valid"
    )


def validate_unexpected_fields(payload: dict) -> ContractValidationResult:
    """Check for any unexpected fields (not in allowed list).
    
    Args:
        payload: Request payload dict
        
    Returns:
        ContractValidationResult
    """
    if not payload:
        return ContractValidationResult(
            status=ValidationStatus.DENIED,
            is_valid=False,
            reason_code="NULL_PAYLOAD",
            reason_description="Payload is null or empty"
        )
    
    unexpected = []
    for field in payload.keys():
        if field not in ALLOWED_FIELDS:
            unexpected.append(field)
    
    if unexpected:
        return ContractValidationResult(
            status=ValidationStatus.DENIED,
            is_valid=False,
            reason_code="UNEXPECTED_FIELD",
            reason_description=f"Unexpected fields: {', '.join(unexpected)}",
            denied_fields=tuple(unexpected)
        )
    
    return ContractValidationResult(
        status=ValidationStatus.VALID,
        is_valid=True,
        reason_code="NO_UNEXPECTED_FIELDS",
        reason_description="No unexpected fields"
    )


def validate_contract(payload: Optional[dict]) -> ContractValidationResult:
    """Full contract validation. Deny-by-default.
    
    Validates:
    1. Null payload
    2. Required fields
    3. Forbidden fields
    4. Unexpected fields
    5. Request type enum
    
    Args:
        payload: Request payload dict
        
    Returns:
        ContractValidationResult
    """
    # 1. Null payload check
    if payload is None:
        return ContractValidationResult(
            status=ValidationStatus.DENIED,
            is_valid=False,
            reason_code="NULL_PAYLOAD",
            reason_description="Payload is null"
        )
    
    # 2. Required fields check
    result = validate_required_fields(payload)
    if not result.is_valid:
        return result
    
    # 3. Forbidden fields check
    result = validate_forbidden_fields(payload)
    if not result.is_valid:
        return result
    
    # 4. Unexpected fields check
    result = validate_unexpected_fields(payload)
    if not result.is_valid:
        return result
    
    # 5. Request type validation
    result = validate_request_type(payload)
    if not result.is_valid:
        return result
    
    # All checks passed - create validated request
    request = FrontendRequest(
        request_id=payload["request_id"],
        bug_id=payload["bug_id"],
        target_id=payload["target_id"],
        request_type=RequestType(payload["request_type"]),
        timestamp=payload["timestamp"],
        session_id=payload.get("session_id"),
        user_context=payload.get("user_context"),
        notes=payload.get("notes")
    )
    
    return ContractValidationResult(
        status=ValidationStatus.VALID,
        is_valid=True,
        reason_code="CONTRACT_VALID",
        reason_description="Contract validation passed",
        request=request
    )
