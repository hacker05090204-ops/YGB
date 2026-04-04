# Phase-38 Tests: Browser Types and Validation
"""
Tests for Phase-38 browser governance types and validation.
100% coverage required.
Negative paths dominate.
"""

import pytest
from enum import Enum

from impl_v1.phase38.browser_types import (
    # Enums
    BrowserType,
    BrowserAction,
    BrowserDecision,
    BrowserDenialReason,
    BrowserScope,
    TabIsolation,
    StoragePolicy,
    ActionState,
    # Dataclasses
    BrowserIntent,
    BrowserResponse,
    BrowserValidationResult,
)

from impl_v1.phase38.browser_validator import (
    get_action_state,
    validate_url,
    validate_url_in_scope,
    validate_intent_id,
    validate_browser_intent,
    browser_type_requires_escalate,
    scope_requires_escalate,
    is_browser_type_allowed,
    NEVER_ACTIONS,
    ESCALATE_ACTIONS,
    ALLOW_ACTIONS,
)


# =============================================================================
# FIXTURES
# =============================================================================

def make_valid_intent(
    intent_id: str = "INT-0123456789ABCDEF",
    action: BrowserAction = BrowserAction.NAVIGATE,
    url: str = "https://example.com",
    browser_type: BrowserType = BrowserType.HEADLESS,
    scope: BrowserScope = BrowserScope.SINGLE_PAGE,
) -> BrowserIntent:
    """Create a valid browser intent for testing."""
    return BrowserIntent(
        intent_id=intent_id,
        browser_type=browser_type,
        action=action,
        target_url=url,
        scope=scope,
        tab_isolation=TabIsolation.ISOLATED,
        storage_policy=StoragePolicy.NO_STORAGE,
        description="Test browser intent",
        timestamp="2026-01-27T00:00:00Z",
        context_hash="a" * 64,
        requester_id="test-requester"
    )


# =============================================================================
# ENUM CLOSURE TESTS
# =============================================================================

class TestEnumClosure:
    """Verify all enums are CLOSED with exact member counts."""
    
    def test_browser_type_has_3_members(self):
        """BrowserType must have exactly 3 members."""
        assert len(BrowserType) == 3
    
    def test_browser_action_has_8_members(self):
        """BrowserAction must have exactly 8 members."""
        assert len(BrowserAction) == 8
    
    def test_browser_decision_has_4_members(self):
        """BrowserDecision must have exactly 4 members."""
        assert len(BrowserDecision) == 4
    
    def test_browser_denial_reason_has_12_members(self):
        """BrowserDenialReason must have exactly 12 members."""
        assert len(BrowserDenialReason) == 12
    
    def test_browser_scope_has_5_members(self):
        """BrowserScope must have exactly 5 members."""
        assert len(BrowserScope) == 5
    
    def test_tab_isolation_has_3_members(self):
        """TabIsolation must have exactly 3 members."""
        assert len(TabIsolation) == 3
    
    def test_storage_policy_has_4_members(self):
        """StoragePolicy must have exactly 4 members."""
        assert len(StoragePolicy) == 4
    
    def test_action_state_has_3_members(self):
        """ActionState must have exactly 3 members."""
        assert len(ActionState) == 3


# =============================================================================
# DATACLASS FROZEN TESTS
# =============================================================================

class TestDataclassFrozen:
    """Verify all dataclasses are frozen (immutable)."""
    
    def test_browser_intent_is_frozen(self):
        """BrowserIntent must be frozen."""
        intent = make_valid_intent()
        with pytest.raises(AttributeError):
            intent.target_url = "https://evil.com"
    
    def test_browser_response_is_frozen(self):
        """BrowserResponse must be frozen."""
        response = BrowserResponse(
            intent_id="INT-0123456789ABCDEF",
            decision=BrowserDecision.DENY,
            reason_code="TEST",
            reason_description="test",
            simulated_result=False,
            requires_human=False
        )
        with pytest.raises(AttributeError):
            response.decision = BrowserDecision.ALLOW


# =============================================================================
# ACTION STATE TESTS
# =============================================================================

class TestActionState:
    """Test action state classification."""
    
    def test_never_actions(self):
        """EXECUTE_SCRIPT and DOWNLOAD are NEVER."""
        assert get_action_state(BrowserAction.EXECUTE_SCRIPT) == ActionState.NEVER
        assert get_action_state(BrowserAction.DOWNLOAD) == ActionState.NEVER
    
    def test_escalate_actions(self):
        """COOKIE_ACCESS and STORAGE_ACCESS require ESCALATE."""
        assert get_action_state(BrowserAction.COOKIE_ACCESS) == ActionState.ESCALATE
        assert get_action_state(BrowserAction.STORAGE_ACCESS) == ActionState.ESCALATE
    
    def test_allow_actions(self):
        """NAVIGATE, CLICK, TYPE, SCREENSHOT are ALLOW."""
        assert get_action_state(BrowserAction.NAVIGATE) == ActionState.ALLOW
        assert get_action_state(BrowserAction.CLICK) == ActionState.ALLOW
        assert get_action_state(BrowserAction.TYPE) == ActionState.ALLOW
        assert get_action_state(BrowserAction.SCREENSHOT) == ActionState.ALLOW
    
    def test_never_actions_set(self):
        """NEVER_ACTIONS contains correct actions."""
        assert BrowserAction.EXECUTE_SCRIPT in NEVER_ACTIONS
        assert BrowserAction.DOWNLOAD in NEVER_ACTIONS
        assert len(NEVER_ACTIONS) == 2


