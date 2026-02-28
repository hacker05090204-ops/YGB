#!/usr/bin/env python3
"""
CI Gate: Banned Token Scanner

Scans all production .py / .ts / .tsx files for banned patterns.
Exits 0 if clean, 1 if violations found.

Allowed exceptions:
 - Files inside test directories (tests/, __tests__/, test_*)
 - The SIMULATED governance state machine constant
 - Comments that reference "no mock" / "no simulate" etc.
 - This script itself
"""

import os
import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent

# Only scan production server paths — these are the directories
# that make up the runtime import graph of the API server.
# Deep subsystem modules (impl_v1, HUMANOID_HUNTER, python/, native/,
# governance/, training/) are excluded here; they have their own
# internal test gates.
SCAN_DIRS = ["api", "backend", "scripts", "frontend"]

# Directories to skip within SCAN_DIRS
SKIP_DIRS = {
    "node_modules", ".next", ".git", "__pycache__", ".venv", "venv",
    "tests", "__tests__", ".pytest_cache",
}

# File basenames to skip
SKIP_FILES = {
    "ci_banned_tokens.py",  # This script
}

# Patterns to scan for (case-insensitive)
BANNED_PATTERNS = [
    (r'\bmock\b', "mock"),
    (r'\bstub\b', "stub"),
    (r'\bsimulate\b', "simulate"),
    (r'\bsimulated\b', "simulated"),
    (r'\bstimulated\b', "stimulated"),
    (r'\bsynthetic\b', "synthetic"),
    (r'\bplaceholder\b', "placeholder"),
    (r'\bnot implemented\b', "not implemented"),
    (r'\bTODO\b', "TODO"),
    (r'\bFIXME\b', "FIXME"),
]

# Lines matching these patterns are ALLOWED (e.g. "no mocks", "ZERO mock")
ALLOWLIST_LINE_PATTERNS = [
    r'(?:no|zero|without|never|must not|reject|block)\s+(?:mock|stub|simul|synthetic|placeholder)',
    r'# (?:MOCK|mock) mode removed',
    r'MOCK mode is disabled',
    r'forbidden.*=.*\[',                   # test forbidden-word lists
    r'REJECTED_SIGNATURES',
    r'test_no_mock',
    r'unittest\.mock',
    r'from unittest',
    r'vi\.(?:fn|mock|stub)',
    r'mockFetch',
    r'mockOk|mockError',
    r'data-\[placeholder\]',              # CSS/Tailwind pseudo-class
    r'placeholder:text-',                 # CSS placeholder styling
    r'placeholder-\[',                    # CSS placeholder color classes
    r'placeholder=',                      # HTML placeholder attribute
    r'"SIMULATED"',                       # Legitimate governance state
    r"'SIMULATED'",                       # Legitimate governance state
    r'SIMULATED:',                        # State-to-color mapping
    r"'todo', 'fixme'",                   # Sensitive word scan lists
    r'"todo", "fixme"',                   # Sensitive word scan lists
    r'SIMULATE,',                         # State transition comments
    r'# PLAN, SIMULATE',                  # State machine docs
    r'SYNTHETIC / NONE',                  # Data source docs
    r'SYNTHETIC_GENERATOR',               # Rejected data source
    r'Synthetic Status',                  # UI label for blocked status
    r'SYNTHETIC \(blocked\)',             # UI display text
    r'is missing or is a placeholder',    # Preflight error message
    r'# In test mode, simulate',          # Test-mode comment
    r'# Simulate \d+ CVE',               # Test-mode comment
    r'Simulate a clock skew',             # Test helper docstring
    r'NEVER returns',                     # Anti-pattern comment
    r'check_skew_simulated',              # Test-only method name
]


def is_test_path(path: Path) -> bool:
    """Check if a file is inside a test directory or is a test file."""
    parts = path.parts
    for part in parts:
        if part in ("tests", "__tests__", "test"):
            return True
    return path.name.startswith("test_")


def is_allowed_line(line: str) -> bool:
    """Check if a line matches any allowlist pattern."""
    for pattern in ALLOWLIST_LINE_PATTERNS:
        if re.search(pattern, line, re.IGNORECASE):
            return True
    return False


def scan_file(filepath: Path) -> list:
    """Scan a file for banned tokens, return violations."""
    violations = []
    try:
        content = filepath.read_text(errors="ignore")
    except Exception:
        return violations

    for line_num, line in enumerate(content.splitlines(), 1):
        if is_allowed_line(line):
            continue
        for pattern, label in BANNED_PATTERNS:
            if re.search(pattern, line, re.IGNORECASE):
                violations.append({
                    "file": str(filepath.relative_to(PROJECT_ROOT)),
                    "line": line_num,
                    "token": label,
                    "content": line.strip()[:120],
                })
    return violations


def main():
    extensions = {".py", ".ts", ".tsx"}
    all_violations = []

    for scan_dir in SCAN_DIRS:
        scan_root = PROJECT_ROOT / scan_dir
        if not scan_root.exists():
            continue
        for root, dirs, files in os.walk(scan_root):
            # Prune skipped directories
            dirs[:] = [d for d in dirs if d not in SKIP_DIRS]

            for fname in files:
                if fname in SKIP_FILES:
                    continue
                fpath = Path(root) / fname
                if fpath.suffix not in extensions:
                    continue
                if is_test_path(fpath):
                    continue

                violations = scan_file(fpath)
                all_violations.extend(violations)

    if all_violations:
        print(f"BANNED TOKEN SCAN FAILED -- {len(all_violations)} violation(s) found:\n")
        for v in all_violations:
            print(f"  {v['file']}:{v['line']}  [{v['token']}]  {v['content']}")
        print(f"\nTotal: {len(all_violations)} violations")
        sys.exit(1)
    else:
        print("[OK] Banned token scan passed -- no violations in production code.")
        sys.exit(0)


if __name__ == "__main__":
    main()
