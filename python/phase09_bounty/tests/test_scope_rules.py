"""
Tests for scope rules - Phase-09.

Tests verify:
- In-scope assets return IN_SCOPE
- Out-of-scope assets return OUT_OF_SCOPE
- Unknown assets return OUT_OF_SCOPE (deny-by-default)
- No forbidden imports
- No phase10+ imports
"""

import pytest
import os


class TestScopeRulesExist:
    """Test scope rules function exists."""
    
    def test_check_scope_exists(self):
        """check_scope function must exist."""
        from python.phase09_bounty.scope_rules import check_scope
        assert check_scope is not None
        assert callable(check_scope)


class TestInScopeAssets:
    """Test in-scope asset types."""
    
    def test_web_app_in_scope(self):
        """WEB_APP is in scope."""
        from python.phase09_bounty.scope_rules import check_scope
        from python.phase09_bounty.bounty_types import AssetType, ScopeResult
        
        result = check_scope(AssetType.WEB_APP)
        assert result == ScopeResult.IN_SCOPE
    
    def test_api_in_scope(self):
        """API is in scope."""
        from python.phase09_bounty.scope_rules import check_scope
        from python.phase09_bounty.bounty_types import AssetType, ScopeResult
        
        result = check_scope(AssetType.API)
        assert result == ScopeResult.IN_SCOPE
    
    def test_mobile_in_scope(self):
        """MOBILE is in scope."""
        from python.phase09_bounty.scope_rules import check_scope
        from python.phase09_bounty.bounty_types import AssetType, ScopeResult
        
        result = check_scope(AssetType.MOBILE)
        assert result == ScopeResult.IN_SCOPE


class TestOutOfScopeAssets:
    """Test out-of-scope asset types."""
    
    def test_infrastructure_out_of_scope(self):
        """INFRASTRUCTURE is out of scope."""
        from python.phase09_bounty.scope_rules import check_scope
        from python.phase09_bounty.bounty_types import AssetType, ScopeResult
        
        result = check_scope(AssetType.INFRASTRUCTURE)
        assert result == ScopeResult.OUT_OF_SCOPE
    
    def test_out_of_program_out_of_scope(self):
        """OUT_OF_PROGRAM is out of scope."""
        from python.phase09_bounty.scope_rules import check_scope
        from python.phase09_bounty.bounty_types import AssetType, ScopeResult
        
        result = check_scope(AssetType.OUT_OF_PROGRAM)
        assert result == ScopeResult.OUT_OF_SCOPE


class TestDenyByDefault:
    """Test deny-by-default behavior."""
    
    def test_unknown_out_of_scope(self):
        """UNKNOWN is out of scope (deny-by-default)."""
        from python.phase09_bounty.scope_rules import check_scope
        from python.phase09_bounty.bounty_types import AssetType, ScopeResult
        
        result = check_scope(AssetType.UNKNOWN)
        assert result == ScopeResult.OUT_OF_SCOPE


class TestScopeDeterminism:
    """Test scope determination is deterministic."""
    
    def test_same_input_same_output(self):
        """Same input gives same output."""
        from python.phase09_bounty.scope_rules import check_scope
        from python.phase09_bounty.bounty_types import AssetType
        
        result1 = check_scope(AssetType.WEB_APP)
        result2 = check_scope(AssetType.WEB_APP)
        assert result1 == result2


class TestNoForbiddenImports:
    """Test no forbidden imports in scope_rules."""
    
    def test_no_os_import(self):
        """No os import in scope_rules.py."""
        scope_rules_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            'scope_rules.py'
        )
        with open(scope_rules_path, 'r', encoding='utf-8') as f:
            content = f.read()
        assert 'import os' not in content
    
    def test_no_subprocess_import(self):
        """No subprocess import."""
        scope_rules_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            'scope_rules.py'
        )
        with open(scope_rules_path, 'r', encoding='utf-8') as f:
            content = f.read()
        assert 'import subprocess' not in content
    
    def test_no_requests_import(self):
        """No requests import."""
        scope_rules_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            'scope_rules.py'
        )
        with open(scope_rules_path, 'r', encoding='utf-8') as f:
            content = f.read()
        assert 'import requests' not in content


class TestNoFuturePhaseCoupling:
    """Test no phase10+ imports."""
    
    def test_no_phase10_import(self):
        """No phase10 imports in Phase-09 files."""
        phase09_dir = os.path.dirname(os.path.dirname(__file__))
        for filename in os.listdir(phase09_dir):
            if filename.endswith('.py'):
                filepath = os.path.join(phase09_dir, filename)
                with open(filepath, 'r', encoding='utf-8') as f:
                    content = f.read().lower()
                assert 'phase10' not in content, f"Found phase10 in {filename}"
                assert 'phase11' not in content, f"Found phase11 in {filename}"
