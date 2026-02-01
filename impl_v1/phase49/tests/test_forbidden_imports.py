# test_forbidden_imports.py
"""Verify Phase-49 has no forbidden imports."""

import pytest
from pathlib import Path

PHASE49_DIR = Path(__file__).parent.parent
PYTHON_FILES = list(PHASE49_DIR.rglob("*.py"))

FORBIDDEN = ["subprocess", "socket", "selenium", "playwright"]

class TestForbiddenImports:
    @pytest.mark.parametrize("filepath", PYTHON_FILES)
    def test_no_forbidden_imports(self, filepath):
        content = filepath.read_text()
        for name in FORBIDDEN:
            if f"import {name}" in content:
                pytest.fail(f"Forbidden import '{name}' in {filepath.name}")
