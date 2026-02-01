# Phase-38 Additional Coverage Tests
"""Additional tests for full coverage."""

import pytest

from impl_v1.phase38.browser_types import (
    BrowserIntent,
    BrowserType,
    BrowserAction,
    BrowserScope,
    TabIsolation,
    StoragePolicy,
)

from impl_v1.phase38.browser_validator import (
    validate_url,
    validate_url_in_scope,
    is_storage_allowed,
    is_tab_isolation_allowed,
    storage_requires_escalate,
    tab_isolation_requires_escalate,
)

from impl_v1.phase38.browser_engine import (
    check_navigation_scope,
)


class TestAdditionalBrowserCoverage:
    """Additional coverage tests."""
    
    def test_session_scope_navigation(self):
        """SESSION scope allows navigation."""
        result = check_navigation_scope(
            "https://example.com",
            "https://other.com",
            BrowserScope.SESSION
        )
        assert result is True
    
    def test_allowlist_scope_navigation(self):
        """ALLOWLIST scope requires domain check."""
        # Without first domain set
        result = validate_url_in_scope(
            "https://example.com",
            BrowserScope.ALLOWLIST,
            allowed_domains=("example.com",)
        )
        assert result is True
    
    def test_storage_policies(self):
        """Test storage policy checks."""
        assert is_storage_allowed(StoragePolicy.NO_STORAGE) is True
        assert is_storage_allowed(StoragePolicy.SESSION_ONLY) is True
        assert is_storage_allowed(StoragePolicy.ENCRYPTED) is True
        assert is_storage_allowed(StoragePolicy.PERSISTENT) is False
    
    def test_storage_escalation(self):
        """Test storage escalation."""
        assert storage_requires_escalate(StoragePolicy.PERSISTENT) is True
        assert storage_requires_escalate(StoragePolicy.NO_STORAGE) is False
    
    def test_tab_isolation_allowed(self):
        """Test tab isolation checks."""
        assert is_tab_isolation_allowed(TabIsolation.ISOLATED) is True
        assert is_tab_isolation_allowed(TabIsolation.SHARED_CONTEXT) is True
        assert is_tab_isolation_allowed(TabIsolation.FORBIDDEN) is False
    
    def test_tab_isolation_escalation(self):
        """Test tab isolation escalation."""
        assert tab_isolation_requires_escalate(TabIsolation.SHARED_CONTEXT) is True
        assert tab_isolation_requires_escalate(TabIsolation.ISOLATED) is False
    
    def test_url_with_malformed_parse(self):
        """Test URL that fails parsing."""
        assert validate_url("://missing-scheme") is False
    
    def test_unbounded_scope_navigation(self):
        """UNBOUNDED scope allows all navigation."""
        result = check_navigation_scope(
            "https://example.com",
            "https://anywhere.com",
            BrowserScope.UNBOUNDED
        )
        assert result is True
    
    def test_single_domain_first_navigation(self):
        """SINGLE_DOMAIN first navigation sets domain."""
        result = check_navigation_scope(
            "",
            "https://example.com",
            BrowserScope.SINGLE_DOMAIN,
            first_domain=None
        )
        assert result is True


class TestBrowserUrlEdgeCases:
    """URL edge case tests."""
    
    def test_ftp_url_blocked(self):
        """FTP scheme is blocked."""
        assert validate_url("ftp://files.example.com") is False
    
    def test_about_url_blocked(self):
        """about: scheme is blocked."""
        assert validate_url("about:blank") is False
    
    def test_chrome_extension_blocked(self):
        """chrome-extension: is blocked."""
        assert validate_url("chrome-extension://xxx") is False
    
    def test_url_with_port(self):
        """URL with port works."""
        assert validate_url("https://example.com:8080/path") is True
