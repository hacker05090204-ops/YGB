"""
Tests for Phase-15 Enum Validation.

Tests:
- Valid request types pass
- Invalid request types are denied
"""
import pytest


class TestRequestTypeValidation:
    """Test request type validation."""

    def test_status_check_valid(self):
        """STATUS_CHECK is valid."""
        from python.phase15_contract.validation_engine import validate_request_type
        from python.phase15_contract.contract_types import ValidationStatus

        payload = {"request_type": "STATUS_CHECK"}

        result = validate_request_type(payload)
        assert result.status == ValidationStatus.VALID

    def test_readiness_check_valid(self):
        """READINESS_CHECK is valid."""
        from python.phase15_contract.validation_engine import validate_request_type
        from python.phase15_contract.contract_types import ValidationStatus

        payload = {"request_type": "READINESS_CHECK"}

        result = validate_request_type(payload)
        assert result.status == ValidationStatus.VALID

    def test_full_evaluation_valid(self):
        """FULL_EVALUATION is valid."""
        from python.phase15_contract.validation_engine import validate_request_type
        from python.phase15_contract.contract_types import ValidationStatus

        payload = {"request_type": "FULL_EVALUATION"}

        result = validate_request_type(payload)
        assert result.status == ValidationStatus.VALID

    def test_invalid_request_type_denied(self):
        """Invalid request_type is denied."""
        from python.phase15_contract.validation_engine import validate_request_type
        from python.phase15_contract.contract_types import ValidationStatus

        payload = {"request_type": "UNKNOWN_TYPE"}

        result = validate_request_type(payload)
        assert result.status == ValidationStatus.DENIED
        assert result.reason_code == "INVALID_REQUEST_TYPE"

    def test_random_string_denied(self):
        """Random string request_type is denied."""
        from python.phase15_contract.validation_engine import validate_request_type
        from python.phase15_contract.contract_types import ValidationStatus

        payload = {"request_type": "foobar123"}

        result = validate_request_type(payload)
        assert result.status == ValidationStatus.DENIED

    def test_lowercase_denied(self):
        """Lowercase request_type is denied (must be exact)."""
        from python.phase15_contract.validation_engine import validate_request_type
        from python.phase15_contract.contract_types import ValidationStatus

        payload = {"request_type": "status_check"}  # lowercase

        result = validate_request_type(payload)
        assert result.status == ValidationStatus.DENIED


class TestEnumMemberCounts:
    """Test enum member counts."""

    def test_request_type_has_three_members(self):
        """RequestType has exactly 3 members."""
        from python.phase15_contract.contract_types import RequestType
        assert len(RequestType) == 3

    def test_validation_status_has_two_members(self):
        """ValidationStatus has exactly 2 members."""
        from python.phase15_contract.contract_types import ValidationStatus
        assert len(ValidationStatus) == 2
