"""
Tests for Phase-17 Deny-By-Default.

Tests:
- Null request/response → DENIED
- Unknown values → DENIED
- Determinism
"""
import pytest


class TestDenyByDefault:
    """Test deny-by-default behavior."""

    def test_null_request_denied(self):
        """Null request is denied."""
        from python.phase17_interface.interface_engine import validate_execution_request
        from python.phase17_interface.interface_types import ContractStatus

        result = validate_execution_request(None)
        assert result.status == ContractStatus.DENIED
        assert result.reason_code == "RQ-000"

    def test_empty_request_denied(self):
        """Empty request is denied."""
        from python.phase17_interface.interface_engine import validate_execution_request
        from python.phase17_interface.interface_types import ContractStatus

        result = validate_execution_request({})
        assert result.status == ContractStatus.DENIED

    def test_null_response_denied(self):
        """Null response is denied."""
        from python.phase17_interface.interface_engine import validate_execution_response
        from python.phase17_interface.interface_types import ContractStatus

        result = validate_execution_response(None, "REQ-001")
        assert result.status == ContractStatus.DENIED
        assert result.reason_code == "RS-000"


class TestDeterminism:
    """Test deterministic behavior."""

    def test_same_request_same_result(self):
        """Same request produces same result."""
        from python.phase17_interface.interface_engine import validate_execution_request

        request = {
            "request_id": "REQ-001",
            "bug_id": "BUG-001",
            "target_id": "TARGET-001",
            "action_type": "NAVIGATE",
            "timestamp": "2026-01-25T07:05:00-05:00",
            "execution_permission": "ALLOWED"
        }

        result1 = validate_execution_request(request)
        result2 = validate_execution_request(request)
        result3 = validate_execution_request(request)

        assert result1.is_valid == result2.is_valid == result3.is_valid


class TestDataclassFrozen:
    """Test dataclass immutability."""

    def test_contract_validation_result_frozen(self):
        """ContractValidationResult is frozen."""
        from python.phase17_interface.interface_types import ContractStatus
        from python.phase17_interface.interface_context import ContractValidationResult

        result = ContractValidationResult(
            status=ContractStatus.VALID,
            is_valid=True,
            reason_code="OK",
            reason_description="Valid"
        )

        with pytest.raises(Exception):
            result.is_valid = False
