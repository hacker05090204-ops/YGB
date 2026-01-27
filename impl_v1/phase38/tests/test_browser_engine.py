# Phase-38 Tests: Browser Engine
"""
Tests for Phase-38 browser decision engine.
100% coverage required.
Negative paths dominate.
"""

import pytest

from impl_v1.phase38.browser_types import (
    BrowserIntent,
    BrowserDecision,
    BrowserDenialReason,
    BrowserType,
    BrowserAction,
    BrowserScope,
    TabIsolation,
    StoragePolicy,
)

from impl_v1.phase38.browser_engine import (
    make_browser_decision,
    create_browser_audit_entry,
    check_navigation_scope,
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
    tab_isolation: TabIsolation = TabIsolation.ISOLATED,
    storage_policy: StoragePolicy = StoragePolicy.NO_STORAGE,
) -> BrowserIntent:
    """Create a valid browser intent for testing."""
    return BrowserIntent(
        intent_id=intent_id,
        browser_type=browser_type,
        action=action,
        target_url=url,
        scope=scope,
        tab_isolation=tab_isolation,
        storage_policy=storage_policy,
        description="Test browser intent",
        timestamp="2026-01-27T00:00:00Z",
        context_hash="a" * 64,
        requester_id="test-requester"
    )


# =============================================================================
# DECISION ENGINE TESTS
# =============================================================================

class TestDecisionEngine:
    """Test browser decision making."""
    
    def test_valid_allow_action_granted(self):
        """Valid ALLOW action is allowed."""
        intent = make_valid_intent(action=BrowserAction.NAVIGATE)
        response = make_browser_decision(intent)
        
        assert response.decision == BrowserDecision.ALLOW
        assert response.simulated_result is True
        assert response.requires_human is False
    
    def test_never_action_denied(self):
        """NEVER action is immediately denied."""
        intent = make_valid_intent(action=BrowserAction.EXECUTE_SCRIPT)
        response = make_browser_decision(intent)
        
        assert response.decision == BrowserDecision.DENY
        assert response.reason_code == BrowserDenialReason.FORBIDDEN_ACTION.value
    
    def test_escalate_action_pending(self):
        """ESCALATE action goes to PENDING."""
        intent = make_valid_intent(action=BrowserAction.COOKIE_ACCESS)
        response = make_browser_decision(intent)
        
        assert response.decision == BrowserDecision.PENDING
        assert response.requires_human is True
    
    def test_headed_browser_pending(self):
        """HEADED browser requires escalation."""
        intent = make_valid_intent(browser_type=BrowserType.HEADED)
        response = make_browser_decision(intent)
        
        assert response.decision == BrowserDecision.PENDING
        assert response.requires_human is True
    
    def test_unbounded_scope_pending(self):
        """UNBOUNDED scope requires escalation."""
        intent = make_valid_intent(scope=BrowserScope.UNBOUNDED)
        response = make_browser_decision(intent)
        
        assert response.decision == BrowserDecision.PENDING
        assert response.requires_human is True
    
    def test_human_approved_allowed(self):
        """Human approval allows the intent."""
        intent = make_valid_intent(browser_type=BrowserType.HEADED)
        response = make_browser_decision(intent, human_approved=True)
        
        assert response.decision == BrowserDecision.ALLOW
        assert response.reason_code == "HUMAN_APPROVED"
    
    def test_human_denied(self):
        """Human denial rejects the intent."""
        intent = make_valid_intent(browser_type=BrowserType.HEADED)
        response = make_browser_decision(intent, human_approved=False)
        
        assert response.decision == BrowserDecision.DENY
        assert response.reason_code == BrowserDenialReason.HUMAN_DENIED.value


# =============================================================================
# ESCALATION TESTS
# =============================================================================

