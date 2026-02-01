# test_g11_execution_seal.py
"""Tests for G11: Execution Seal"""

import pytest
from impl_v1.phase49.governors.g11_execution_seal import (
    SealCheckType,
    SealCheckResult,
    SealCheckEntry,
    ExecutionSealResult,
    create_check,
    seal_execution_intent,
    validate_seal,
    can_execute,
)


class TestEnumClosure:
    """Verify enums are closed."""
    
    def test_seal_check_type_11_members(self):
        assert len(SealCheckType) == 11
    
    def test_seal_check_result_3_members(self):
        assert len(SealCheckResult) == 3


class TestCreateCheck:
    """Test check creation."""
    
    def test_pass_check(self):
        check = create_check(SealCheckType.G01_EXECUTION_STATE, True, "State valid")
        assert check.result == SealCheckResult.PASS
        assert check.reason == "State valid"
    
    def test_fail_check(self):
        check = create_check(SealCheckType.G08_LICENSE_VALID, False, "Invalid license")
        assert check.result == SealCheckResult.FAIL
        assert check.reason == "Invalid license"
    
    def test_check_has_timestamp(self):
        check = create_check(SealCheckType.G01_EXECUTION_STATE, True, "")
        assert check.timestamp is not None


class TestSealExecutionIntent:
    """Test execution seal creation."""
    
    def test_all_pass_seal_valid(self):
        seal = seal_execution_intent(
            execution_state_valid=True,
            browser_types_valid=True,
            browser_safety_passed=True,
            voice_ready=True,
            assistant_approved=True,
            autonomy_mode_valid=True,
            cve_loaded=True,
            license_valid=True,
            device_trusted=True,
            no_critical_alerts=True,
            human_confirmed=True,
        )
        assert seal.sealed is True
        assert seal.all_passed is True
        assert len(seal.failed_checks) == 0
    
    def test_any_fail_blocks_seal(self):
        seal = seal_execution_intent(
            execution_state_valid=True,
            browser_types_valid=True,
            browser_safety_passed=True,
            voice_ready=True,
            assistant_approved=True,
            autonomy_mode_valid=True,
            cve_loaded=True,
            license_valid=False,  # This fails
            device_trusted=True,
            no_critical_alerts=True,
            human_confirmed=True,
        )
        assert seal.sealed is False
        assert seal.all_passed is False
        assert SealCheckType.G08_LICENSE_VALID in seal.failed_checks
    
    def test_multiple_failures(self):
        seal = seal_execution_intent(
            execution_state_valid=False,
            browser_types_valid=False,
            browser_safety_passed=True,
            voice_ready=True,
            assistant_approved=True,
            autonomy_mode_valid=True,
            cve_loaded=True,
            license_valid=True,
            device_trusted=True,
            no_critical_alerts=True,
            human_confirmed=True,
        )
        assert seal.sealed is False
        assert len(seal.failed_checks) == 2
    
    def test_seal_has_id(self):
        seal = seal_execution_intent(
            execution_state_valid=True,
            browser_types_valid=True,
            browser_safety_passed=True,
            voice_ready=True,
            assistant_approved=True,
            autonomy_mode_valid=True,
            cve_loaded=True,
            license_valid=True,
            device_trusted=True,
            no_critical_alerts=True,
            human_confirmed=True,
        )
        assert seal.seal_id.startswith("SEAL-")
    
    def test_block_reason_set_on_failure(self):
        seal = seal_execution_intent(
            execution_state_valid=True,
            browser_types_valid=True,
            browser_safety_passed=False,
            voice_ready=True,
            assistant_approved=True,
            autonomy_mode_valid=True,
            cve_loaded=True,
            license_valid=True,
            device_trusted=True,
            no_critical_alerts=True,
            human_confirmed=True,
        )
        assert seal.block_reason is not None
        assert "safety" in seal.block_reason.lower()
    
    def test_human_confirmation_required(self):
        seal = seal_execution_intent(
            execution_state_valid=True,
            browser_types_valid=True,
            browser_safety_passed=True,
            voice_ready=True,
            assistant_approved=True,
            autonomy_mode_valid=True,
            cve_loaded=True,
            license_valid=True,
            device_trusted=True,
            no_critical_alerts=True,
            human_confirmed=False,  # Not confirmed
        )
        assert seal.sealed is False
        assert SealCheckType.G11_FINAL_SEAL in seal.failed_checks


class TestValidateSeal:
    """Test seal validation."""
    
    def test_valid_seal(self):
        seal = seal_execution_intent(
            True, True, True, True, True, True, True, True, True, True, True
        )
        valid, reason = validate_seal(seal)
        assert valid
        assert "valid" in reason.lower()
    
    def test_invalid_seal(self):
        seal = seal_execution_intent(
            True, True, True, True, True, True, True, False, True, True, True
        )
        valid, reason = validate_seal(seal)
        assert not valid


class TestCanExecute:
    """Test can_execute shorthand."""
    
    def test_can_execute_valid(self):
        seal = seal_execution_intent(
            True, True, True, True, True, True, True, True, True, True, True
        )
        assert can_execute(seal) is True
    
    def test_cannot_execute_invalid(self):
        seal = seal_execution_intent(
            True, True, True, True, True, True, True, True, True, True, False
        )
        assert can_execute(seal) is False


class TestAllChecksIncluded:
    """Verify all 11 checks are performed."""
    
    def test_all_11_checks(self):
        seal = seal_execution_intent(
            True, True, True, True, True, True, True, True, True, True, True
        )
        assert len(seal.checks) == 11
    
    def test_check_types_match(self):
        seal = seal_execution_intent(
            True, True, True, True, True, True, True, True, True, True, True
        )
        check_types = {c.check_type for c in seal.checks}
        assert check_types == set(SealCheckType)


class TestDataclassFrozen:
    """Verify dataclasses are frozen."""
    
    def test_seal_frozen(self):
        seal = seal_execution_intent(
            True, True, True, True, True, True, True, True, True, True, True
        )
        with pytest.raises(AttributeError):
            seal.sealed = False
    
    def test_check_entry_frozen(self):
        check = create_check(SealCheckType.G01_EXECUTION_STATE, True, "")
        with pytest.raises(AttributeError):
            check.result = SealCheckResult.FAIL
