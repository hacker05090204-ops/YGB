"""
Phase-17 Interface Engine.

This module provides interface contract validation logic.

All functions are pure (no side effects).
All validation is deny-by-default.

THIS IS AN INTERFACE CONTRACT LAYER ONLY.
IT DOES NOT EXECUTE ANYTHING.
"""
from typing import Optional

from .interface_types import (
    ContractStatus,
    REQUIRED_REQUEST_FIELDS,
    OPTIONAL_REQUEST_FIELDS,
    FORBIDDEN_REQUEST_FIELDS,
    VALID_ACTION_TYPES,
    REQUIRED_RESPONSE_FIELDS,
    OPTIONAL_RESPONSE_FIELDS,
    FORBIDDEN_RESPONSE_FIELDS,
    VALID_RESPONSE_STATUSES
)
from .interface_context import ContractValidationResult


def validate_execution_request(request: Optional[dict]) -> ContractValidationResult:
    """Validate execution request before sending to executor.
    
    Args:
        request: Request dict
        
    Returns:
        ContractValidationResult
    """
    # Null check
    if request is None:
        return ContractValidationResult(
            status=ContractStatus.DENIED,
            is_valid=False,
            reason_code="RQ-000",
            reason_description="Request is null"
        )
    
    # Check required fields
    required_checks = [
        ("request_id", "RQ-001"),
        ("bug_id", "RQ-002"),
        ("target_id", "RQ-003"),
        ("action_type", "RQ-004"),
        ("timestamp", "RQ-005"),
        ("execution_permission", "RQ-006"),
    ]
    
    for field, code in required_checks:
        if field not in request or not request[field]:
            return ContractValidationResult(
                status=ContractStatus.DENIED,
                is_valid=False,
                reason_code=code,
                reason_description=f"Missing required field: {field}"
            )
    
    # Check execution_permission is ALLOWED
    if request["execution_permission"] != "ALLOWED":
        return ContractValidationResult(
            status=ContractStatus.DENIED,
            is_valid=False,
            reason_code="RQ-007",
            reason_description="execution_permission must be ALLOWED"
        )
    
    # Check valid action_type
    if request["action_type"] not in VALID_ACTION_TYPES:
        return ContractValidationResult(
            status=ContractStatus.DENIED,
            is_valid=False,
            reason_code="RQ-008",
            reason_description=f"Invalid action_type: {request['action_type']}"
        )
    
    # Check for forbidden fields
    forbidden_found = []
    for field in request.keys():
        if field in FORBIDDEN_REQUEST_FIELDS:
            forbidden_found.append(field)
    
    if forbidden_found:
        return ContractValidationResult(
            status=ContractStatus.DENIED,
            is_valid=False,
            reason_code="RQ-009",
            reason_description=f"Forbidden fields: {', '.join(forbidden_found)}",
            denied_fields=tuple(forbidden_found)
        )
    
    # All checks passed
    return ContractValidationResult(
        status=ContractStatus.VALID,
        is_valid=True,
        reason_code="RQ-OK",
        reason_description="Request is valid"
    )


def verify_success_has_evidence(response: dict) -> bool:
    """Verify SUCCESS has evidence_hash.
    
    Args:
        response: Response dict
        
    Returns:
        True if valid (not SUCCESS or has evidence_hash)
    """
    if not response:
        return False
    
    status = response.get("status")
    if status != "SUCCESS":
        return True  # Not SUCCESS, OK
    
    evidence_hash = response.get("evidence_hash")
    return bool(evidence_hash)


def validate_execution_response(
    response: Optional[dict],
    expected_request_id: str
) -> ContractValidationResult:
    """Validate executor response.
    
    Args:
        response: Response dict from executor
        expected_request_id: Expected request_id
        
    Returns:
        ContractValidationResult
    """
    # Null check
    if response is None:
        return ContractValidationResult(
            status=ContractStatus.DENIED,
            is_valid=False,
            reason_code="RS-000",
            reason_description="Response is null"
        )
    
    # Check required fields
    if "request_id" not in response or not response["request_id"]:
        return ContractValidationResult(
            status=ContractStatus.DENIED,
            is_valid=False,
            reason_code="RS-001",
            reason_description="Missing request_id"
        )
    
    if "status" not in response or not response["status"]:
        return ContractValidationResult(
            status=ContractStatus.DENIED,
            is_valid=False,
            reason_code="RS-002",
            reason_description="Missing status"
        )
    
    if "timestamp" not in response or not response["timestamp"]:
        return ContractValidationResult(
            status=ContractStatus.DENIED,
            is_valid=False,
            reason_code="RS-003",
            reason_description="Missing timestamp"
        )
    
    # Check request_id match
    if response["request_id"] != expected_request_id:
        return ContractValidationResult(
            status=ContractStatus.DENIED,
            is_valid=False,
            reason_code="RS-004",
            reason_description=f"Request ID mismatch: {response['request_id']} != {expected_request_id}"
        )
    
    # Check valid status
    if response["status"] not in VALID_RESPONSE_STATUSES:
        return ContractValidationResult(
            status=ContractStatus.DENIED,
            is_valid=False,
            reason_code="RS-005",
            reason_description=f"Invalid status: {response['status']}"
        )
    
    # SUCCESS must have evidence_hash
    if not verify_success_has_evidence(response):
        return ContractValidationResult(
            status=ContractStatus.DENIED,
            is_valid=False,
            reason_code="RS-006",
            reason_description="SUCCESS requires evidence_hash"
        )
    
    # Check for forbidden fields
    forbidden_found = []
    for field in response.keys():
        if field in FORBIDDEN_RESPONSE_FIELDS:
            forbidden_found.append(field)
    
    if forbidden_found:
        return ContractValidationResult(
            status=ContractStatus.DENIED,
            is_valid=False,
            reason_code="RS-007",
            reason_description=f"Forbidden fields: {', '.join(forbidden_found)}",
            denied_fields=tuple(forbidden_found)
        )
    
    # All checks passed
    return ContractValidationResult(
        status=ContractStatus.VALID,
        is_valid=True,
        reason_code="RS-OK",
        reason_description="Response is valid"
    )
