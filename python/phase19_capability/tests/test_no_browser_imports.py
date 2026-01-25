"""
Tests for Phase-19 No Browser Imports.

Tests:
- No browser imports (playwright, selenium)
- No execution imports (subprocess, os)
- No phase20+ imports
"""
import pytest


class TestNoForbiddenImports:
    """Test no forbidden imports."""

    def test_no_playwright_import(self):
        """No playwright import."""
        import python.phase19_capability.capability_engine as module
        import inspect
        source = inspect.getsource(module)
        assert 'playwright' not in source

    def test_no_selenium_import(self):
        """No selenium import."""
        import python.phase19_capability.capability_engine as module
        import inspect
        source = inspect.getsource(module)
        assert 'selenium' not in source

    def test_no_subprocess_import(self):
        """No subprocess import."""
        import python.phase19_capability.capability_engine as module
        import inspect
        source = inspect.getsource(module)
        assert 'import subprocess' not in source

    def test_no_os_import(self):
        """No os import."""
        import python.phase19_capability.capability_engine as module
        import inspect
        source = inspect.getsource(module)
        assert 'import os' not in source

    def test_no_phase20_import(self):
        """No phase20+ imports."""
        import os
        module_dir = os.path.dirname(__file__).replace('/tests', '')
        for filename in os.listdir(module_dir):
            if filename.endswith('.py'):
                filepath = os.path.join(module_dir, filename)
                with open(filepath, 'r') as f:
                    content = f.read()
                    assert 'phase20' not in content


class TestEnumCounts:
    """Test enum member counts."""

    def test_browser_action_type_has_ten_members(self):
        """BrowserActionType has exactly 10 members."""
        from python.phase19_capability.capability_types import BrowserActionType
        assert len(BrowserActionType) == 10

    def test_action_risk_level_has_four_members(self):
        """ActionRiskLevel has exactly 4 members."""
        from python.phase19_capability.capability_types import ActionRiskLevel
        assert len(ActionRiskLevel) == 4

    def test_capability_decision_has_three_members(self):
        """CapabilityDecision has exactly 3 members."""
        from python.phase19_capability.capability_types import CapabilityDecision
        assert len(CapabilityDecision) == 3
