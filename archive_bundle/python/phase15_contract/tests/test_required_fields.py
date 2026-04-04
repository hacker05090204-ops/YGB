"""
Tests for Phase-15 Required Fields.

Tests:
- All required fields must be present
- Empty required fields are denied
- Missing required fields are denied
"""
import pytest


class TestRequiredFieldsPresent:
    """Test required fields are present."""

    def test_valid_payload_passes(self):
        """Valid payload with all required fields passes."""
        from python.phase15_contract.validation_engine import validate_required_fields
        from python.phase15_contract.contract_types import ValidationStatus

        payload = {
            "request_id": "REQ-001",
            "bug_id": "BUG-001",
            "target_id": "TARGET-001",
            "request_type": "STATUS_CHECK",
            "timestamp": "2026-01-25T06:00:00-05:00"
        }

        result = validate_required_fields(payload)
        assert result.status == ValidationStatus.VALID

    def test_missing_request_id_denied(self):
        """Missing request_id is denied."""
        from python.phase15_contract.validation_engine import validate_required_fields
        from python.phase15_contract.contract_types import ValidationStatus

        payload = {
            "bug_id": "BUG-001",
            "target_id": "TARGET-001",
            "request_type": "STATUS_CHECK",
            "timestamp": "2026-01-25T06:00:00-05:00"
        }

        result = validate_required_fields(payload)
        assert result.status == ValidationStatus.DENIED
        assert result.reason_code == "MISSING_REQUEST_ID"

    def test_missing_bug_id_denied(self):
        """Missing bug_id is denied."""
        from python.phase15_contract.validation_engine import validate_required_fields
        from python.phase15_contract.contract_types import ValidationStatus

        payload = {
            "request_id": "REQ-001",
            "target_id": "TARGET-001",
            "request_type": "STATUS_CHECK",
            "timestamp": "2026-01-25T06:00:00-05:00"
        }

        result = validate_required_fields(payload)
        assert result.status == ValidationStatus.DENIED
        assert result.reason_code == "MISSING_BUG_ID"

    def test_missing_target_id_denied(self):
        """Missing target_id is denied."""
        from python.phase15_contract.validation_engine import validate_required_fields
        from python.phase15_contract.contract_types import ValidationStatus

        payload = {
            "request_id": "REQ-001",
            "bug_id": "BUG-001",
            "request_type": "STATUS_CHECK",
            "timestamp": "2026-01-25T06:00:00-05:00"
        }

        result = validate_required_fields(payload)
        assert result.status == ValidationStatus.DENIED
        assert result.reason_code == "MISSING_TARGET_ID"

    def test_missing_request_type_denied(self):
        """Missing request_type is denied."""
        from python.phase15_contract.validation_engine import validate_required_fields
        from python.phase15_contract.contract_types import ValidationStatus

        payload = {
            "request_id": "REQ-001",
            "bug_id": "BUG-001",
            "target_id": "TARGET-001",
            "timestamp": "2026-01-25T06:00:00-05:00"
        }

        result = validate_required_fields(payload)
        assert result.status == ValidationStatus.DENIED
        assert result.reason_code == "MISSING_REQUEST_TYPE"

    def test_missing_timestamp_denied(self):
        """Missing timestamp is denied."""
        from python.phase15_contract.validation_engine import validate_required_fields
        from python.phase15_contract.contract_types import ValidationStatus

        payload = {
            "request_id": "REQ-001",
            "bug_id": "BUG-001",
            "target_id": "TARGET-001",
            "request_type": "STATUS_CHECK"
        }

        result = validate_required_fields(payload)
        assert result.status == ValidationStatus.DENIED
        assert result.reason_code == "MISSING_TIMESTAMP"


class TestEmptyRequiredFields:
    """Test empty required fields are denied."""

    def test_empty_request_id_denied(self):
        """Empty request_id is denied."""
        from python.phase15_contract.validation_engine import validate_required_fields
        from python.phase15_contract.contract_types import ValidationStatus

        payload = {
            "request_id": "",
            "bug_id": "BUG-001",
            "target_id": "TARGET-001",
            "request_type": "STATUS_CHECK",
            "timestamp": "2026-01-25T06:00:00-05:00"
        }

        result = validate_required_fields(payload)
        assert result.status == ValidationStatus.DENIED

    def test_empty_bug_id_denied(self):
        """Empty bug_id is denied."""
        from python.phase15_contract.validation_engine import validate_required_fields
        from python.phase15_contract.contract_types import ValidationStatus

        payload = {
            "request_id": "REQ-001",
            "bug_id": "",
            "target_id": "TARGET-001",
            "request_type": "STATUS_CHECK",
            "timestamp": "2026-01-25T06:00:00-05:00"
        }

        result = validate_required_fields(payload)
        assert result.status == ValidationStatus.DENIED
