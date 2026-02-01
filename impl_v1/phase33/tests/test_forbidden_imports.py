"""
Phase-33 Forbidden Import Tests.

Tests that FAIL if any forbidden imports appear in source code.
"""
import pytest
from pathlib import Path


PHASE33_DIR = Path(__file__).parent.parent

IMPLEMENTATION_FILES = [
    "phase33_types.py",
    "phase33_context.py",
    "phase33_engine.py",
    "__init__.py",
]


def _read_source(filename: str) -> str:
    """Read source file content."""
    filepath = PHASE33_DIR / filename
    if not filepath.exists():
        pytest.skip(f"File {filename} does not exist yet")
    return filepath.read_text()


class TestForbiddenImports:
    """Test that forbidden imports do not appear in source code."""

    @pytest.mark.parametrize("filename", IMPLEMENTATION_FILES)
    def test_no_os_import(self, filename: str) -> None:
        """No os module import."""
        source = _read_source(filename)
        assert "import os" not in source
        assert "from os" not in source

    @pytest.mark.parametrize("filename", IMPLEMENTATION_FILES)
    def test_no_subprocess_import(self, filename: str) -> None:
        """No subprocess module import."""
        source = _read_source(filename)
        assert "import subprocess" not in source
        assert "from subprocess" not in source

    @pytest.mark.parametrize("filename", IMPLEMENTATION_FILES)
    def test_no_socket_import(self, filename: str) -> None:
        """No socket module import."""
        source = _read_source(filename)
        assert "import socket" not in source
        assert "from socket" not in source

    @pytest.mark.parametrize("filename", IMPLEMENTATION_FILES)
    def test_no_asyncio_import(self, filename: str) -> None:
        """No asyncio module import."""
        source = _read_source(filename)
        assert "import asyncio" not in source
        assert "from asyncio" not in source

    @pytest.mark.parametrize("filename", IMPLEMENTATION_FILES)
    def test_no_requests_import(self, filename: str) -> None:
        """No requests module import."""
        source = _read_source(filename)
        assert "import requests" not in source
        assert "from requests" not in source

    @pytest.mark.parametrize("filename", IMPLEMENTATION_FILES)
    def test_no_urllib_import(self, filename: str) -> None:
        """No urllib module import."""
        source = _read_source(filename)
        assert "import urllib" not in source
        assert "from urllib" not in source

    @pytest.mark.parametrize("filename", IMPLEMENTATION_FILES)
    def test_no_http_client_import(self, filename: str) -> None:
        """No http.client module import."""
        source = _read_source(filename)
        assert "import http.client" not in source
        assert "from http.client" not in source

    @pytest.mark.parametrize("filename", IMPLEMENTATION_FILES)
    def test_no_playwright_import(self, filename: str) -> None:
        """No playwright module import."""
        source = _read_source(filename)
        assert "import playwright" not in source
        assert "from playwright" not in source

    @pytest.mark.parametrize("filename", IMPLEMENTATION_FILES)
    def test_no_selenium_import(self, filename: str) -> None:
        """No selenium module import."""
        source = _read_source(filename)
        assert "import selenium" not in source
        assert "from selenium" not in source

    @pytest.mark.parametrize("filename", IMPLEMENTATION_FILES)
    def test_no_threading_import(self, filename: str) -> None:
        """No threading module import."""
        source = _read_source(filename)
        assert "import threading" not in source
        assert "from threading" not in source

    @pytest.mark.parametrize("filename", IMPLEMENTATION_FILES)
    def test_no_multiprocessing_import(self, filename: str) -> None:
        """No multiprocessing module import."""
        source = _read_source(filename)
        assert "import multiprocessing" not in source
        assert "from multiprocessing" not in source

    @pytest.mark.parametrize("filename", IMPLEMENTATION_FILES)
    def test_no_exec_call(self, filename: str) -> None:
        """No exec() calls."""
        source = _read_source(filename)
        assert "exec(" not in source

    @pytest.mark.parametrize("filename", IMPLEMENTATION_FILES)
    def test_no_eval_call(self, filename: str) -> None:
        """No eval() calls."""
        source = _read_source(filename)
        assert "eval(" not in source

    @pytest.mark.parametrize("filename", IMPLEMENTATION_FILES)
    def test_no_async_def(self, filename: str) -> None:
        """No async function definitions."""
        source = _read_source(filename)
        assert "async def" not in source

    @pytest.mark.parametrize("filename", IMPLEMENTATION_FILES)
    def test_no_await(self, filename: str) -> None:
        """No await expressions."""
        source = _read_source(filename)
        assert "await " not in source

    @pytest.mark.parametrize("filename", IMPLEMENTATION_FILES)
    def test_no_phase34_import(self, filename: str) -> None:
        """No phase34+ imports."""
        source = _read_source(filename).lower()
        assert "phase34" not in source
        assert "phase35" not in source
        assert "phase36" not in source


class TestNoFileOperations:
    """Test that no file operations appear in implementation."""

    @pytest.mark.parametrize("filename", ["phase33_types.py", "phase33_context.py", "phase33_engine.py"])
    def test_no_open_call_in_implementation(self, filename: str) -> None:
        """No open() calls in implementation files."""
        source = _read_source(filename)
        lines = source.split('\n')
        for i, line in enumerate(lines, 1):
            stripped = line.strip()
            if stripped.startswith('#') or stripped.startswith('"""') or stripped.startswith("'''"):
                continue
            if "open(" in line and not line.strip().startswith('#'):
                if '"open("' not in line and "'open('" not in line:
                    assert False, f"{filename}:{i} contains open() call"
