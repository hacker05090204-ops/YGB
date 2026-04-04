"""
Tests for Phase-17 Request Validation.

Tests:
- Required fields present
- Valid field values
"""
import pytest


class TestRequestValidation:
    """Test execution request validation."""

    def test_valid_request_passes(self):
        """Valid request passes validation."""
        from python.phase17_interface.interface_engine import validate_execution_request
        from python.phase17_interface.interface_types import ContractStatus

        request = {
            "request_id": "REQ-001",
            "bug_id": "BUG-001",
            "target_id": "TARGET-001",
            "action_type": "NAVIGATE",
            "timestamp": "2026-01-25T07:05:00-05:00",
            "execution_permission": "ALLOWED"
        }

        result = validate_execution_request(request)
        assert result.status == ContractStatus.VALID

    def test_missing_request_id_denied(self):
        """Missing request_id is denied."""
        from python.phase17_interface.interface_engine import validate_execution_request
        from python.phase17_interface.interface_types import ContractStatus

        request = {
            "bug_id": "BUG-001",
            "target_id": "TARGET-001",
            "action_type": "NAVIGATE",
            "timestamp": "2026-01-25T07:05:00-05:00",
            "execution_permission": "ALLOWED"
        }

        result = validate_execution_request(request)
        assert result.status == ContractStatus.DENIED
        assert result.reason_code == "RQ-001"

    def test_missing_bug_id_denied(self):
        """Missing bug_id is denied."""
        from python.phase17_interface.interface_engine import validate_execution_request
        from python.phase17_interface.interface_types import ContractStatus

        request = {
            "request_id": "REQ-001",
            "target_id": "TARGET-001",
            "action_type": "NAVIGATE",
            "timestamp": "2026-01-25T07:05:00-05:00",
            "execution_permission": "ALLOWED"
        }

        result = validate_execution_request(request)
        assert result.status == ContractStatus.DENIED
        assert result.reason_code == "RQ-002"

    def test_missing_action_type_denied(self):
        """Missing action_type is denied."""
        from python.phase17_interface.interface_engine import validate_execution_request
        from python.phase17_interface.interface_types import ContractStatus

        request = {
            "request_id": "REQ-001",
            "bug_id": "BUG-001",
            "target_id": "TARGET-001",
            "timestamp": "2026-01-25T07:05:00-05:00",
            "execution_permission": "ALLOWED"
        }

        result = validate_execution_request(request)
        assert result.status == ContractStatus.DENIED

    def test_permission_not_allowed_denied(self):
        """Permission not ALLOWED is denied."""
        from python.phase17_interface.interface_engine import validate_execution_request
        from python.phase17_interface.interface_types import ContractStatus

        request = {
            "request_id": "REQ-001",
            "bug_id": "BUG-001",
            "target_id": "TARGET-001",
            "action_type": "NAVIGATE",
            "timestamp": "2026-01-25T07:05:00-05:00",
            "execution_permission": "DENIED"  # Not allowed
        }

        result = validate_execution_request(request)
        assert result.status == ContractStatus.DENIED
        assert result.reason_code == "RQ-007"

    def test_invalid_action_type_denied(self):
        """Invalid action_type is denied."""
        from python.phase17_interface.interface_engine import validate_execution_request
        from python.phase17_interface.interface_types import ContractStatus

        request = {
            "request_id": "REQ-001",
            "bug_id": "BUG-001",
            "target_id": "TARGET-001",
            "action_type": "INVALID_ACTION",
            "timestamp": "2026-01-25T07:05:00-05:00",
            "execution_permission": "ALLOWED"
        }

        result = validate_execution_request(request)
        assert result.status == ContractStatus.DENIED
        assert result.reason_code == "RQ-008"
