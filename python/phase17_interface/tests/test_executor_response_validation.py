"""
Tests for Phase-17 Executor Response Validation.

Tests:
- Executor response validation
- SUCCESS must have evidence
- Request ID must match
"""
import pytest


class TestExecutorResponseValidation:
    """Test executor response validation."""

    def test_valid_success_response_passes(self):
        """Valid SUCCESS response passes."""
        from python.phase17_interface.interface_engine import validate_execution_response
        from python.phase17_interface.interface_types import ContractStatus

        response = {
            "request_id": "REQ-001",
            "status": "SUCCESS",
            "timestamp": "2026-01-25T07:05:00-05:00",
            "evidence_hash": "abc123def456"
        }

        result = validate_execution_response(response, "REQ-001")
        assert result.status == ContractStatus.VALID

    def test_valid_failure_response_passes(self):
        """Valid FAILURE response passes."""
        from python.phase17_interface.interface_engine import validate_execution_response
        from python.phase17_interface.interface_types import ContractStatus

        response = {
            "request_id": "REQ-001",
            "status": "FAILURE",
            "timestamp": "2026-01-25T07:05:00-05:00",
            "error_code": "ERR-001"
        }

        result = validate_execution_response(response, "REQ-001")
        assert result.status == ContractStatus.VALID

    def test_success_without_evidence_denied(self):
        """SUCCESS without evidence_hash is denied."""
        from python.phase17_interface.interface_engine import validate_execution_response
        from python.phase17_interface.interface_types import ContractStatus

        response = {
            "request_id": "REQ-001",
            "status": "SUCCESS",
            "timestamp": "2026-01-25T07:05:00-05:00"
            # No evidence_hash
        }

        result = validate_execution_response(response, "REQ-001")
        assert result.status == ContractStatus.DENIED
        assert result.reason_code == "RS-006"

    def test_mismatched_request_id_denied(self):
        """Mismatched request_id is denied."""
        from python.phase17_interface.interface_engine import validate_execution_response
        from python.phase17_interface.interface_types import ContractStatus

        response = {
            "request_id": "REQ-002",  # Different
            "status": "SUCCESS",
            "timestamp": "2026-01-25T07:05:00-05:00",
            "evidence_hash": "abc123"
        }

        result = validate_execution_response(response, "REQ-001")  # Expected REQ-001
        assert result.status == ContractStatus.DENIED
        assert result.reason_code == "RS-004"

    def test_missing_status_denied(self):
        """Missing status is denied."""
        from python.phase17_interface.interface_engine import validate_execution_response
        from python.phase17_interface.interface_types import ContractStatus

        response = {
            "request_id": "REQ-001",
            "timestamp": "2026-01-25T07:05:00-05:00"
        }

        result = validate_execution_response(response, "REQ-001")
        assert result.status == ContractStatus.DENIED
        assert result.reason_code == "RS-002"

    def test_invalid_status_denied(self):
        """Invalid status is denied."""
        from python.phase17_interface.interface_engine import validate_execution_response
        from python.phase17_interface.interface_types import ContractStatus

        response = {
            "request_id": "REQ-001",
            "status": "INVALID_STATUS",
            "timestamp": "2026-01-25T07:05:00-05:00"
        }

        result = validate_execution_response(response, "REQ-001")
        assert result.status == ContractStatus.DENIED
        assert result.reason_code == "RS-005"


class TestVerifySuccessHasEvidence:
    """Test verify_success_has_evidence function."""

    def test_success_with_hash_returns_true(self):
        """SUCCESS with hash returns True."""
        from python.phase17_interface.interface_engine import verify_success_has_evidence

        response = {
            "status": "SUCCESS",
            "evidence_hash": "abc123"
        }

        assert verify_success_has_evidence(response) is True

    def test_success_without_hash_returns_false(self):
        """SUCCESS without hash returns False."""
        from python.phase17_interface.interface_engine import verify_success_has_evidence

        response = {
            "status": "SUCCESS"
        }

        assert verify_success_has_evidence(response) is False

    def test_failure_returns_true(self):
        """FAILURE doesn't need hash."""
        from python.phase17_interface.interface_engine import verify_success_has_evidence

        response = {
            "status": "FAILURE"
        }

        assert verify_success_has_evidence(response) is True

    def test_empty_response_returns_false(self):
        """Empty response returns False."""
        from python.phase17_interface.interface_engine import verify_success_has_evidence

        assert verify_success_has_evidence({}) is False


class TestMissingResponseFields:
    """Test missing response fields."""

    def test_missing_request_id_denied(self):
        """Missing request_id is denied."""
        from python.phase17_interface.interface_engine import validate_execution_response
        from python.phase17_interface.interface_types import ContractStatus

        response = {
            "status": "SUCCESS",
            "timestamp": "2026-01-25T07:05:00-05:00",
            "evidence_hash": "abc123"
        }

        result = validate_execution_response(response, "REQ-001")
        assert result.status == ContractStatus.DENIED
        assert result.reason_code == "RS-001"

    def test_missing_timestamp_denied(self):
        """Missing timestamp is denied."""
        from python.phase17_interface.interface_engine import validate_execution_response
        from python.phase17_interface.interface_types import ContractStatus

        response = {
            "request_id": "REQ-001",
            "status": "SUCCESS",
            "evidence_hash": "abc123"
        }

        result = validate_execution_response(response, "REQ-001")
        assert result.status == ContractStatus.DENIED
        assert result.reason_code == "RS-003"
