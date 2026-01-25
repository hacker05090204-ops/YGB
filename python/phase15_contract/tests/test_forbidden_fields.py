"""
Tests for Phase-15 Forbidden Fields.

Tests:
- Forbidden fields cause denial
- Backend-only fields cannot be set by frontend
"""
import pytest


class TestForbiddenFieldsDetection:
    """Test forbidden fields are detected and denied."""

    def test_confidence_field_denied(self):
        """confidence field is denied."""
        from python.phase15_contract.validation_engine import validate_forbidden_fields
        from python.phase15_contract.contract_types import ValidationStatus

        payload = {
            "request_id": "REQ-001",
            "bug_id": "BUG-001",
            "target_id": "TARGET-001",
            "request_type": "STATUS_CHECK",
            "timestamp": "2026-01-25T06:00:00-05:00",
            "confidence": "HIGH"  # FORBIDDEN
        }

        result = validate_forbidden_fields(payload)
        assert result.status == ValidationStatus.DENIED
        assert "confidence" in result.denied_fields

    def test_severity_field_denied(self):
        """severity field is denied."""
        from python.phase15_contract.validation_engine import validate_forbidden_fields
        from python.phase15_contract.contract_types import ValidationStatus

        payload = {
            "request_id": "REQ-001",
            "bug_id": "BUG-001",
            "target_id": "TARGET-001",
            "request_type": "STATUS_CHECK",
            "timestamp": "2026-01-25T06:00:00-05:00",
            "severity": "CRITICAL"  # FORBIDDEN
        }

        result = validate_forbidden_fields(payload)
        assert result.status == ValidationStatus.DENIED
        assert "severity" in result.denied_fields

    def test_readiness_field_denied(self):
        """readiness field is denied."""
        from python.phase15_contract.validation_engine import validate_forbidden_fields
        from python.phase15_contract.contract_types import ValidationStatus

        payload = {
            "request_id": "REQ-001",
            "bug_id": "BUG-001",
            "target_id": "TARGET-001",
            "request_type": "STATUS_CHECK",
            "timestamp": "2026-01-25T06:00:00-05:00",
            "readiness": "READY_FOR_BROWSER"  # FORBIDDEN
        }

        result = validate_forbidden_fields(payload)
        assert result.status == ValidationStatus.DENIED
        assert "readiness" in result.denied_fields

    def test_can_proceed_field_denied(self):
        """can_proceed field is denied."""
        from python.phase15_contract.validation_engine import validate_forbidden_fields
        from python.phase15_contract.contract_types import ValidationStatus

        payload = {
            "request_id": "REQ-001",
            "bug_id": "BUG-001",
            "target_id": "TARGET-001",
            "request_type": "STATUS_CHECK",
            "timestamp": "2026-01-25T06:00:00-05:00",
            "can_proceed": True  # FORBIDDEN
        }

        result = validate_forbidden_fields(payload)
        assert result.status == ValidationStatus.DENIED

    def test_is_blocked_field_denied(self):
        """is_blocked field is denied."""
        from python.phase15_contract.validation_engine import validate_forbidden_fields
        from python.phase15_contract.contract_types import ValidationStatus

        payload = {
            "request_id": "REQ-001",
            "bug_id": "BUG-001",
            "target_id": "TARGET-001",
            "request_type": "STATUS_CHECK",
            "timestamp": "2026-01-25T06:00:00-05:00",
            "is_blocked": False  # FORBIDDEN
        }

        result = validate_forbidden_fields(payload)
        assert result.status == ValidationStatus.DENIED

    def test_trust_level_field_denied(self):
        """trust_level field is denied."""
        from python.phase15_contract.validation_engine import validate_forbidden_fields
        from python.phase15_contract.contract_types import ValidationStatus

        payload = {
            "request_id": "REQ-001",
            "bug_id": "BUG-001",
            "target_id": "TARGET-001",
            "request_type": "STATUS_CHECK",
            "timestamp": "2026-01-25T06:00:00-05:00",
            "trust_level": "HIGH"  # FORBIDDEN
        }

        result = validate_forbidden_fields(payload)
        assert result.status == ValidationStatus.DENIED

    def test_no_forbidden_fields_valid(self):
        """No forbidden fields passes validation."""
        from python.phase15_contract.validation_engine import validate_forbidden_fields
        from python.phase15_contract.contract_types import ValidationStatus

        payload = {
            "request_id": "REQ-001",
            "bug_id": "BUG-001",
            "target_id": "TARGET-001",
            "request_type": "STATUS_CHECK",
            "timestamp": "2026-01-25T06:00:00-05:00"
        }

        result = validate_forbidden_fields(payload)
        assert result.status == ValidationStatus.VALID
