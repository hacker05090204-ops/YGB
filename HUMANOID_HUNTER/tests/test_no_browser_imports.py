"""
Tests for Phase-20 No Browser Imports.

Tests:
- No browser imports (playwright, selenium)
- No execution imports (subprocess, os)
- No phase21+ imports
"""
import pytest
from pathlib import Path


class TestNoForbiddenImports:
    """Test no forbidden imports."""

    def test_no_playwright_import(self):
        """No playwright import."""
        import HUMANOID_HUNTER.interface.executor_adapter as module
        import inspect
        source = inspect.getsource(module)
        assert 'playwright' not in source

    def test_no_selenium_import(self):
        """No selenium import."""
        import HUMANOID_HUNTER.interface.executor_adapter as module
        import inspect
        source = inspect.getsource(module)
        assert 'selenium' not in source

    def test_no_subprocess_import(self):
        """No subprocess import."""
        import HUMANOID_HUNTER.interface.executor_adapter as module
        import inspect
        source = inspect.getsource(module)
        assert 'import subprocess' not in source

    def test_no_os_import(self):
        """No os import."""
        import HUMANOID_HUNTER.interface.executor_adapter as module
        import inspect
        source = inspect.getsource(module)
        assert 'import os' not in source

    def test_no_phase21_import(self):
        """No phase21+ imports."""
        module_dir = Path(__file__).resolve().parents[1] / "interface"
        for filepath in module_dir.glob("*.py"):
            content = filepath.read_text()
            assert 'phase21' not in content


class TestEnumCounts:
    """Test enum member counts."""

    def test_executor_command_type_has_seven_members(self):
        """ExecutorCommandType has exactly 7 members."""
        from HUMANOID_HUNTER.interface.executor_types import ExecutorCommandType
        assert len(ExecutorCommandType) == 7

    def test_executor_response_type_has_five_members(self):
        """ExecutorResponseType has exactly 5 members."""
        from HUMANOID_HUNTER.interface.executor_types import ExecutorResponseType
        assert len(ExecutorResponseType) == 5

    def test_executor_status_has_four_members(self):
        """ExecutorStatus has exactly 4 members."""
        from HUMANOID_HUNTER.interface.executor_types import ExecutorStatus
        assert len(ExecutorStatus) == 4
