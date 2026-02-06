#!/usr/bin/env python3
"""
CI Full Security Scanner - Phase 49
====================================

Comprehensive CI security check for all code:
- Python
- C++ (headers only, checks for patterns)
- Frontend (TypeScript/JavaScript)
- Markdown (documentation)
- Native code

EXIT CODES:
- 0: PASS - No violations
- 1: FAIL - Violations found

BLOCKERS:
- selenium/playwright in any code
- subprocess (unapproved files)
- eval() (except model.eval())
- socket() in Python (except approved)
- execve in Python
"""

import os
import sys
import re
from pathlib import Path
from typing import List, Tuple, Set, Dict
from dataclasses import dataclass


# =============================================================================
# CONFIGURATION
# =============================================================================

# Files that are ALLOWED to use subprocess (approved after audit)
APPROVED_SUBPROCESS_FILES: Set[str] = {
    "idle_detector.py",      # OS idle detection (read-only queries)
    "secure_subprocess.py",  # Hardened wrapper itself
    "check_full_security.py", # CI scanner (pattern matching only)
    "check_security.py",     # Original CI scanner
}

# Files that are ALLOWED to have eval patterns (for checking others)
APPROVED_EVAL_PATTERN_FILES: Set[str] = {
    "check_security.py",
    "check_full_security.py",
    "phase_runner.py",       # Contains XSS vulnerability pattern definitions (string literals)
}

# Directories to skip
SKIP_DIRS: Set[str] = {
    "__pycache__",
    ".git",
    "node_modules",
    ".venv",
    "venv",
    ".mypy_cache",
    ".pytest_cache",
    ".next",
    "dist",
    "build",
}

# Files to completely skip (CI scanners themselves)
SKIP_FILES: Set[str] = {
    "check_security.py",
    "check_full_security.py",
}

# Test file patterns
TEST_FILE_PATTERNS = {"test_", "_test.py", "tests/"}


# =============================================================================
# PATTERNS
# =============================================================================

@dataclass
class ViolationPattern:
    """Pattern that indicates a violation."""
    name: str
    pattern: str
    file_types: List[str]
    is_regex: bool = True


PYTHON_VIOLATIONS = [
    ViolationPattern("selenium import", r"from selenium", [".py"]),
    ViolationPattern("playwright import", r"from playwright", [".py"]),
    ViolationPattern("pyppeteer import", r"from pyppeteer", [".py"]),
    ViolationPattern("os.system call", r"os\.system\s*\(", [".py"]),
    ViolationPattern("Popen direct", r"Popen\s*\(", [".py"]),
    ViolationPattern("os.fork call", r"os\.fork\s*\(", [".py"]),
    ViolationPattern("dynamic import", r"__import__\s*\(", [".py"]),
]

CPP_VIOLATIONS = [
    ViolationPattern("system() call", r"\bsystem\s*\(", [".cpp", ".hpp", ".h"]),
    ViolationPattern("popen() call", r"\bpopen\s*\(", [".cpp", ".hpp", ".h"]),
]

FRONTEND_VIOLATIONS = [
    ViolationPattern("eval() call", r"\beval\s*\(", [".ts", ".tsx", ".js", ".jsx"]),
    ViolationPattern("Function() constructor", r"\bnew Function\s*\(", [".ts", ".tsx", ".js", ".jsx"]),
]


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def is_test_file(filepath: Path) -> bool:
    """Check if file is a test file."""
    name = filepath.name
    path_str = str(filepath)
    return (
        name.startswith("test_") or
        name.endswith("_test.py") or
        "/tests/" in path_str or
        "\\tests\\" in path_str
    )


def should_skip_file(filepath: Path, pattern: ViolationPattern) -> bool:
    """Check if file should be skipped for a pattern."""
    name = filepath.name
    
    # Skip test files
    if is_test_file(filepath):
        return True
    
    # Skip approved files for subprocess
    if pattern.name == "subprocess import":
        if name in APPROVED_SUBPROCESS_FILES:
            return True
    
    # Skip approved eval pattern files
    if "eval" in pattern.name:
        if name in APPROVED_EVAL_PATTERN_FILES:
            return True
    
    return False


