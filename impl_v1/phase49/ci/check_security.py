#!/usr/bin/env python3
"""
CI Security Check - Static Analysis for Forbidden Imports
==========================================================

Scans codebase for forbidden patterns that must fail CI pipeline.
Exit code 0 = PASS, Exit code 1 = FAIL

FORBIDDEN PATTERNS:
- subprocess (in non-test files)
- os.system
- socket( (in non-test files)
- exec( (in non-test files)
- eval( (except model.eval())
- from selenium
- from playwright
"""

import os
import sys
import re
from pathlib import Path
from typing import List, Tuple

# Patterns that MUST NOT exist in production code
FORBIDDEN_PATTERNS = [
    (r"import subprocess", "subprocess import"),
    (r"from subprocess import", "subprocess import"),
    (r"os\.system\s*\(", "os.system call"),
    (r"Popen\s*\(", "Popen call"),
    (r"from selenium", "selenium import"),
    (r"from playwright", "playwright import"),
    (r"from pyppeteer", "pyppeteer import"),
    (r"os\.fork\s*\(", "os.fork call"),
    (r"__import__\s*\(", "dynamic import"),
]

# Patterns allowed in specific contexts
CONTEXT_PATTERNS = [
    # exec( and eval( are checked separately to allow model.eval()
]

# Directories to skip
SKIP_DIRS = {
    "__pycache__",
    ".git",
    "node_modules",
    ".venv",
    "venv",
    ".mypy_cache",
    ".pytest_cache",
}


def is_test_file(filepath: Path) -> bool:
    """Check if file is a test file."""
    name = filepath.name
    return name.startswith("test_") or name.endswith("_test.py") or "/tests/" in str(filepath)


def scan_file(filepath: Path) -> List[Tuple[str, int, str]]:
    """Scan a file for forbidden patterns."""
    violations = []
    
    try:
        content = filepath.read_text(encoding="utf-8", errors="ignore")
        lines = content.split("\n")
        
        for i, line in enumerate(lines, 1):
            # Skip comments
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            
            # Skip string assertions in tests
            if is_test_file(filepath):
                if "assert" in line or '"""' in line or "'''" in line:
                    continue
            
            for pattern, description in FORBIDDEN_PATTERNS:
                if re.search(pattern, line):
                    # Skip if in test file and it's an assertion
                    if is_test_file(filepath):
                        continue
                    violations.append((description, i, line.strip()[:80]))
        
        # Special check for exec( - must not be in production code
        if not is_test_file(filepath):
            for i, line in enumerate(lines, 1):
                if "exec(" in line and not line.strip().startswith("#"):
                    violations.append(("exec() call", i, line.strip()[:80]))
        
        # Special check for eval( - allow model.eval() only
        if not is_test_file(filepath):
            for i, line in enumerate(lines, 1):
                if "eval(" in line and "model.eval()" not in line:
                    if not line.strip().startswith("#"):
                        violations.append(("eval() call", i, line.strip()[:80]))
        
        # Special check for socket( - allow WebSocket
        if not is_test_file(filepath):
            for i, line in enumerate(lines, 1):
                if "socket(" in line and "websocket" not in line.lower():
                    if not line.strip().startswith("#"):
                        violations.append(("raw socket call", i, line.strip()[:80]))
    
    except Exception as e:
        print(f"  Warning: Could not read {filepath}: {e}")
    
    return violations


def main():
    """Run CI security check."""
    print("=" * 60)
    print("CI SECURITY CHECK - Forbidden Import Scanner")
    print("=" * 60)
    
    # Find project root
    script_dir = Path(__file__).parent
    project_root = script_dir.parent.parent.parent  # impl_v1/phase49/ci -> impl_v1/phase49 -> impl_v1 -> YGB
    
    if not project_root.exists():
        project_root = Path.cwd()
    
    print(f"\nScanning: {project_root}")
    print("-" * 60)
    
    all_violations = []
    files_scanned = 0
    
    for root, dirs, files in os.walk(project_root):
        # Skip excluded directories
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        
        for filename in files:
            if not filename.endswith(".py"):
                continue
            
            filepath = Path(root) / filename
            files_scanned += 1
            
            violations = scan_file(filepath)
            
            if violations:
                rel_path = filepath.relative_to(project_root)
                for desc, line_num, content in violations:
                    all_violations.append((rel_path, desc, line_num, content))
    
    print(f"\nFiles scanned: {files_scanned}")
    print("-" * 60)
    
    if all_violations:
        print(f"\n[FAIL] VIOLATIONS FOUND: {len(all_violations)}\n")
        for rel_path, desc, line_num, content in all_violations:
            print(f"  [{desc}] {rel_path}:{line_num}")
            print(f"    -> {content}")
            print()
        
        print("=" * 60)
        print("CI CHECK: FAILED")
        print("=" * 60)
        return 1
    else:
        print("\n[PASS] NO VIOLATIONS FOUND")
        print("=" * 60)
        print("CI CHECK: PASSED")
        print("=" * 60)
        return 0


if __name__ == "__main__":
    sys.exit(main())
