"""
Tests for Phase-15 Tampered Payloads.

Tests:
- Injected confidence is denied
- Injected severity is denied
- Multiple forbidden fields denied
- Determinism
"""
import pytest


class TestTamperedPayloads:
    """Test tampered payloads are denied."""

    def test_injected_confidence_level_denied(self):
        """Injected confidence_level is denied."""
        from python.phase15_contract.validation_engine import validate_contract
        from python.phase15_contract.contract_types import ValidationStatus

        payload = {
            "request_id": "REQ-001",
            "bug_id": "BUG-001",
            "target_id": "TARGET-001",
            "request_type": "STATUS_CHECK",
            "timestamp": "2026-01-25T06:00:00-05:00",
            "confidence_level": "HIGH"  # TAMPERED
        }

        result = validate_contract(payload)
        assert result.status == ValidationStatus.DENIED

    def test_injected_bug_severity_denied(self):
        """Injected bug_severity is denied."""
        from python.phase15_contract.validation_engine import validate_contract
        from python.phase15_contract.contract_types import ValidationStatus

        payload = {
            "request_id": "REQ-001",
            "bug_id": "BUG-001",
            "target_id": "TARGET-001",
            "request_type": "STATUS_CHECK",
            "timestamp": "2026-01-25T06:00:00-05:00",
            "bug_severity": "CRITICAL"  # TAMPERED
        }

        result = validate_contract(payload)
        assert result.status == ValidationStatus.DENIED

    def test_injected_readiness_state_denied(self):
        """Injected readiness_state is denied."""
        from python.phase15_contract.validation_engine import validate_contract
        from python.phase15_contract.contract_types import ValidationStatus

        payload = {
            "request_id": "REQ-001",
            "bug_id": "BUG-001",
            "target_id": "TARGET-001",
            "request_type": "STATUS_CHECK",
            "timestamp": "2026-01-25T06:00:00-05:00",
            "readiness_state": "READY"  # TAMPERED
        }

        result = validate_contract(payload)
        assert result.status == ValidationStatus.DENIED

    def test_injected_human_presence_denied(self):
        """Injected human_presence is denied."""
        from python.phase15_contract.validation_engine import validate_contract
        from python.phase15_contract.contract_types import ValidationStatus

        payload = {
            "request_id": "REQ-001",
            "bug_id": "BUG-001",
            "target_id": "TARGET-001",
            "request_type": "STATUS_CHECK",
            "timestamp": "2026-01-25T06:00:00-05:00",
            "human_presence": "OPTIONAL"  # TAMPERED
        }

        result = validate_contract(payload)
        assert result.status == ValidationStatus.DENIED

    def test_injected_evidence_state_denied(self):
        """Injected evidence_state is denied."""
        from python.phase15_contract.validation_engine import validate_contract
        from python.phase15_contract.contract_types import ValidationStatus

        payload = {
            "request_id": "REQ-001",
            "bug_id": "BUG-001",
            "target_id": "TARGET-001",
            "request_type": "STATUS_CHECK",
            "timestamp": "2026-01-25T06:00:00-05:00",
            "evidence_state": "CONSISTENT"  # TAMPERED
        }

        result = validate_contract(payload)
        assert result.status == ValidationStatus.DENIED

    def test_multiple_forbidden_fields_denied(self):
        """Multiple forbidden fields are all detected."""
        from python.phase15_contract.validation_engine import validate_contract
        from python.phase15_contract.contract_types import ValidationStatus

        payload = {
            "request_id": "REQ-001",
            "bug_id": "BUG-001",
            "target_id": "TARGET-001",
            "request_type": "STATUS_CHECK",
            "timestamp": "2026-01-25T06:00:00-05:00",
            "confidence": "HIGH",
            "severity": "CRITICAL",
            "can_proceed": True
        }

        result = validate_contract(payload)
        assert result.status == ValidationStatus.DENIED


class TestDeterminism:
    """Test deterministic behavior."""

    def test_same_payload_same_result(self):
        """Same payload produces same result."""
        from python.phase15_contract.validation_engine import validate_contract

        payload = {
            "request_id": "REQ-001",
            "bug_id": "BUG-001",
            "target_id": "TARGET-001",
            "request_type": "STATUS_CHECK",
            "timestamp": "2026-01-25T06:00:00-05:00"
        }

        result1 = validate_contract(payload)
        result2 = validate_contract(payload)
        result3 = validate_contract(payload)

        assert result1.is_valid == result2.is_valid == result3.is_valid
        assert result1.reason_code == result2.reason_code == result3.reason_code


class TestDataclassFrozen:
    """Test dataclass immutability."""

    def test_frontend_request_is_frozen(self):
        """FrontendRequest is frozen."""
        from python.phase15_contract.contract_types import RequestType
        from python.phase15_contract.contract_context import FrontendRequest

        request = FrontendRequest(
            request_id="REQ-001",
            bug_id="BUG-001",
            target_id="TARGET-001",
            request_type=RequestType.STATUS_CHECK,
            timestamp="2026-01-25T06:00:00-05:00"
        )

        with pytest.raises(Exception):
            request.request_id = "MODIFIED"

    def test_validation_result_is_frozen(self):
        """ContractValidationResult is frozen."""
        from python.phase15_contract.contract_types import ValidationStatus
        from python.phase15_contract.contract_context import ContractValidationResult

        result = ContractValidationResult(
            status=ValidationStatus.VALID,
            is_valid=True,
            reason_code="VALID",
            reason_description="All checks passed"
        )

        with pytest.raises(Exception):
            result.is_valid = False
