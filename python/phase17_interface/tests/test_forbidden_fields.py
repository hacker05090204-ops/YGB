"""
Tests for Phase-17 Forbidden Fields.

Tests:
- Forbidden fields in request
- Forbidden fields in response
"""
import pytest


class TestForbiddenFieldsRequest:
    """Test forbidden fields in request."""

    def test_trust_level_forbidden(self):
        """trust_level is forbidden."""
        from python.phase17_interface.interface_engine import validate_execution_request
        from python.phase17_interface.interface_types import ContractStatus

        request = {
            "request_id": "REQ-001",
            "bug_id": "BUG-001",
            "target_id": "TARGET-001",
            "action_type": "NAVIGATE",
            "timestamp": "2026-01-25T07:05:00-05:00",
            "execution_permission": "ALLOWED",
            "trust_level": "HIGH"  # FORBIDDEN
        }

        result = validate_execution_request(request)
        assert result.status == ContractStatus.DENIED
        assert "trust_level" in result.denied_fields

    def test_confidence_forbidden(self):
        """confidence is forbidden."""
        from python.phase17_interface.interface_engine import validate_execution_request
        from python.phase17_interface.interface_types import ContractStatus

        request = {
            "request_id": "REQ-001",
            "bug_id": "BUG-001",
            "target_id": "TARGET-001",
            "action_type": "NAVIGATE",
            "timestamp": "2026-01-25T07:05:00-05:00",
            "execution_permission": "ALLOWED",
            "confidence": "HIGH"  # FORBIDDEN
        }

        result = validate_execution_request(request)
        assert result.status == ContractStatus.DENIED

    def test_override_forbidden(self):
        """override is forbidden."""
        from python.phase17_interface.interface_engine import validate_execution_request
        from python.phase17_interface.interface_types import ContractStatus

        request = {
            "request_id": "REQ-001",
            "bug_id": "BUG-001",
            "target_id": "TARGET-001",
            "action_type": "NAVIGATE",
            "timestamp": "2026-01-25T07:05:00-05:00",
            "execution_permission": "ALLOWED",
            "override": True  # FORBIDDEN
        }

        result = validate_execution_request(request)
        assert result.status == ContractStatus.DENIED


class TestForbiddenFieldsResponse:
    """Test forbidden fields in response."""

    def test_approved_forbidden(self):
        """approved is forbidden in response."""
        from python.phase17_interface.interface_engine import validate_execution_response
        from python.phase17_interface.interface_types import ContractStatus

        response = {
            "request_id": "REQ-001",
            "status": "SUCCESS",
            "timestamp": "2026-01-25T07:05:00-05:00",
            "evidence_hash": "abc123",
            "approved": True  # FORBIDDEN
        }

        result = validate_execution_response(response, "REQ-001")
        assert result.status == ContractStatus.DENIED

    def test_validated_forbidden(self):
        """validated is forbidden in response."""
        from python.phase17_interface.interface_engine import validate_execution_response
        from python.phase17_interface.interface_types import ContractStatus

        response = {
            "request_id": "REQ-001",
            "status": "SUCCESS",
            "timestamp": "2026-01-25T07:05:00-05:00",
            "evidence_hash": "abc123",
            "validated": True  # FORBIDDEN
        }

        result = validate_execution_response(response, "REQ-001")
        assert result.status == ContractStatus.DENIED