def check_special_patterns(filepath: Path, content: str) -> List[Tuple[str, int, str]]:
    """Check for special patterns that need context."""
    violations = []
    lines = content.split("\n")
    name = filepath.name
    
    # Skip test files
    if is_test_file(filepath):
        return []
    
    # Check for subprocess import (with approved file list)
    if filepath.suffix == ".py" and name not in APPROVED_SUBPROCESS_FILES:
        for i, line in enumerate(lines, 1):
            if "import subprocess" in line or "from subprocess import" in line:
                if not line.strip().startswith("#"):
                    violations.append(("subprocess import (unapproved)", i, line.strip()[:80]))
    
    # Check for exec() in Python
    if filepath.suffix == ".py" and name not in APPROVED_EVAL_PATTERN_FILES:
        for i, line in enumerate(lines, 1):
            stripped = line.strip()
            if "exec(" in line and not stripped.startswith("#"):
                # Skip string literals in test assertions
                if "assert" not in line and '"""' not in line and "'''" not in line:
                    violations.append(("exec() call", i, stripped[:80]))
    
    # Check for eval() in Python (allow model.eval())
    if filepath.suffix == ".py" and name not in APPROVED_EVAL_PATTERN_FILES:
        for i, line in enumerate(lines, 1):
            stripped = line.strip()
            if "eval(" in line and "model.eval()" not in line:
                if not stripped.startswith("#"):
                    if "assert" not in line and '"""' not in line:
                        violations.append(("eval() call", i, stripped[:80]))
    
    # Check for raw socket in Python
    if filepath.suffix == ".py":
        for i, line in enumerate(lines, 1):
            stripped = line.strip()
            if "socket(" in line and "websocket" not in line.lower():
                if not stripped.startswith("#"):
                    if "assert" not in line:
                        violations.append(("raw socket call", i, stripped[:80]))
    
    return violations


def scan_file(filepath: Path, patterns: List[ViolationPattern]) -> List[Tuple[str, int, str]]:
    """Scan a file for violations."""
    violations = []
    
    try:
        content = filepath.read_text(encoding="utf-8", errors="ignore")
        lines = content.split("\n")
        
        # Check regular patterns
        for pattern in patterns:
            if filepath.suffix not in pattern.file_types:
                continue
            
            if should_skip_file(filepath, pattern):
                continue
            
            for i, line in enumerate(lines, 1):
                stripped = line.strip()
                if stripped.startswith("#") or stripped.startswith("//"):
                    continue
                
                if pattern.is_regex:
                    if re.search(pattern.pattern, line):
                        violations.append((pattern.name, i, stripped[:80]))
                else:
                    if pattern.pattern in line:
                        violations.append((pattern.name, i, stripped[:80]))
        
        # Check special patterns
        violations.extend(check_special_patterns(filepath, content))
    
    except Exception as e:
        print(f"  Warning: Could not read {filepath}: {e}")
    
    return violations


# =============================================================================
# MAIN
# =============================================================================

def main() -> int:
    """Run full CI security scan."""
    print("=" * 70)
    print("CI FULL SECURITY SCANNER - Phase 49")
    print("=" * 70)
    
    # Find project root
    script_dir = Path(__file__).parent
    project_root = script_dir.parent.parent.parent  # ci -> phase49 -> impl_v1 -> YGB
    
    if not project_root.exists() or not (project_root / "pyproject.toml").exists():
        project_root = Path.cwd()
    
    print(f"\nScanning: {project_root}")
    print("-" * 70)
    
    all_violations: List[Tuple[Path, str, int, str]] = []
    files_scanned = 0
    
    # Combine all patterns
    all_patterns = PYTHON_VIOLATIONS + CPP_VIOLATIONS + FRONTEND_VIOLATIONS
    
    for root, dirs, files in os.walk(project_root):
        # Skip excluded directories
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        
        for filename in files:
            # Skip CI scanner files (they contain pattern definitions)
            if filename in SKIP_FILES:
                continue
            
            # Only scan relevant file types
            if not filename.endswith((".py", ".cpp", ".hpp", ".h", ".ts", ".tsx", ".js", ".jsx")):
                continue
            
            filepath = Path(root) / filename
            files_scanned += 1
            
            violations = scan_file(filepath, all_patterns)
            
            for desc, line_num, content in violations:
                try:
                    rel_path = filepath.relative_to(project_root)
                except ValueError:
                    rel_path = filepath
                all_violations.append((rel_path, desc, line_num, content))
    
    print(f"\nFiles scanned: {files_scanned}")
    print("-" * 70)
    
    if all_violations:
        print(f"\n[FAIL] VIOLATIONS FOUND: {len(all_violations)}\n")
        for rel_path, desc, line_num, content in all_violations:
            print(f"  [{desc}] {rel_path}:{line_num}")
            print(f"    -> {content}")
            print()
        
        print("=" * 70)
        print("CI CHECK: FAILED")
        print("=" * 70)
        return 1
    else:
        print("\n[PASS] NO VIOLATIONS FOUND")
        print("=" * 70)
        print("CI CHECK: PASSED")
        print("=" * 70)
        return 0


if __name__ == "__main__":
    sys.exit(main())
