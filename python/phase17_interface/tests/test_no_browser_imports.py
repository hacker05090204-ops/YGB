"""
Tests for Phase-17 No Browser Imports.

Tests:
- No browser imports (playwright, selenium)
- No execution imports (subprocess, os)
- No phase18+ imports
"""
import pytest


class TestNoForbiddenImports:
    """Test no forbidden imports."""

    def test_no_playwright_import(self):
        """No playwright import."""
        import python.phase17_interface.interface_engine as module
        import inspect
        source = inspect.getsource(module)
        assert 'playwright' not in source

    def test_no_selenium_import(self):
        """No selenium import."""
        import python.phase17_interface.interface_engine as module
        import inspect
        source = inspect.getsource(module)
        assert 'selenium' not in source

    def test_no_subprocess_import(self):
        """No subprocess import."""
        import python.phase17_interface.interface_engine as module
        import inspect
        source = inspect.getsource(module)
        assert 'import subprocess' not in source

    def test_no_os_import(self):
        """No os import."""
        import python.phase17_interface.interface_engine as module
        import inspect
        source = inspect.getsource(module)
        assert 'import os' not in source

    def test_no_phase18_import(self):
        """No phase18+ imports."""
        import os
        module_dir = os.path.dirname(__file__).replace('/tests', '')
        for filename in os.listdir(module_dir):
            if filename.endswith('.py'):
                filepath = os.path.join(module_dir, filename)
                with open(filepath, 'r') as f:
                    content = f.read()
                    assert 'phase18' not in content


class TestEnumCounts:
    """Test enum member counts."""

    def test_action_type_has_five_members(self):
        """ActionType has exactly 5 members."""
        from python.phase17_interface.interface_types import ActionType
        assert len(ActionType) == 5

    def test_response_status_has_three_members(self):
        """ResponseStatus has exactly 3 members."""
        from python.phase17_interface.interface_types import ResponseStatus
        assert len(ResponseStatus) == 3

    def test_contract_status_has_two_members(self):
        """ContractStatus has exactly 2 members."""
        from python.phase17_interface.interface_types import ContractStatus
        assert len(ContractStatus) == 2
