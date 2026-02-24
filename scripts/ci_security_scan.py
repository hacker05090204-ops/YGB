"""
CI Security Guard — Automated security scanning for CI/CD pipeline

Scans the codebase for:
1. Hardcoded secrets / placeholder patterns
2. Mock/simulated/fake keywords in production code
3. str(e) error leakage in API responses
4. Insecure default secrets

Exit code 0 = clean, 1 = violations found.
"""

import os
import sys
import re
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent

# =============================================================================
# SCAN CONFIGURATION
# =============================================================================

# Directories to scan (production code only)
SCAN_DIRS = ["api", "backend", "native", "scripts", "impl_v1"]

# Directories to exclude
EXCLUDE_DIRS = {"tests", "__pycache__", ".git", "node_modules", "__tests__"}

# Patterns that indicate hardcoded secrets
SECRET_PATTERNS = [
    re.compile(r'["\']change-me["\']', re.IGNORECASE),
    re.compile(r'["\']change_me["\']', re.IGNORECASE),
    re.compile(r'["\']changeme["\']', re.IGNORECASE),
    re.compile(r'["\']replace-me["\']', re.IGNORECASE),
    re.compile(r'["\']your-secret["\']', re.IGNORECASE),
    re.compile(r'secret.*=.*["\'][a-f0-9]{32,}["\']', re.IGNORECASE),
]

# Patterns that indicate mock/fake behavior in production code
MOCK_PATTERNS = [
    re.compile(r'["\']mock-gpu["\']'),
    re.compile(r'["\'].*-mock["\']'),
    re.compile(r'MOCK_[A-Z]+\s*='),
    re.compile(r'FAKE_[A-Z]+\s*='),
    re.compile(r'DEMO_[A-Z]+\s*='),
    re.compile(r'simulated\s*=\s*True'),
]

# Error leakage patterns
ERROR_LEAKAGE_PATTERNS = [
    re.compile(r'"error".*:\s*str\(e\)'),
    re.compile(r'detail\s*=\s*str\(e\)'),
]


# =============================================================================
# SCANNER
# =============================================================================

def should_skip(path: Path) -> bool:
    """Check if path should be skipped."""
    for part in path.parts:
        if part in EXCLUDE_DIRS:
            return True
    return False


def scan_file(filepath: Path, patterns: list, label: str) -> list:
    """Scan a file for pattern violations."""
    violations = []
    try:
        content = filepath.read_text(encoding="utf-8", errors="ignore")
        for i, line in enumerate(content.splitlines(), 1):
            for pat in patterns:
                if pat.search(line):
                    violations.append({
                        "file": str(filepath.relative_to(PROJECT_ROOT)),
                        "line": i,
                        "type": label,
                        "content": line.strip()[:120],
                    })
    except Exception:
        pass
    return violations


def main():
    print("=" * 60)
    print("  YGB CI Security Guard")
    print("=" * 60)

    all_violations = []

    for scan_dir in SCAN_DIRS:
        dir_path = PROJECT_ROOT / scan_dir
        if not dir_path.exists():
            continue

        for filepath in dir_path.rglob("*.py"):
            if should_skip(filepath):
                continue

            # Check for hardcoded secrets
            all_violations.extend(
                scan_file(filepath, SECRET_PATTERNS, "HARDCODED_SECRET")
            )

            # Check for mock patterns
            all_violations.extend(
                scan_file(filepath, MOCK_PATTERNS, "MOCK_PATTERN")
            )

            # Check for error leakage
            all_violations.extend(
                scan_file(filepath, ERROR_LEAKAGE_PATTERNS, "ERROR_LEAKAGE")
            )

    # Report
    if all_violations:
        print(f"\n❌ {len(all_violations)} violation(s) found:\n")
        for v in all_violations:
            print(f"  [{v['type']}] {v['file']}:{v['line']}")
            print(f"    {v['content']}")
            print()
        sys.exit(1)
    else:
        print("\n✅ No security violations found.")
        sys.exit(0)


if __name__ == "__main__":
    main()
