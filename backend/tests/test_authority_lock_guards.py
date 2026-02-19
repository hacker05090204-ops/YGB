"""
TEST AUTHORITY LOCK — All Guards Permanently FALSE
===================================================
Validates that ALL authority locks are in their safe (False) state.
NO lock may ever be True. NO setter. NO environment override.
"""

import os
import sys
import pytest

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.insert(0, os.path.join(PROJECT_ROOT, 'backend'))

from governance.authority_lock import AuthorityLock


# ==================================================================
# INDIVIDUAL GUARDS
# ==================================================================

class TestIndividualGuards:
    """Every single guard must be permanently False."""

    def test_auto_submit(self):
        assert AuthorityLock.AUTO_SUBMIT is False

    def test_authority_unlock(self):
        assert AuthorityLock.AUTHORITY_UNLOCK is False

    def test_company_targeting(self):
        assert AuthorityLock.COMPANY_TARGETING is False

    def test_mid_training_merge(self):
        assert AuthorityLock.MID_TRAINING_MERGE is False

    def test_voice_hunt_trigger(self):
        assert AuthorityLock.VOICE_HUNT_TRIGGER is False

    def test_voice_submit(self):
        assert AuthorityLock.VOICE_SUBMIT is False

    def test_auto_negotiate(self):
        assert AuthorityLock.AUTO_NEGOTIATE is False

    def test_skip_certification(self):
        assert AuthorityLock.SKIP_CERTIFICATION is False

    def test_cross_field_data(self):
        assert AuthorityLock.CROSS_FIELD_DATA is False

    def test_time_forced_completion(self):
        assert AuthorityLock.TIME_FORCED_COMPLETION is False

    def test_parallel_field_training(self):
        assert AuthorityLock.PARALLEL_FIELD_TRAINING is False


# ==================================================================
# BULK VERIFICATION
# ==================================================================

class TestBulkVerification:
    """Verify all locks at once."""

    def test_verify_all_locked(self):
        result = AuthorityLock.verify_all_locked()
        assert result["all_locked"] is True
        assert result["violations"] == []
        assert result["status"] == "ALL_SAFE"

    def test_total_lock_count(self):
        result = AuthorityLock.verify_all_locked()
        assert result["total_locks"] == 11


# ==================================================================
# ACTION BLOCKING
# ==================================================================

class TestActionBlocking:
    """Verify dangerous actions are permanently blocked."""

    @pytest.mark.parametrize("action", [
        "auto_submit",
        "unlock_authority",
        "target_company",
        "merge_mid_training",
        "voice_hunt",
        "voice_submit",
        "auto_negotiate",
        "skip_cert",
        "cross_field",
        "force_time",
        "parallel_train",
    ])
    def test_blocked_action(self, action):
        result = AuthorityLock.is_action_allowed(action)
        assert result["allowed"] is False
        assert "PERMANENTLY_BLOCKED" in result["reason"]

    def test_unrestricted_action_allowed(self):
        result = AuthorityLock.is_action_allowed("view_dashboard")
        assert result["allowed"] is True
        assert "NOT_RESTRICTED" in result["reason"]


# ==================================================================
# IMMUTABILITY
# ==================================================================

class TestImmutability:
    """Verify locks cannot be modified at runtime."""

    def test_class_attributes_are_bool(self):
        """All lock attributes must be bool False, not ints or strings."""
        locks = [
            AuthorityLock.AUTO_SUBMIT,
            AuthorityLock.AUTHORITY_UNLOCK,
            AuthorityLock.COMPANY_TARGETING,
            AuthorityLock.MID_TRAINING_MERGE,
            AuthorityLock.VOICE_HUNT_TRIGGER,
            AuthorityLock.VOICE_SUBMIT,
            AuthorityLock.AUTO_NEGOTIATE,
            AuthorityLock.SKIP_CERTIFICATION,
            AuthorityLock.CROSS_FIELD_DATA,
            AuthorityLock.TIME_FORCED_COMPLETION,
            AuthorityLock.PARALLEL_FIELD_TRAINING,
        ]
        for lock in locks:
            assert isinstance(lock, bool)
            assert lock is False

    def test_no_setter_bypass(self):
        """Even if someone sets a value, verify_all_locked catches it."""
        # Temporarily set (should fail verify)
        original = AuthorityLock.AUTO_SUBMIT
        AuthorityLock.AUTO_SUBMIT = True
        try:
            result = AuthorityLock.verify_all_locked()
            assert result["all_locked"] is False
            assert "AUTO_SUBMIT" in result["violations"]
        finally:
            AuthorityLock.AUTO_SUBMIT = original
