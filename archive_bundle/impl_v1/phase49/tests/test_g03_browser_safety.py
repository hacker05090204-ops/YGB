# test_g03_browser_safety.py
"""Tests for G03: Browser Safety Adapter"""

import pytest
from impl_v1.phase49.governors.g03_browser_safety import (
    BrowserSafetyCheck,
    SafetyCheckResult,
    check_scope,
    check_ethics,
    check_duplicate,
    check_mutex,
    check_human_approval,
    check_browser_safety,
)


class TestEnumClosure:
    """Verify enums are closed."""
    
    def test_safety_check_5_members(self):
        assert len(BrowserSafetyCheck) == 5
    
    def test_safety_result_3_members(self):
        assert len(SafetyCheckResult) == 3


class TestScopeCheck:
    """Test scope checking."""
    
    def test_in_scope_domain(self):
        result = check_scope("https://example.com/path", ["example.com"])
        assert result.result == SafetyCheckResult.PASS
    
    def test_subdomain_in_scope(self):
        result = check_scope("https://api.example.com/v1", ["example.com"])
        assert result.result == SafetyCheckResult.PASS
    
    def test_out_of_scope(self):
        result = check_scope("https://evil.com", ["example.com"])
        assert result.result == SafetyCheckResult.FAIL
        assert "OUT OF SCOPE" in result.reason
    
    def test_invalid_url(self):
        result = check_scope("not-a-url", ["example.com"])
        assert result.result == SafetyCheckResult.FAIL


class TestEthicsCheck:
    """Test ethics checking."""
    
    def test_allowed_action(self):
        result = check_ethics("READ", ["EXPLOIT", "DELETE"])
        assert result.result == SafetyCheckResult.PASS
    
    def test_prohibited_action(self):
        result = check_ethics("EXPLOIT", ["EXPLOIT", "DELETE"])
        assert result.result == SafetyCheckResult.FAIL
        assert "PROHIBITED" in result.reason
    
    def test_case_insensitive(self):
        result = check_ethics("exploit", ["EXPLOIT"])
        assert result.result == SafetyCheckResult.FAIL


class TestDuplicateCheck:
    """Test duplicate checking."""
    
    def test_no_duplicate(self):
        result = check_duplicate("target-new", ["target-1", "target-2"])
        assert result.result == SafetyCheckResult.PASS
    
    def test_duplicate_found(self):
        result = check_duplicate("target-1", ["target-1", "target-2"])
        assert result.result == SafetyCheckResult.FAIL
        assert "DUPLICATE" in result.reason


class TestMutexCheck:
    """Test mutex checking."""
    
    def test_no_conflict(self):
        result = check_mutex("resource-new", ["resource-1"])
        assert result.result == SafetyCheckResult.PASS
    
    def test_mutex_conflict(self):
        result = check_mutex("resource-1", ["resource-1"])
        assert result.result == SafetyCheckResult.FAIL
        assert "LOCKED" in result.reason


class TestHumanApprovalCheck:
    """Test human approval checking."""
    
    def test_approved(self):
        result = check_human_approval(True, "human-123")
        assert result.result == SafetyCheckResult.PASS
    
    def test_not_approved(self):
        result = check_human_approval(False, None)
        assert result.result == SafetyCheckResult.FAIL
        assert "NOT granted" in result.reason


class TestFullSafetyCheck:
    """Test complete browser safety check."""
    
    def test_all_pass(self):
        result = check_browser_safety(
            target_url="https://example.com",
            action_type="READ",
            target_id="target-1",
            resource_id="resource-1",
            human_approved=True,
            approver_id="human-1",
            allowed_domains=["example.com"],
            prohibited_actions=["EXPLOIT"],
            known_targets=[],
            locked_resources=[],
        )
        assert result.all_passed
        assert result.blocked_by is None
    
    def test_blocked_by_scope(self):
        result = check_browser_safety(
            target_url="https://evil.com",
            action_type="READ",
            target_id="target-1",
            resource_id="resource-1",
            human_approved=True,
            approver_id="human-1",
            allowed_domains=["example.com"],
            prohibited_actions=["EXPLOIT"],
            known_targets=[],
            locked_resources=[],
        )
        assert not result.all_passed
        assert result.blocked_by == BrowserSafetyCheck.SCOPE
    
    def test_blocked_by_ethics(self):
        result = check_browser_safety(
            target_url="https://example.com",
            action_type="EXPLOIT",
            target_id="target-1",
            resource_id="resource-1",
            human_approved=True,
            approver_id="human-1",
            allowed_domains=["example.com"],
            prohibited_actions=["EXPLOIT"],
            known_targets=[],
            locked_resources=[],
        )
        assert not result.all_passed
        assert result.blocked_by == BrowserSafetyCheck.ETHICS
    
    def test_blocked_by_duplicate(self):
        result = check_browser_safety(
            target_url="https://example.com",
            action_type="READ",
            target_id="target-1",
            resource_id="resource-1",
            human_approved=True,
            approver_id="human-1",
            allowed_domains=["example.com"],
            prohibited_actions=["EXPLOIT"],
            known_targets=["target-1"],
            locked_resources=[],
        )
        assert not result.all_passed
        assert result.blocked_by == BrowserSafetyCheck.DUPLICATE
    
    def test_blocked_by_mutex(self):
        result = check_browser_safety(
            target_url="https://example.com",
            action_type="READ",
            target_id="target-1",
            resource_id="resource-1",
            human_approved=True,
            approver_id="human-1",
            allowed_domains=["example.com"],
            prohibited_actions=["EXPLOIT"],
            known_targets=[],
            locked_resources=["resource-1"],
        )
        assert not result.all_passed
        assert result.blocked_by == BrowserSafetyCheck.MUTEX
    
    def test_blocked_by_human_approval(self):
        result = check_browser_safety(
            target_url="https://example.com",
            action_type="READ",
            target_id="target-1",
            resource_id="resource-1",
            human_approved=False,
            approver_id=None,
            allowed_domains=["example.com"],
            prohibited_actions=["EXPLOIT"],
            known_targets=[],
            locked_resources=[],
        )
        assert not result.all_passed
        assert result.blocked_by == BrowserSafetyCheck.HUMAN_APPROVAL
    
    def test_result_has_id(self):
        result = check_browser_safety(
            target_url="https://example.com",
            action_type="READ",
            target_id="t1",
            resource_id="r1",
            human_approved=True,
            approver_id="h1",
            allowed_domains=["example.com"],
            prohibited_actions=[],
            known_targets=[],
            locked_resources=[],
        )
        assert result.result_id.startswith("SAF-")
