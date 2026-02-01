"""
Tests for Phase-22 No Browser Imports.

Tests:
- No browser imports (playwright, selenium)
- No execution imports (subprocess, os)
- No phase23+ imports
"""
import pytest


class TestNoForbiddenImports:
    """Test no forbidden imports."""

    def test_no_playwright_import(self):
        """No playwright import."""
        import HUMANOID_HUNTER.native.native_engine as module
        import inspect
        source = inspect.getsource(module)
        assert 'playwright' not in source

    def test_no_selenium_import(self):
        """No selenium import."""
        import HUMANOID_HUNTER.native.native_engine as module
        import inspect
        source = inspect.getsource(module)
        assert 'selenium' not in source

    def test_no_subprocess_import(self):
        """No subprocess import."""
        import HUMANOID_HUNTER.native.native_engine as module
        import inspect
        source = inspect.getsource(module)
        assert 'import subprocess' not in source

    def test_no_os_import(self):
        """No os import."""
        import HUMANOID_HUNTER.native.native_engine as module
        import inspect
        source = inspect.getsource(module)
        assert 'import os' not in source

    def test_no_phase23_import(self):
        """No phase23+ imports."""
        import os
        module_dir = os.path.dirname(__file__).replace('/tests', '')
        for filename in os.listdir(module_dir):
            if filename.endswith('.py'):
                filepath = os.path.join(module_dir, filename)
                with open(filepath, 'r') as f:
                    content = f.read()
                    assert 'phase23' not in content


class TestEnumCounts:
    """Test enum member counts."""

    def test_native_process_state_has_six_members(self):
        """NativeProcessState has exactly 6 members."""
        from HUMANOID_HUNTER.native.native_types import NativeProcessState
        assert len(NativeProcessState) == 6

    def test_native_exit_reason_has_six_members(self):
        """NativeExitReason has exactly 6 members."""
        from HUMANOID_HUNTER.native.native_types import NativeExitReason
        assert len(NativeExitReason) == 6

    def test_isolation_decision_has_three_members(self):
        """IsolationDecision has exactly 3 members."""
        from HUMANOID_HUNTER.native.native_types import IsolationDecision
        assert len(IsolationDecision) == 3
