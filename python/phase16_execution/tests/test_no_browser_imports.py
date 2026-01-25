"""
Tests for Phase-16 No Browser Imports.

Tests:
- No browser imports (playwright, selenium)
- No execution imports (subprocess, os)
"""
import pytest


class TestNoForbiddenImports:
    """Test no forbidden imports."""

    def test_no_playwright_import(self):
        """No playwright import."""
        import python.phase16_execution.execution_engine as module
        import inspect
        source = inspect.getsource(module)
        assert 'playwright' not in source

    def test_no_selenium_import(self):
        """No selenium import."""
        import python.phase16_execution.execution_engine as module
        import inspect
        source = inspect.getsource(module)
        assert 'selenium' not in source

    def test_no_subprocess_import(self):
        """No subprocess import."""
        import python.phase16_execution.execution_engine as module
        import inspect
        source = inspect.getsource(module)
        assert 'import subprocess' not in source

    def test_no_os_system_import(self):
        """No os import."""
        import python.phase16_execution.execution_engine as module
        import inspect
        source = inspect.getsource(module)
        assert 'import os' not in source

    def test_no_phase17_import(self):
        """No phase17+ imports."""
        import os
        module_dir = os.path.dirname(__file__).replace('/tests', '')
        for filename in os.listdir(module_dir):
            if filename.endswith('.py'):
                filepath = os.path.join(module_dir, filename)
                with open(filepath, 'r') as f:
                    content = f.read()
                    assert 'phase17' not in content


class TestEnumCounts:
    """Test enum member counts."""

    def test_execution_permission_has_two_members(self):
        """ExecutionPermission has exactly 2 members."""
        from python.phase16_execution.execution_types import ExecutionPermission
        assert len(ExecutionPermission) == 2
