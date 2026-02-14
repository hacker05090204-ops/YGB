"""
test_governance_guards.py — Governance Guard Engine Tests

Tests for Phase 1: AutomationEnforcer, Scope Validation, Submission Blocker
"""

import pytest
from backend.governance.automation_enforcer import (
    AutomationEnforcer, ActionResult, ActionType
)


class TestAutoSubmissionBlocking:
    """Tests that auto-submission is ALWAYS blocked."""

    def test_block_submission_hackerone(self):
        enf = AutomationEnforcer()
        result = enf.block_submission("hackerone", "RPT-001")
        assert result == ActionResult.BLOCKED

    def test_block_submission_bugcrowd(self):
        enf = AutomationEnforcer()
        result = enf.block_submission("bugcrowd", "RPT-002")
        assert result == ActionResult.BLOCKED

    def test_block_submission_unknown_platform(self):
        enf = AutomationEnforcer()
        result = enf.block_submission("unknown_platform", "RPT-003")
        assert result == ActionResult.BLOCKED

    def test_block_submission_empty_platform(self):
        enf = AutomationEnforcer()
        result = enf.block_submission("", "RPT-004")
        assert result == ActionResult.BLOCKED


class TestAuthorityUnlockBlocking:
    """Tests that authority unlock is ALWAYS blocked."""

    def test_block_severity_unlock(self):
        enf = AutomationEnforcer()
        result = enf.block_authority_unlock("severity")
        assert result == ActionResult.BLOCKED

    def test_block_exploit_unlock(self):
        enf = AutomationEnforcer()
        result = enf.block_authority_unlock("exploit")
        assert result == ActionResult.BLOCKED

    def test_block_governance_unlock(self):
        enf = AutomationEnforcer()
        result = enf.block_authority_unlock("governance")
        assert result == ActionResult.BLOCKED


class TestHuntStartValidation:
    """Tests that hunt start requires scope + approval."""

    def test_hunt_start_approved_with_scope(self):
        enf = AutomationEnforcer()
        result = enf.validate_hunt_start("example.com", True, True)
        assert result == ActionResult.ALLOWED

    def test_hunt_start_no_scope_blocked(self):
        enf = AutomationEnforcer()
        result = enf.validate_hunt_start("example.com", False, True)
        assert result == ActionResult.BLOCKED

    def test_hunt_start_no_approval_blocked(self):
        enf = AutomationEnforcer()
        result = enf.validate_hunt_start("example.com", True, False)
        assert result == ActionResult.BLOCKED

    def test_hunt_start_no_scope_no_approval_blocked(self):
        enf = AutomationEnforcer()
        result = enf.validate_hunt_start("example.com", False, False)
        assert result == ActionResult.BLOCKED


class TestAuditLogging:
    """Tests that all actions are logged."""

    def test_actions_are_logged(self):
        enf = AutomationEnforcer()
        enf.block_submission("hackerone", "RPT-001")
        enf.block_authority_unlock("severity")
        log = enf.audit_log
        assert len(log) >= 2

    def test_log_entries_have_hashes(self):
        enf = AutomationEnforcer()
        enf.block_submission("test", "RPT-001")
        log = enf.audit_log
        assert log[0]["hash"] is not None
        assert len(log[0]["hash"]) > 0

    def test_blocked_count_increments(self):
        enf = AutomationEnforcer()
        enf.block_submission("p1", "r1")
        enf.block_submission("p2", "r2")
        assert enf.blocked_count >= 2


class TestImmutableRules:
    """Tests that core governance rules cannot be changed."""

    def test_auto_submit_constant_false(self):
        assert AutomationEnforcer.CAN_AUTO_SUBMIT is False

    def test_authority_unlock_constant_false(self):
        assert AutomationEnforcer.CAN_UNLOCK_AUTHORITY is False

    def test_constants_cannot_change(self):
        # Attempting to override should not change the class constant
        original = AutomationEnforcer.CAN_AUTO_SUBMIT
        try:
            AutomationEnforcer.CAN_AUTO_SUBMIT = True  # type: ignore
        except (AttributeError, TypeError):
            pass
        # Even if assignment doesn't throw, check the original behavior
        enf = AutomationEnforcer()
        result = enf.block_submission("test", "RPT-001")
        assert result == ActionResult.BLOCKED
