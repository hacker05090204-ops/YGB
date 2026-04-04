"""
Tests for Phase-28 No Browser Imports.

Tests:
- No playwright imports
- No selenium imports
- No subprocess imports
- No os imports
- No phase29+ imports
"""
import pytest


class TestNoForbiddenImports:
    """Test no forbidden imports."""

    def test_no_playwright_import_in_types(self):
        """No playwright import in handshake_types."""
        import HUMANOID_HUNTER.handshake.handshake_types as module
        import inspect
        source = inspect.getsource(module)
        assert 'playwright' not in source

    def test_no_playwright_import_in_context(self):
        """No playwright import in handshake_context."""
        import HUMANOID_HUNTER.handshake.handshake_context as module
        import inspect
        source = inspect.getsource(module)
        assert 'playwright' not in source

    def test_no_playwright_import_in_engine(self):
        """No playwright import in handshake_engine."""
        import HUMANOID_HUNTER.handshake.handshake_engine as module
        import inspect
        source = inspect.getsource(module)
        assert 'playwright' not in source

    def test_no_selenium_import_in_types(self):
        """No selenium import in handshake_types."""
        import HUMANOID_HUNTER.handshake.handshake_types as module
        import inspect
        source = inspect.getsource(module)
        assert 'selenium' not in source

    def test_no_selenium_import_in_context(self):
        """No selenium import in handshake_context."""
        import HUMANOID_HUNTER.handshake.handshake_context as module
        import inspect
        source = inspect.getsource(module)
        assert 'selenium' not in source

    def test_no_selenium_import_in_engine(self):
        """No selenium import in handshake_engine."""
        import HUMANOID_HUNTER.handshake.handshake_engine as module
        import inspect
        source = inspect.getsource(module)
        assert 'selenium' not in source

    def test_no_subprocess_import_in_types(self):
        """No subprocess import in handshake_types."""
        import HUMANOID_HUNTER.handshake.handshake_types as module
        import inspect
        source = inspect.getsource(module)
        assert 'import subprocess' not in source

    def test_no_subprocess_import_in_context(self):
        """No subprocess import in handshake_context."""
        import HUMANOID_HUNTER.handshake.handshake_context as module
        import inspect
        source = inspect.getsource(module)
        assert 'import subprocess' not in source

    def test_no_subprocess_import_in_engine(self):
        """No subprocess import in handshake_engine."""
        import HUMANOID_HUNTER.handshake.handshake_engine as module
        import inspect
        source = inspect.getsource(module)
        assert 'import subprocess' not in source

    def test_no_os_import_in_types(self):
        """No os import in handshake_types."""
        import HUMANOID_HUNTER.handshake.handshake_types as module
        import inspect
        source = inspect.getsource(module)
        assert 'import os' not in source

    def test_no_os_import_in_context(self):
        """No os import in handshake_context."""
        import HUMANOID_HUNTER.handshake.handshake_context as module
        import inspect
        source = inspect.getsource(module)
        assert 'import os' not in source

    def test_no_os_import_in_engine(self):
        """No os import in handshake_engine."""
        import HUMANOID_HUNTER.handshake.handshake_engine as module
        import inspect
        source = inspect.getsource(module)
        assert 'import os' not in source


class TestNoForwardPhaseImports:
    """Test no forward-phase imports."""

    def test_no_phase29_import(self):
        """No phase29+ imports."""
        import os as os_module
        import HUMANOID_HUNTER.handshake
        module_dir = os_module.path.dirname(HUMANOID_HUNTER.handshake.__file__)
        for filename in os_module.listdir(module_dir):
            if filename.endswith('.py'):
                filepath = os_module.path.join(module_dir, filename)
                with open(filepath, 'r') as f:
                    content = f.read()
                    assert 'phase29' not in content.lower(), f"phase29 found in {filename}"
                    assert 'phase30' not in content.lower(), f"phase30 found in {filename}"


class TestNoExecutionCode:
    """Test no execution code in handshake module."""

    def test_no_exec_call_in_engine(self):
        """No exec() call in handshake_engine."""
        import HUMANOID_HUNTER.handshake.handshake_engine as module
        import inspect
        source = inspect.getsource(module)
        assert 'exec(' not in source

    def test_no_eval_call_in_engine(self):
        """No eval() call in handshake_engine."""
        import HUMANOID_HUNTER.handshake.handshake_engine as module
        import inspect
        source = inspect.getsource(module)
        assert 'eval(' not in source
