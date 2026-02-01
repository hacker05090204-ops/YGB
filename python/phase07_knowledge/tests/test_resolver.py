"""
Tests for resolve_bug_info function - Phase-07.

Tests verify:
- No guessing allowed
- Unknown bugs return explicit UNKNOWN
- Explanations are deterministic
- Hindi explanations exist
- No forbidden imports
- No phase08+ imports
"""

import pytest
import os


class TestResolverExists:
    """Test resolver function exists."""
    
    def test_resolve_bug_info_exists(self):
        """resolve_bug_info function must exist."""
        from python.phase07_knowledge.resolver import resolve_bug_info
        assert resolve_bug_info is not None
        assert callable(resolve_bug_info)


class TestKnownBugResolution:
    """Test known bug types are resolved correctly."""
    
    def test_resolve_xss(self):
        """XSS type returns correct explanation."""
        from python.phase07_knowledge.resolver import resolve_bug_info
        from python.phase07_knowledge.bug_types import BugType
        
        result = resolve_bug_info(BugType.XSS)
        
        assert result.bug_type == BugType.XSS
        assert "XSS" in result.title_en or "Cross" in result.title_en
        assert len(result.title_hi) > 0  # Hindi must exist
        assert len(result.steps_en) > 0  # Steps must exist
    
    def test_resolve_sqli(self):
        """SQLI type returns correct explanation."""
        from python.phase07_knowledge.resolver import resolve_bug_info
        from python.phase07_knowledge.bug_types import BugType
        
        result = resolve_bug_info(BugType.SQLI)
        
        assert result.bug_type == BugType.SQLI
        assert result.cwe_id is not None


class TestUnknownBugResolution:
    """Test unknown bugs return UNKNOWN explicitly."""
    
    def test_unknown_returns_unknown_type(self):
        """UNKNOWN bug type returns UNKNOWN explanation."""
        from python.phase07_knowledge.resolver import resolve_bug_info
        from python.phase07_knowledge.bug_types import BugType
        from python.phase07_knowledge.knowledge_sources import KnowledgeSource
        
        result = resolve_bug_info(BugType.UNKNOWN)
        
        assert result.bug_type == BugType.UNKNOWN
        assert result.source == KnowledgeSource.UNKNOWN
    
    def test_unknown_has_explicit_message(self):
        """UNKNOWN explanation has explicit unknown message."""
        from python.phase07_knowledge.resolver import resolve_bug_info
        from python.phase07_knowledge.bug_types import BugType
        
        result = resolve_bug_info(BugType.UNKNOWN)
        
        assert "unknown" in result.title_en.lower() or "Unknown" in result.title_en


class TestNoGuessing:
    """Test that resolver never guesses."""
    
    def test_lookup_unknown_string_returns_unknown(self):
        """Lookup unknown string returns UNKNOWN type."""
        from python.phase07_knowledge.bug_types import lookup_bug_type, BugType
        from python.phase07_knowledge.resolver import resolve_bug_info
        
        bug_type = lookup_bug_type("made_up_vulnerability")
        result = resolve_bug_info(bug_type)
        
        assert result.bug_type == BugType.UNKNOWN
    
    def test_no_fabricated_cwe(self):
        """UNKNOWN explanation has no fabricated CWE."""
        from python.phase07_knowledge.resolver import resolve_bug_info
        from python.phase07_knowledge.bug_types import BugType
        
        result = resolve_bug_info(BugType.UNKNOWN)
        
        assert result.cwe_id is None


class TestDeterminism:
    """Test that explanations are deterministic."""
    
    def test_same_input_same_output(self):
        """Same input always gives same output."""
        from python.phase07_knowledge.resolver import resolve_bug_info
        from python.phase07_knowledge.bug_types import BugType
        
        result1 = resolve_bug_info(BugType.XSS)
        result2 = resolve_bug_info(BugType.XSS)
        
        assert result1 == result2
    
    def test_unknown_is_deterministic(self):
        """UNKNOWN always returns same explanation."""
        from python.phase07_knowledge.resolver import resolve_bug_info
        from python.phase07_knowledge.bug_types import BugType
        
        result1 = resolve_bug_info(BugType.UNKNOWN)
        result2 = resolve_bug_info(BugType.UNKNOWN)
        
        assert result1 == result2


class TestBilingualSupport:
    """Test Hindi and English explanations exist."""
    
    def test_xss_has_hindi(self):
        """XSS explanation has Hindi fields."""
        from python.phase07_knowledge.resolver import resolve_bug_info
        from python.phase07_knowledge.bug_types import BugType
        
        result = resolve_bug_info(BugType.XSS)
        
        assert len(result.title_hi) > 0
        assert len(result.description_hi) > 0
        assert len(result.impact_hi) > 0
        assert len(result.steps_hi) > 0
    
    def test_unknown_has_hindi(self):
        """UNKNOWN explanation has Hindi fields."""
        from python.phase07_knowledge.resolver import resolve_bug_info
        from python.phase07_knowledge.bug_types import BugType
        
        result = resolve_bug_info(BugType.UNKNOWN)
        
        assert len(result.title_hi) > 0


class TestNoForbiddenImports:
    """Test no forbidden imports in resolver."""
    
    def test_no_os_import(self):
        """No os import in resolver.py."""
        resolver_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            'resolver.py'
        )
        with open(resolver_path, 'r', encoding='utf-8') as f:
            content = f.read()
        assert 'import os' not in content
    
    def test_no_subprocess_import(self):
        """No subprocess import."""
        resolver_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            'resolver.py'
        )
        with open(resolver_path, 'r', encoding='utf-8') as f:
            content = f.read()
        assert 'import subprocess' not in content
    
    def test_no_requests_import(self):
        """No requests import."""
        resolver_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            'resolver.py'
        )
        with open(resolver_path, 'r', encoding='utf-8') as f:
            content = f.read()
        assert 'import requests' not in content
    
    def test_no_selenium_import(self):
        """No selenium import."""
        resolver_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            'resolver.py'
        )
        with open(resolver_path, 'r', encoding='utf-8') as f:
            content = f.read()
        assert 'import selenium' not in content


class TestNoFuturePhaseCoupling:
    """Test no phase08+ imports."""
    
    def test_no_phase08_import(self):
        """No phase08 imports in any Phase-07 file."""
        phase07_dir = os.path.dirname(os.path.dirname(__file__))
        for filename in os.listdir(phase07_dir):
            if filename.endswith('.py'):
                filepath = os.path.join(phase07_dir, filename)
                with open(filepath, 'r', encoding='utf-8') as f:
                    content = f.read().lower()
                assert 'phase08' not in content, f"Found phase08 in {filename}"
                assert 'phase09' not in content, f"Found phase09 in {filename}"
