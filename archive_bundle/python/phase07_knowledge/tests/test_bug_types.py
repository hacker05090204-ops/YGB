"""
Tests for BugType enum - Phase-07.

Tests verify:
- Enum exists with all required bug types
- Enum is closed
- UNKNOWN exists for unknown bugs
"""

import pytest
from enum import Enum


class TestBugTypeEnum:
    """Test BugType enum existence and values."""
    
    def test_bug_type_enum_exists(self):
        """BugType enum must exist."""
        from python.phase07_knowledge.bug_types import BugType
        assert BugType is not None
    
    def test_bug_type_is_enum(self):
        """BugType must be an Enum."""
        from python.phase07_knowledge.bug_types import BugType
        assert issubclass(BugType, Enum)
    
    def test_has_xss(self):
        """BugType must have XSS member."""
        from python.phase07_knowledge.bug_types import BugType
        assert hasattr(BugType, 'XSS')
        assert BugType.XSS.value == "xss"
    
    def test_has_sqli(self):
        """BugType must have SQLI member."""
        from python.phase07_knowledge.bug_types import BugType
        assert hasattr(BugType, 'SQLI')
        assert BugType.SQLI.value == "sqli"
    
    def test_has_idor(self):
        """BugType must have IDOR member."""
        from python.phase07_knowledge.bug_types import BugType
        assert hasattr(BugType, 'IDOR')
    
    def test_has_ssrf(self):
        """BugType must have SSRF member."""
        from python.phase07_knowledge.bug_types import BugType
        assert hasattr(BugType, 'SSRF')
    
    def test_has_csrf(self):
        """BugType must have CSRF member."""
        from python.phase07_knowledge.bug_types import BugType
        assert hasattr(BugType, 'CSRF')
    
    def test_has_xxe(self):
        """BugType must have XXE member."""
        from python.phase07_knowledge.bug_types import BugType
        assert hasattr(BugType, 'XXE')
    
    def test_has_path_traversal(self):
        """BugType must have PATH_TRAVERSAL member."""
        from python.phase07_knowledge.bug_types import BugType
        assert hasattr(BugType, 'PATH_TRAVERSAL')
    
    def test_has_open_redirect(self):
        """BugType must have OPEN_REDIRECT member."""
        from python.phase07_knowledge.bug_types import BugType
        assert hasattr(BugType, 'OPEN_REDIRECT')
    
    def test_has_rce(self):
        """BugType must have RCE member."""
        from python.phase07_knowledge.bug_types import BugType
        assert hasattr(BugType, 'RCE')
    
    def test_has_lfi(self):
        """BugType must have LFI member."""
        from python.phase07_knowledge.bug_types import BugType
        assert hasattr(BugType, 'LFI')
    
    def test_has_unknown(self):
        """BugType must have UNKNOWN member for unknown bugs."""
        from python.phase07_knowledge.bug_types import BugType
        assert hasattr(BugType, 'UNKNOWN')
        assert BugType.UNKNOWN.value == "unknown"
    
    def test_bug_type_is_closed(self):
        """BugType must have exactly 11 members."""
        from python.phase07_knowledge.bug_types import BugType
        assert len(BugType) == 11


class TestBugTypeLookup:
    """Test bug type lookup function."""
    
    def test_lookup_exists(self):
        """lookup_bug_type function must exist."""
        from python.phase07_knowledge.bug_types import lookup_bug_type
        assert lookup_bug_type is not None
        assert callable(lookup_bug_type)
    
    def test_lookup_xss(self):
        """Lookup 'xss' returns BugType.XSS."""
        from python.phase07_knowledge.bug_types import lookup_bug_type, BugType
        assert lookup_bug_type("xss") == BugType.XSS
    
    def test_lookup_case_insensitive(self):
        """Lookup is case insensitive."""
        from python.phase07_knowledge.bug_types import lookup_bug_type, BugType
        assert lookup_bug_type("XSS") == BugType.XSS
        assert lookup_bug_type("Xss") == BugType.XSS
    
    def test_lookup_unknown_returns_unknown(self):
        """Unknown bug name returns UNKNOWN, not guess."""
        from python.phase07_knowledge.bug_types import lookup_bug_type, BugType
        assert lookup_bug_type("foobar") == BugType.UNKNOWN
        assert lookup_bug_type("some_random_bug") == BugType.UNKNOWN
    
    def test_no_guessing(self):
        """Lookup NEVER guesses similar names."""
        from python.phase07_knowledge.bug_types import lookup_bug_type, BugType
        # These should NOT guess to XSS/SQLI etc.
        assert lookup_bug_type("cross_site") == BugType.UNKNOWN
        assert lookup_bug_type("sql") == BugType.UNKNOWN
        assert lookup_bug_type("injection") == BugType.UNKNOWN
