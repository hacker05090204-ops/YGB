"""
Phase-34 Forbidden Import Tests.

Tests that FAIL if any forbidden imports appear in source code.
This is mandatory per governance requirements.

FORBIDDEN PATTERNS:
- os, subprocess, socket, asyncio
- requests, urllib, http.client
- playwright, selenium
- threading, multiprocessing
- exec(, eval(, open(
- async def, await
- phase35, phase36
"""
import pytest
from pathlib import Path


# Directory containing impl_v1/phase34 source files
PHASE34_DIR = Path(__file__).parent.parent


# All implementation files to scan
IMPLEMENTATION_FILES = [
    "phase34_types.py",
    "phase34_context.py",
    "phase34_engine.py",
    "__init__.py",
]


# Forbidden patterns - tests MUST FAIL if any appear
FORBIDDEN_PATTERNS = [
    # OS and system access
    "import os",
    "from os",
    "import subprocess",
    "from subprocess",
    # Network access
    "import socket",
    "from socket",
    "import requests",
    "from requests",
    "import urllib",
    "from urllib",
    "import http.client",
    "from http.client",
    "import http",
    "from http import",
    # Browser automation
    "import playwright",
    "from playwright",
    "import selenium",
    "from selenium",
    # Concurrency
    "import asyncio",
    "from asyncio",
    "import threading",
    "from threading",
    "import multiprocessing",
    "from multiprocessing",
    # Dynamic execution
    "exec(",
    "eval(",
    # Future phases
    "phase35",
    "phase36",
    "phase37",
]


# Async patterns (separate due to context sensitivity)
ASYNC_PATTERNS = [
    "async def",
    "await ",
]


def _read_source(filename: str) -> str:
    """Read source file content."""
    filepath = PHASE34_DIR / filename
    if not filepath.exists():
        pytest.skip(f"File {filename} does not exist yet")
    return filepath.read_text()


class TestForbiddenImports:
    """Test that forbidden imports do not appear in source code."""

    @pytest.mark.parametrize("filename", IMPLEMENTATION_FILES)
    def test_no_os_import(self, filename: str) -> None:
        """No os module import."""
        source = _read_source(filename)
        assert "import os" not in source, f"{filename} contains 'import os'"
        assert "from os" not in source, f"{filename} contains 'from os'"

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
        assert "exec(" not in source, f"{filename} contains exec()"

    @pytest.mark.parametrize("filename", IMPLEMENTATION_FILES)
    def test_no_eval_call(self, filename: str) -> None:
        """No eval() calls."""
        source = _read_source(filename)
        assert "eval(" not in source, f"{filename} contains eval()"

    @pytest.mark.parametrize("filename", IMPLEMENTATION_FILES)
    def test_no_async_def(self, filename: str) -> None:
        """No async function definitions."""
        source = _read_source(filename)
        assert "async def" not in source, f"{filename} contains async def"

    @pytest.mark.parametrize("filename", IMPLEMENTATION_FILES)
    def test_no_await(self, filename: str) -> None:
        """No await expressions."""
        source = _read_source(filename)
        assert "await " not in source, f"{filename} contains await"

    @pytest.mark.parametrize("filename", IMPLEMENTATION_FILES)
    def test_no_phase35_import(self, filename: str) -> None:
        """No phase35+ imports."""
        source = _read_source(filename).lower()
        assert "phase35" not in source
        assert "phase36" not in source
        assert "phase37" not in source


class TestNoFileOperations:
    """Test that no file operations appear in implementation."""

    @pytest.mark.parametrize("filename", ["phase34_types.py", "phase34_context.py", "phase34_engine.py"])
    def test_no_open_call_in_implementation(self, filename: str) -> None:
        """No open() calls in implementation files (test files are allowed)."""
        source = _read_source(filename)
        # Check for open() but allow it in comments
        lines = source.split('\n')
        for i, line in enumerate(lines, 1):
            # Skip comments and docstrings
            stripped = line.strip()
            if stripped.startswith('#') or stripped.startswith('"""') or stripped.startswith("'''"):
                continue
            # Check for open( outside of strings
            if "open(" in line and not line.strip().startswith('#'):
                # Allow if it's in a string (rough heuristic)
                if '"open("' not in line and "'open('" not in line:
                    assert False, f"{filename}:{i} contains open() call: {line}"