class TestEscalation:
    """Test escalation conditions."""
    
    def test_shared_context_escalates(self):
        """SHARED_CONTEXT tab isolation requires escalation."""
        intent = make_valid_intent(tab_isolation=TabIsolation.SHARED_CONTEXT)
        response = make_browser_decision(intent)
        
        assert response.decision == BrowserDecision.PENDING
        assert response.requires_human is True
    
    def test_persistent_storage_denied(self):
        """PERSISTENT storage is denied (not escalated)."""
        intent = make_valid_intent(storage_policy=StoragePolicy.PERSISTENT)
        response = make_browser_decision(intent)
        
        # PERSISTENT is not allowed, so validation fails
        assert response.decision == BrowserDecision.DENY


# =============================================================================
# AUDIT ENTRY TESTS
# =============================================================================

class TestAuditEntry:
    """Test audit entry creation."""
    
    def test_audit_entry_created(self):
        """Audit entry is created with correct fields."""
        intent = make_valid_intent()
        entry = create_browser_audit_entry(
            intent,
            BrowserDecision.ALLOW,
            "VALIDATED"
        )
        
        assert entry.intent_id == intent.intent_id
        assert entry.action == intent.action
        assert entry.target_url == intent.target_url
        assert entry.decision == BrowserDecision.ALLOW
        assert entry.audit_id.startswith("BAUD-")


# =============================================================================
# NAVIGATION SCOPE TESTS
# =============================================================================

class TestNavigationScope:
    """Test navigation scope checking."""
    
    def test_single_page_first_navigation(self):
        """SINGLE_PAGE allows first navigation."""
        assert check_navigation_scope(
            "",
            "https://example.com",
            BrowserScope.SINGLE_PAGE
        ) is True
    
    def test_single_page_second_navigation_denied(self):
        """SINGLE_PAGE denies second navigation."""
        assert check_navigation_scope(
            "https://example.com",
            "https://other.com",
            BrowserScope.SINGLE_PAGE
        ) is False
    
    def test_single_domain_same_domain(self):
        """SINGLE_DOMAIN allows same domain navigation."""
        assert check_navigation_scope(
            "https://example.com/page1",
            "https://example.com/page2",
            BrowserScope.SINGLE_DOMAIN,
            first_domain="example.com"
        ) is True
    
    def test_single_domain_different_domain_denied(self):
        """SINGLE_DOMAIN denies different domain."""
        assert check_navigation_scope(
            "https://example.com",
            "https://other.com",
            BrowserScope.SINGLE_DOMAIN,
            first_domain="example.com"
        ) is False


# =============================================================================
# NEGATIVE PATH TESTS
# =============================================================================

class TestNegativePaths:
    """Test denial paths dominate."""
    
    def test_all_never_actions_denied(self):
        """All NEVER actions are denied."""
        never_actions = [BrowserAction.EXECUTE_SCRIPT, BrowserAction.DOWNLOAD]
        
        for action in never_actions:
            intent = make_valid_intent(action=action)
            response = make_browser_decision(intent)
            assert response.decision == BrowserDecision.DENY, f"{action} should be denied"
    
    def test_invalid_url_denied(self):
        """Invalid URL is denied."""
        intent = make_valid_intent(url="javascript:alert(1)")
        response = make_browser_decision(intent)
        assert response.decision == BrowserDecision.DENY
    
    def test_forbidden_browser_denied(self):
        """FORBIDDEN browser is denied."""
        intent = make_valid_intent(browser_type=BrowserType.FORBIDDEN)
        response = make_browser_decision(intent)
        assert response.decision == BrowserDecision.DENY
    
    def test_forbidden_tab_isolation_denied(self):
        """FORBIDDEN tab isolation is denied."""
        intent = make_valid_intent(tab_isolation=TabIsolation.FORBIDDEN)
        response = make_browser_decision(intent)
        assert response.decision == BrowserDecision.DENY
    
    def test_simulated_result_false_on_deny(self):
        """Simulated result is False when denied."""
        intent = make_valid_intent(action=BrowserAction.EXECUTE_SCRIPT)
        response = make_browser_decision(intent)
        
        assert response.decision == BrowserDecision.DENY
        assert response.simulated_result is False
    
    def test_simulated_result_true_on_allow(self):
        """Simulated result is True when allowed."""
        intent = make_valid_intent()
        response = make_browser_decision(intent)
        
        assert response.decision == BrowserDecision.ALLOW
        assert response.simulated_result is True
