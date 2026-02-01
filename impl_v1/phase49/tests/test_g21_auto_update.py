# test_g21_auto_update.py
"""Tests for G21 Auto-Update Governance."""

import pytest

from impl_v1.phase49.governors.g21_auto_update import (
    UpdateStatus,
    UpdateChannel,
    UpdateInfo,
    UpdateApproval,
    UpdateResult,
    RollbackInfo,
    get_current_version,
    set_current_version,
    check_for_updates,
    get_update_status,
    verify_signature,
    request_update_approval,
    submit_approval,
    install_update,
    rollback,
    can_auto_update_execute,
    can_update_skip_signature,
    can_update_prevent_rollback,
    clear_update_state,
)


class TestUpdateStatus:
    """Tests for UpdateStatus enum."""
    
    def test_has_none_available(self):
        assert UpdateStatus.NONE_AVAILABLE.value == "NONE_AVAILABLE"
    
    def test_has_available(self):
        assert UpdateStatus.AVAILABLE.value == "AVAILABLE"
    
    def test_has_awaiting_approval(self):
        assert UpdateStatus.AWAITING_APPROVAL.value == "AWAITING_APPROVAL"
    
    def test_has_installed(self):
        assert UpdateStatus.INSTALLED.value == "INSTALLED"
    
    def test_has_rolled_back(self):
        assert UpdateStatus.ROLLED_BACK.value == "ROLLED_BACK"


class TestUpdateChannel:
    """Tests for UpdateChannel enum."""
    
    def test_has_stable(self):
        assert UpdateChannel.STABLE.value == "STABLE"
    
    def test_has_beta(self):
        assert UpdateChannel.BETA.value == "BETA"


class TestCheckForUpdates:
    """Tests for check_for_updates."""
    
    def setup_method(self):
        clear_update_state()
    
    def test_no_update_by_default(self):
        result = check_for_updates()
        assert result is None
        assert get_update_status() == UpdateStatus.NONE_AVAILABLE
    
    def test_mock_update_available(self):
        mock = {"version": "1.0.1", "channel": "STABLE"}
        result = check_for_updates(_mock_update=mock)
        assert result is not None
        assert result.version == "1.0.1"
    
    def test_status_changes_to_available(self):
        mock = {"version": "1.0.1"}
        check_for_updates(_mock_update=mock)
        assert get_update_status() == UpdateStatus.AVAILABLE


class TestVerifySignature:
    """Tests for verify_signature."""
    
    def setup_method(self):
        clear_update_state()
    
    def test_valid_signature(self):
        mock = {"version": "1.0.1", "signature": "valid-sig"}
        update = check_for_updates(_mock_update=mock)
        is_valid, reason = verify_signature(update)
        assert is_valid == True
    
    def test_invalid_signature(self):
        mock = {"version": "1.0.1", "signature": "invalid"}
        update = check_for_updates(_mock_update=mock)
        is_valid, reason = verify_signature(update)
        assert is_valid == False


class TestUpdateApproval:
    """Tests for update approval flow."""
    
    def setup_method(self):
        clear_update_state()
    
    def test_request_approval(self):
        mock = {"version": "1.0.1"}
        update = check_for_updates(_mock_update=mock)
        approval = request_update_approval(update.update_id, "user1")
        assert approval is not None
        assert approval.approved == False
    
    def test_status_awaiting_approval(self):
        mock = {"version": "1.0.1"}
        update = check_for_updates(_mock_update=mock)
        request_update_approval(update.update_id, "user1")
        assert get_update_status() == UpdateStatus.AWAITING_APPROVAL
    
    def test_submit_approval_approved(self):
        mock = {"version": "1.0.1"}
        update = check_for_updates(_mock_update=mock)
        approval = request_update_approval(update.update_id, "user1")
        result = submit_approval(approval.approval_id, True)
        assert result.approved == True
        assert get_update_status() == UpdateStatus.READY_TO_INSTALL
    
    def test_submit_approval_rejected(self):
        mock = {"version": "1.0.1"}
        update = check_for_updates(_mock_update=mock)
        approval = request_update_approval(update.update_id, "user1")
        result = submit_approval(approval.approval_id, False)
        assert result.approved == False


class TestInstallUpdate:
    """Tests for install_update."""
    
    def setup_method(self):
        clear_update_state()
    
    def test_fails_without_approval(self):
        mock = {"version": "1.0.1"}
        update = check_for_updates(_mock_update=mock)
        result = install_update(update.update_id)
        assert result.status == UpdateStatus.FAILED
        assert "not approved" in result.error_message.lower()
    
    def test_installs_with_approval(self):
        mock = {"version": "1.0.1"}
        update = check_for_updates(_mock_update=mock)
        approval = request_update_approval(update.update_id, "user1")
        submit_approval(approval.approval_id, True)
        
        result = install_update(update.update_id)
        assert result.status == UpdateStatus.INSTALLED
        assert result.new_version == "1.0.1"
    
    def test_rollback_available_after_install(self):
        mock = {"version": "1.0.1"}
        update = check_for_updates(_mock_update=mock)
        approval = request_update_approval(update.update_id, "user1")
        submit_approval(approval.approval_id, True)
        
        result = install_update(update.update_id)
        assert result.rollback_available == True


class TestRollback:
    """Tests for rollback."""
    
    def setup_method(self):
        clear_update_state()
    
    def test_rollback_without_install_fails(self):
        result = rollback()
        assert result.status == UpdateStatus.FAILED
    
    def test_rollback_restores_version(self):
        set_current_version("1.0.0")
        mock = {"version": "1.0.1"}
        update = check_for_updates(_mock_update=mock)
        approval = request_update_approval(update.update_id, "user1")
        submit_approval(approval.approval_id, True)
        install_update(update.update_id)
        
        assert get_current_version() == "1.0.1"
        
        result = rollback()
        assert result.status == UpdateStatus.ROLLED_BACK
        assert get_current_version() == "1.0.0"


class TestCanAutoUpdateExecute:
    """Tests for can_auto_update_execute guard."""
    
    def test_cannot_auto_execute(self):
        can_exec, reason = can_auto_update_execute()
        assert can_exec == False
        assert "approval" in reason.lower()


class TestCanUpdateSkipSignature:
    """Tests for can_update_skip_signature guard."""
    
    def test_cannot_skip_signature(self):
        can_skip, reason = can_update_skip_signature()
        assert can_skip == False
        assert "signature" in reason.lower()


class TestCanUpdatePreventRollback:
    """Tests for can_update_prevent_rollback guard."""
    
    def test_cannot_prevent_rollback(self):
        can_prevent, reason = can_update_prevent_rollback()
        assert can_prevent == False
        assert "rollback" in reason.lower()