# =============================================================================
# URL VALIDATION TESTS
# =============================================================================

class TestUrlValidation:
    """Test URL validation."""
    
    def test_valid_https_url(self):
        """Valid HTTPS URL passes."""
        assert validate_url("https://example.com") is True
        assert validate_url("https://example.com/path") is True
        assert validate_url("https://sub.example.com:8080/path?q=1") is True
    
    def test_valid_http_url(self):
        """Valid HTTP URL passes."""
        assert validate_url("http://example.com") is True
    
    def test_invalid_url_empty(self):
        """Empty URL fails."""
        assert validate_url("") is False
        assert validate_url(None) is False
    
    def test_blocked_schemes(self):
        """Blocked schemes fail."""
        assert validate_url("javascript:alert(1)") is False
        assert validate_url("file:///etc/passwd") is False
        assert validate_url("data:text/html,<h1>X</h1>") is False
        assert validate_url("chrome://settings") is False
    
    def test_blocked_domains(self):
        """Blocked domains fail."""
        assert validate_url("https://localhost") is False
        assert validate_url("https://127.0.0.1") is False
        assert validate_url("https://0.0.0.0") is False


# =============================================================================
# INTENT ID VALIDATION TESTS
# =============================================================================

class TestIntentIdValidation:
    """Test intent ID format validation."""
    
    def test_valid_intent_id(self):
        """Valid INT-[16 hex chars] format passes."""
        assert validate_intent_id("INT-0123456789ABCDEF") is True
    
    def test_invalid_intent_id(self):
        """Invalid intent IDs fail."""
        assert validate_intent_id("") is False
        assert validate_intent_id("REQ-0123456789ABCDEF") is False
        assert validate_intent_id("INT-0123") is False


# =============================================================================
# BROWSER TYPE / SCOPE TESTS
# =============================================================================

class TestBrowserTypeScope:
    """Test browser type and scope escalation."""
    
    def test_headed_requires_escalate(self):
        """HEADED browser requires human."""
        assert browser_type_requires_escalate(BrowserType.HEADED) is True
        assert browser_type_requires_escalate(BrowserType.HEADLESS) is False
    
    def test_forbidden_browser_not_allowed(self):
        """FORBIDDEN browser is not allowed."""
        assert is_browser_type_allowed(BrowserType.FORBIDDEN) is False
        assert is_browser_type_allowed(BrowserType.HEADLESS) is True
    
    def test_unbounded_scope_requires_escalate(self):
        """UNBOUNDED scope requires human."""
        assert scope_requires_escalate(BrowserScope.UNBOUNDED) is True
        assert scope_requires_escalate(BrowserScope.SINGLE_PAGE) is False


# =============================================================================
# FULL VALIDATION TESTS
# =============================================================================

class TestFullValidation:
    """Test full browser intent validation."""
    
    def test_valid_intent_passes(self):
        """Valid intent passes all checks."""
        intent = make_valid_intent()
        result = validate_browser_intent(intent)
        assert result.is_valid is True
    
    def test_never_action_denied(self):
        """NEVER action is denied."""
        intent = make_valid_intent(action=BrowserAction.EXECUTE_SCRIPT)
        result = validate_browser_intent(intent)
        assert result.is_valid is False
        assert result.denial_reason == BrowserDenialReason.FORBIDDEN_ACTION
    
    def test_invalid_url_denied(self):
        """Invalid URL is denied."""
        intent = make_valid_intent(url="javascript:alert(1)")
        result = validate_browser_intent(intent)
        assert result.is_valid is False
        assert result.denial_reason == BrowserDenialReason.INVALID_URL
    
    def test_forbidden_browser_denied(self):
        """FORBIDDEN browser is denied."""
        intent = make_valid_intent(browser_type=BrowserType.FORBIDDEN)
        result = validate_browser_intent(intent)
        assert result.is_valid is False
    
    def test_invalid_intent_id_denied(self):
        """Invalid intent ID is denied."""
        intent = make_valid_intent(intent_id="INVALID")
        result = validate_browser_intent(intent)
        assert result.is_valid is False
        assert result.denial_reason == BrowserDenialReason.MALFORMED_REQUEST


# =============================================================================
# NEGATIVE PATH TESTS
# =============================================================================

class TestNegativePaths:
    """Test denial paths dominate."""
    
    def test_all_never_actions_denied(self):
        """All NEVER actions are denied."""
        for action in NEVER_ACTIONS:
            intent = make_valid_intent(
                intent_id=f"INT-{action.value[:12]:0<16}"[:20],
                action=action
            )
            result = validate_browser_intent(intent)
            assert result.is_valid is False, f"{action} should be denied"
    
    def test_all_blocked_urls_denied(self):
        """All blocked URL schemes are denied."""
        blocked = ["javascript:x", "file:///x", "data:x", "chrome://x"]
        for url in blocked:
            intent = make_valid_intent(url=url)
            result = validate_browser_intent(intent)
            assert result.is_valid is False, f"URL {url} should be denied"
