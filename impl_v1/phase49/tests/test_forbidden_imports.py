# test_forbidden_imports.py
"""Verify Phase-49 has no forbidden imports.

Note: The runtime/ directory is excluded because it legitimately needs
subprocess for OS-level idle detection (xprintidle, loginctl).
"""

import pytest
from pathlib import Path

PHASE49_DIR = Path(__file__).parent.parent
# Exclude test files and runtime directory (needs subprocess for OS idle detection)
PYTHON_FILES = [
    f for f in PHASE49_DIR.rglob("*.py")
    if "test_" not in f.name 
    and f.parent.name != "tests"
    and "runtime" not in str(f)  # runtime needs subprocess for OS APIs
]

FORBIDDEN = ["subprocess", "socket", "selenium", "playwright"]

class TestForbiddenImports:
    @pytest.mark.parametrize("filepath", PYTHON_FILES)
    def test_no_forbidden_imports(self, filepath):
        content = filepath.read_text()
        for name in FORBIDDEN:
            if f"import {name}" in content:
                pytest.fail(f"Forbidden import '{name}' in {filepath.name}")
