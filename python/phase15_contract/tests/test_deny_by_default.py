"""
Tests for Phase-15 Deny-By-Default.

Tests:
- Unknown → DENIED
- Null payload → DENIED
- Unexpected fields → DENIED
"""
import pytest


class TestDenyByDefault:
    """Test deny-by-default behavior."""

    def test_null_payload_denied(self):
        """Null payload is denied."""
        from python.phase15_contract.validation_engine import validate_contract
        from python.phase15_contract.contract_types import ValidationStatus

        result = validate_contract(None)
        assert result.status == ValidationStatus.DENIED
        assert result.reason_code == "NULL_PAYLOAD"

    def test_empty_dict_denied(self):
        """Empty dict is denied."""
        from python.phase15_contract.validation_engine import validate_contract
        from python.phase15_contract.contract_types import ValidationStatus

        result = validate_contract({})
        assert result.status == ValidationStatus.DENIED

    def test_unexpected_field_denied(self):
        """Unexpected field is denied."""
        from python.phase15_contract.validation_engine import validate_unexpected_fields
        from python.phase15_contract.contract_types import ValidationStatus

        payload = {
            "request_id": "REQ-001",
            "bug_id": "BUG-001",
            "target_id": "TARGET-001",
            "request_type": "STATUS_CHECK",
            "timestamp": "2026-01-25T06:00:00-05:00",
            "unknown_field": "some_value"  # UNEXPECTED
        }

        result = validate_unexpected_fields(payload)
        assert result.status == ValidationStatus.DENIED

    def test_null_forbidden_check(self):
        """validate_forbidden_fields with null payload."""
        from python.phase15_contract.validation_engine import validate_forbidden_fields
        from python.phase15_contract.contract_types import ValidationStatus

        result = validate_forbidden_fields({})
        assert result.status == ValidationStatus.DENIED

    def test_null_request_type_check(self):
        """validate_request_type with null payload."""
        from python.phase15_contract.validation_engine import validate_request_type
        from python.phase15_contract.contract_types import ValidationStatus

        result = validate_request_type({})
        assert result.status == ValidationStatus.DENIED

    def test_null_unexpected_check(self):
        """validate_unexpected_fields with null payload."""
        from python.phase15_contract.validation_engine import validate_unexpected_fields
        from python.phase15_contract.contract_types import ValidationStatus

        result = validate_unexpected_fields({})
        assert result.status == ValidationStatus.DENIED

    def test_contract_unexpected_via_full_contract(self):
        """Unexpected field via validate_contract."""
        from python.phase15_contract.validation_engine import validate_contract
        from python.phase15_contract.contract_types import ValidationStatus

        payload = {
            "request_id": "REQ-001",
            "bug_id": "BUG-001",
            "target_id": "TARGET-001",
            "request_type": "STATUS_CHECK",
            "timestamp": "2026-01-25T06:00:00-05:00",
            "random_extra": "value"  # Unexpected
        }

        result = validate_contract(payload)
        assert result.status == ValidationStatus.DENIED       

    def test_contract_invalid_request_type_via_full(self):
        """Invalid request_type via validate_contract."""
        from python.phase15_contract.validation_engine import validate_contract
        from python.phase15_contract.contract_types import ValidationStatus

        payload = {
            "request_id": "REQ-001",
            "bug_id": "BUG-001",
            "target_id": "TARGET-001",
            "request_type": "INVALID_TYPE",  # Invalid
            "timestamp": "2026-01-25T06:00:00-05:00"
        }

        result = validate_contract(payload)
        assert result.status == ValidationStatus.DENIED


class TestFullContractValidation:
    """Test full contract validation."""

    def test_valid_contract_passes(self):
        """Valid contract passes all checks."""
        from python.phase15_contract.validation_engine import validate_contract
        from python.phase15_contract.contract_types import ValidationStatus

        payload = {
            "request_id": "REQ-001",
            "bug_id": "BUG-001",
            "target_id": "TARGET-001",
            "request_type": "STATUS_CHECK",
            "timestamp": "2026-01-25T06:00:00-05:00"
        }

        result = validate_contract(payload)
        assert result.status == ValidationStatus.VALID
        assert result.is_valid is True

    def test_valid_with_optional_fields(self):
        """Valid contract with optional fields passes."""
        from python.phase15_contract.validation_engine import validate_contract
        from python.phase15_contract.contract_types import ValidationStatus

        payload = {
            "request_id": "REQ-001",
            "bug_id": "BUG-001",
            "target_id": "TARGET-001",
            "request_type": "STATUS_CHECK",
            "timestamp": "2026-01-25T06:00:00-05:00",
            "session_id": "SESSION-001",
            "notes": "Some notes"
        }

        result = validate_contract(payload)
        assert result.status == ValidationStatus.VALID


class TestNoForbiddenImports:
    """Test no forbidden imports."""

    def test_no_os_import(self):
        """No os import."""
        import python.phase15_contract.validation_engine as module
        import inspect
        source = inspect.getsource(module)
        assert 'import os' not in source

    def test_no_phase16_import(self):
        """No phase16+ imports in implementation files (test files excluded)."""
        import os
        module_dir = os.path.dirname(__file__).replace('/tests', '').replace('\\tests', '')
        for filename in os.listdir(module_dir):
            if filename.endswith('.py') and not filename.startswith('test_'):
                filepath = os.path.join(module_dir, filename)
                with open(filepath, 'r') as f:
                    content = f.read()
                    assert 'phase16' not in content
