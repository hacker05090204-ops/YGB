# test_g02_browser_types.py
"""Tests for G02: Browser Engine Types"""

import pytest
from impl_v1.phase49.governors.g02_browser_types import (
    BrowserType,
    BrowserLaunchMode,
    BrowserRequestStatus,
    BrowserLaunchRequest,
    BrowserLaunchResult,
    validate_launch_request,
    create_launch_result,
)


class TestEnumClosure:
    """Verify enums are closed."""
    
    def test_browser_type_2_members(self):
        assert len(BrowserType) == 2
    
    def test_launch_mode_2_members(self):
        assert len(BrowserLaunchMode) == 2
    
    def test_request_status_4_members(self):
        assert len(BrowserRequestStatus) == 4


class TestDataclassFrozen:
    """Verify dataclasses are frozen."""
    
    def test_launch_request_frozen(self):
        request = BrowserLaunchRequest(
            request_id="REQ-1",
            browser_type=BrowserType.UNGOOGLED_CHROMIUM,
            mode=BrowserLaunchMode.HEADED,
            target_url="https://example.com",
            scope_check_passed=True,
            ethics_check_passed=True,
            duplicate_check_passed=True,
            mutex_check_passed=True,
            human_approved=True,
            reason="test",
        )
        with pytest.raises(AttributeError):
            request.request_id = "NEW"
    
    def test_launch_result_frozen(self):
        result = BrowserLaunchResult(
            request_id="REQ-1",
            status=BrowserRequestStatus.APPROVED,
            browser_type=BrowserType.UNGOOGLED_CHROMIUM,
            mode=BrowserLaunchMode.HEADED,
            error_message=None,
            fallback_used=False,
            fallback_reason=None,
        )
        with pytest.raises(AttributeError):
            result.status = BrowserRequestStatus.FAILED


class TestValidateLaunchRequest:
    """Test launch request validation."""
    
    def test_valid_request(self):
        request = BrowserLaunchRequest(
            request_id="REQ-1",
            browser_type=BrowserType.UNGOOGLED_CHROMIUM,
            mode=BrowserLaunchMode.HEADED,
            target_url="https://example.com",
            scope_check_passed=True,
            ethics_check_passed=True,
            duplicate_check_passed=True,
            mutex_check_passed=True,
            human_approved=True,
            reason="test",
        )
        is_valid, reason = validate_launch_request(request)
        assert is_valid
        assert reason == "All checks passed"
    
    def test_scope_check_failed(self):
        request = BrowserLaunchRequest(
            request_id="REQ-1",
            browser_type=BrowserType.UNGOOGLED_CHROMIUM,
            mode=BrowserLaunchMode.HEADED,
            target_url="https://example.com",
            scope_check_passed=False,
            ethics_check_passed=True,
            duplicate_check_passed=True,
            mutex_check_passed=True,
            human_approved=True,
            reason="",
        )
        is_valid, reason = validate_launch_request(request)
        assert not is_valid
        assert "Scope" in reason
    
    def test_ethics_check_failed(self):
        request = BrowserLaunchRequest(
            request_id="REQ-1",
            browser_type=BrowserType.UNGOOGLED_CHROMIUM,
            mode=BrowserLaunchMode.HEADED,
            target_url="https://example.com",
            scope_check_passed=True,
            ethics_check_passed=False,
            duplicate_check_passed=True,
            mutex_check_passed=True,
            human_approved=True,
            reason="",
        )
        is_valid, reason = validate_launch_request(request)
        assert not is_valid
        assert "Ethics" in reason
    
    def test_duplicate_check_failed(self):
        request = BrowserLaunchRequest(
            request_id="REQ-1",
            browser_type=BrowserType.UNGOOGLED_CHROMIUM,
            mode=BrowserLaunchMode.HEADED,
            target_url="https://example.com",
            scope_check_passed=True,
            ethics_check_passed=True,
            duplicate_check_passed=False,
            mutex_check_passed=True,
            human_approved=True,
            reason="",
        )
        is_valid, reason = validate_launch_request(request)
        assert not is_valid
        assert "Duplicate" in reason
    
    def test_mutex_check_failed(self):
        request = BrowserLaunchRequest(
            request_id="REQ-1",
            browser_type=BrowserType.UNGOOGLED_CHROMIUM,
            mode=BrowserLaunchMode.HEADED,
            target_url="https://example.com",
            scope_check_passed=True,
            ethics_check_passed=True,
            duplicate_check_passed=True,
            mutex_check_passed=False,
            human_approved=True,
            reason="",
        )
        is_valid, reason = validate_launch_request(request)
        assert not is_valid
        assert "Mutex" in reason
    
    def test_human_approval_required(self):
        request = BrowserLaunchRequest(
            request_id="REQ-1",
            browser_type=BrowserType.UNGOOGLED_CHROMIUM,
            mode=BrowserLaunchMode.HEADED,
            target_url="https://example.com",
            scope_check_passed=True,
            ethics_check_passed=True,
            duplicate_check_passed=True,
            mutex_check_passed=True,
            human_approved=False,
            reason="",
        )
        is_valid, reason = validate_launch_request(request)
        assert not is_valid
        assert "Human" in reason
    
    def test_headless_requires_reason(self):
        request = BrowserLaunchRequest(
            request_id="REQ-1",
            browser_type=BrowserType.UNGOOGLED_CHROMIUM,
            mode=BrowserLaunchMode.HEADLESS,
            target_url="https://example.com",
            scope_check_passed=True,
            ethics_check_passed=True,
            duplicate_check_passed=True,
            mutex_check_passed=True,
            human_approved=True,
            reason="",  # Empty reason
        )
        is_valid, reason = validate_launch_request(request)
        assert not is_valid
        assert "Headless" in reason


class TestCreateLaunchResult:
    """Test result creation."""
    
    def test_success_result(self):
        request = BrowserLaunchRequest(
            request_id="REQ-1",
            browser_type=BrowserType.UNGOOGLED_CHROMIUM,
            mode=BrowserLaunchMode.HEADED,
            target_url="https://example.com",
            scope_check_passed=True,
            ethics_check_passed=True,
            duplicate_check_passed=True,
            mutex_check_passed=True,
            human_approved=True,
            reason="",
        )
        result = create_launch_result(request, success=True)
        assert result.status == BrowserRequestStatus.APPROVED
        assert result.browser_type == BrowserType.UNGOOGLED_CHROMIUM
    
    def test_failure_result(self):
        request = BrowserLaunchRequest(
            request_id="REQ-1",
            browser_type=BrowserType.UNGOOGLED_CHROMIUM,
            mode=BrowserLaunchMode.HEADED,
            target_url="https://example.com",
            scope_check_passed=True,
            ethics_check_passed=True,
            duplicate_check_passed=True,
            mutex_check_passed=True,
            human_approved=True,
            reason="",
        )
        result = create_launch_result(request, success=False, error="Browser crashed")
        assert result.status == BrowserRequestStatus.FAILED
        assert result.error_message == "Browser crashed"
