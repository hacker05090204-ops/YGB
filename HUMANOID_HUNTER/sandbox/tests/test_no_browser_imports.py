"""
Tests for Phase-21 No Browser Imports.

Tests:
- No browser imports (playwright, selenium)
- No execution imports (subprocess, os)
- No phase22+ imports
"""
import pytest
from pathlib import Path


class TestNoForbiddenImports:
    """Test no forbidden imports."""

    def test_no_playwright_import(self):
        """No playwright import."""
        import HUMANOID_HUNTER.sandbox.sandbox_engine as module
        import inspect
        source = inspect.getsource(module)
        assert 'playwright' not in source

    def test_no_selenium_import(self):
        """No selenium import."""
        import HUMANOID_HUNTER.sandbox.sandbox_engine as module
        import inspect
        source = inspect.getsource(module)
        assert 'selenium' not in source

    def test_no_subprocess_import(self):
        """No subprocess import."""
        import HUMANOID_HUNTER.sandbox.sandbox_engine as module
        import inspect
        source = inspect.getsource(module)
        assert 'import subprocess' not in source

    def test_no_os_import(self):
        """No os import."""
        import HUMANOID_HUNTER.sandbox.sandbox_engine as module
        import inspect
        source = inspect.getsource(module)
        assert 'import os' not in source

    def test_no_phase22_import(self):
        """No phase22+ imports."""
        module_dir = Path(__file__).resolve().parents[1]
        for filepath in module_dir.glob("*.py"):
            content = filepath.read_text()
            assert 'phase22' not in content


class TestEnumCounts:
    """Test enum member counts."""

    def test_execution_fault_type_has_six_members(self):
        """ExecutionFaultType has exactly 6 members."""
        from HUMANOID_HUNTER.sandbox.sandbox_types import ExecutionFaultType
        assert len(ExecutionFaultType) == 6

    def test_sandbox_decision_has_three_members(self):
        """SandboxDecision has exactly 3 members."""
        from HUMANOID_HUNTER.sandbox.sandbox_types import SandboxDecision
        assert len(SandboxDecision) == 3

    def test_retry_policy_has_four_members(self):
        """RetryPolicy has exactly 4 members."""
        from HUMANOID_HUNTER.sandbox.sandbox_types import RetryPolicy
        assert len(RetryPolicy) == 4
