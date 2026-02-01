"""
Tests for Phase-30 No Forbidden Imports.

Tests:
- No playwright import
- No selenium import
- No subprocess import
- No os import
- No async code
- No phase31+ imports
"""
import pytest


class TestNoForbiddenImports:
    """Test no forbidden imports."""

    def test_no_playwright_import_in_types(self):
        """No playwright import in response_types."""
        import HUMANOID_HUNTER.executor_response.response_types as module
        import inspect
        source = inspect.getsource(module)
        assert 'playwright' not in source

    def test_no_playwright_import_in_context(self):
        """No playwright import in response_context."""
        import HUMANOID_HUNTER.executor_response.response_context as module
        import inspect
        source = inspect.getsource(module)
        assert 'playwright' not in source

    def test_no_playwright_import_in_engine(self):
        """No playwright import in response_engine."""
        import HUMANOID_HUNTER.executor_response.response_engine as module
        import inspect
        source = inspect.getsource(module)
        assert 'playwright' not in source

    def test_no_selenium_import_in_types(self):
        """No selenium import in response_types."""
        import HUMANOID_HUNTER.executor_response.response_types as module
        import inspect
        source = inspect.getsource(module)
        assert 'selenium' not in source

    def test_no_selenium_import_in_context(self):
        """No selenium import in response_context."""
        import HUMANOID_HUNTER.executor_response.response_context as module
        import inspect
        source = inspect.getsource(module)
        assert 'selenium' not in source

    def test_no_selenium_import_in_engine(self):
        """No selenium import in response_engine."""
        import HUMANOID_HUNTER.executor_response.response_engine as module
        import inspect
        source = inspect.getsource(module)
        assert 'selenium' not in source

    def test_no_subprocess_import_in_types(self):
        """No subprocess import in response_types."""
        import HUMANOID_HUNTER.executor_response.response_types as module
        import inspect
        source = inspect.getsource(module)
        assert 'import subprocess' not in source

    def test_no_subprocess_import_in_context(self):
        """No subprocess import in response_context."""
        import HUMANOID_HUNTER.executor_response.response_context as module
        import inspect
        source = inspect.getsource(module)
        assert 'import subprocess' not in source

    def test_no_subprocess_import_in_engine(self):
        """No subprocess import in response_engine."""
        import HUMANOID_HUNTER.executor_response.response_engine as module
        import inspect
        source = inspect.getsource(module)
        assert 'import subprocess' not in source

    def test_no_os_import_in_types(self):
        """No os import in response_types."""
        import HUMANOID_HUNTER.executor_response.response_types as module
        import inspect
        source = inspect.getsource(module)
        assert 'import os' not in source

    def test_no_os_import_in_context(self):
        """No os import in response_context."""
        import HUMANOID_HUNTER.executor_response.response_context as module
        import inspect
        source = inspect.getsource(module)
        assert 'import os' not in source

    def test_no_os_import_in_engine(self):
        """No os import in response_engine."""
        import HUMANOID_HUNTER.executor_response.response_engine as module
        import inspect
        source = inspect.getsource(module)
        assert 'import os' not in source


class TestNoAsyncCode:
    """Test no async code."""

    def test_no_async_in_engine(self):
        """No async def in response_engine."""
        import HUMANOID_HUNTER.executor_response.response_engine as module
        import inspect
        source = inspect.getsource(module)
        assert 'async def' not in source

    def test_no_await_in_engine(self):
        """No await in response_engine."""
        import HUMANOID_HUNTER.executor_response.response_engine as module
        import inspect
        source = inspect.getsource(module)
        assert 'await ' not in source


class TestNoForwardPhaseImports:
    """Test no forward-phase imports."""

    def test_no_phase31_import(self):
        """No phase31+ imports in any module."""
        import os as os_module
        import HUMANOID_HUNTER.executor_response
        module_dir = os_module.path.dirname(HUMANOID_HUNTER.executor_response.__file__)
        for filename in os_module.listdir(module_dir):
            if filename.endswith('.py'):
                filepath = os_module.path.join(module_dir, filename)
                with open(filepath, 'r') as f:
                    content = f.read()
                    assert 'phase31' not in content.lower(), f"phase31 found in {filename}"
                    assert 'phase32' not in content.lower(), f"phase32 found in {filename}"


class TestNoExecutionCode:
    """Test no execution code."""

    def test_no_exec_call_in_engine(self):
        """No exec() call in response_engine."""
        import HUMANOID_HUNTER.executor_response.response_engine as module
        import inspect
        source = inspect.getsource(module)
        assert 'exec(' not in source

    def test_no_eval_call_in_engine(self):
        """No eval() call in response_engine."""
        import HUMANOID_HUNTER.executor_response.response_engine as module
        import inspect
        source = inspect.getsource(module)
        assert 'eval(' not in source
