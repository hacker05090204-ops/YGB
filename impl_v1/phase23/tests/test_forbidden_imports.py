"""Phase-23 Forbidden Import Tests."""
import pytest
from pathlib import Path

PHASE23_DIR = Path(__file__).parent.parent
IMPLEMENTATION_FILES = ["phase23_types.py", "phase23_context.py", "phase23_engine.py", "__init__.py"]


def _read_source(filename: str) -> str:
    filepath = PHASE23_DIR / filename
    if not filepath.exists():
        pytest.skip(f"File {filename} does not exist yet")
    return filepath.read_text()


class TestForbiddenImports:
    @pytest.mark.parametrize("filename", IMPLEMENTATION_FILES)
    def test_no_os_import(self, filename: str) -> None:
        source = _read_source(filename)
        assert "import os" not in source
        assert "from os" not in source

    @pytest.mark.parametrize("filename", IMPLEMENTATION_FILES)
    def test_no_subprocess_import(self, filename: str) -> None:
        source = _read_source(filename)
        assert "import subprocess" not in source

    @pytest.mark.parametrize("filename", IMPLEMENTATION_FILES)
    def test_no_socket_import(self, filename: str) -> None:
        source = _read_source(filename)
        assert "import socket" not in source

    @pytest.mark.parametrize("filename", IMPLEMENTATION_FILES)
    def test_no_asyncio_import(self, filename: str) -> None:
        source = _read_source(filename)
        assert "import asyncio" not in source

    @pytest.mark.parametrize("filename", IMPLEMENTATION_FILES)
    def test_no_requests_import(self, filename: str) -> None:
        source = _read_source(filename)
        assert "import requests" not in source

    @pytest.mark.parametrize("filename", IMPLEMENTATION_FILES)
    def test_no_urllib_import(self, filename: str) -> None:
        source = _read_source(filename)
        assert "import urllib" not in source

    @pytest.mark.parametrize("filename", IMPLEMENTATION_FILES)
    def test_no_http_client_import(self, filename: str) -> None:
        source = _read_source(filename)
        assert "import http.client" not in source

    @pytest.mark.parametrize("filename", IMPLEMENTATION_FILES)
    def test_no_playwright_import(self, filename: str) -> None:
        source = _read_source(filename)
        assert "import playwright" not in source

    @pytest.mark.parametrize("filename", IMPLEMENTATION_FILES)
    def test_no_selenium_import(self, filename: str) -> None:
        source = _read_source(filename)
        assert "import selenium" not in source

    @pytest.mark.parametrize("filename", IMPLEMENTATION_FILES)
    def test_no_threading_import(self, filename: str) -> None:
        source = _read_source(filename)
        assert "import threading" not in source

    @pytest.mark.parametrize("filename", IMPLEMENTATION_FILES)
    def test_no_multiprocessing_import(self, filename: str) -> None:
        source = _read_source(filename)
        assert "import multiprocessing" not in source

    @pytest.mark.parametrize("filename", IMPLEMENTATION_FILES)
    def test_no_exec_call(self, filename: str) -> None:
        source = _read_source(filename)
        assert "exec(" not in source

    @pytest.mark.parametrize("filename", IMPLEMENTATION_FILES)
    def test_no_eval_call(self, filename: str) -> None:
        source = _read_source(filename)
        assert "eval(" not in source

    @pytest.mark.parametrize("filename", IMPLEMENTATION_FILES)
    def test_no_async_def(self, filename: str) -> None:
        source = _read_source(filename)
        assert "async def" not in source

    @pytest.mark.parametrize("filename", IMPLEMENTATION_FILES)
    def test_no_await(self, filename: str) -> None:
        source = _read_source(filename)
        assert "await " not in source

    @pytest.mark.parametrize("filename", IMPLEMENTATION_FILES)
    def test_no_future_phase_imports(self, filename: str) -> None:
        source = _read_source(filename).lower()
        for phase in range(24, 35):
            assert f"phase{phase}" not in source


class TestNoFileOperations:
    @pytest.mark.parametrize("filename", ["phase23_types.py", "phase23_context.py", "phase23_engine.py"])
    def test_no_open_call(self, filename: str) -> None:
        source = _read_source(filename)
        lines = source.split('\n')
        for i, line in enumerate(lines, 1):
            if line.strip().startswith('#') or line.strip().startswith('"""'):
                continue
            if "open(" in line and '"open("' not in line and "'open('" not in line:
                assert False, f"{filename}:{i} contains open() call"
