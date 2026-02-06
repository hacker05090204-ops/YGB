# test_forbidden_imports.py
"""Verify Phase-49 has no forbidden imports.

Exclusions:
- runtime/: Needs subprocess for OS-level idle detection (xprintidle, loginctl)
- ci/: CI scanners contain pattern definitions (not actual imports)
"""

import pytest
from pathlib import Path

PHASE49_DIR = Path(__file__).parent.parent

# Approved files that legitimately use subprocess or contain patterns
APPROVED_FILES = {
    "check_security.py",       # CI scanner - contains patterns
    "check_full_security.py",  # CI scanner - contains patterns
    "idle_detector.py",        # OS idle detection
    "secure_subprocess.py",    # Hardened wrapper
}

# Exclude test files, runtime directory, and CI directory
PYTHON_FILES = [
    f for f in PHASE49_DIR.rglob("*.py")
    if "test_" not in f.name 
    and f.parent.name != "tests"
    and "runtime" not in str(f)  # runtime needs subprocess for OS APIs
    and f.parent.name != "ci"    # ci tools legitimately use subprocess
    and f.name not in APPROVED_FILES
]

FORBIDDEN = ["subprocess", "socket", "selenium", "playwright"]

class TestForbiddenImports:
    @pytest.mark.parametrize("filepath", PYTHON_FILES)
    def test_no_forbidden_imports(self, filepath):
        content = filepath.read_text(encoding="utf-8", errors="ignore")
        for name in FORBIDDEN:
            if f"import {name}" in content:
                pytest.fail(f"Forbidden import '{name}' in {filepath.name}")

