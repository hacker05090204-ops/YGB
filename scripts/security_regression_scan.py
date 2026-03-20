"""
Security Regression Scanner — Static analysis for security anti-patterns.

Scans Python source files for:
  - TOKEN_IN_QUERY:         tokens/api_keys in query parameters
  - BIND_ALL_INTERFACES:    default server binding to 0.0.0.0
  - MISSING_OWNERSHIP:      route handlers accessing resources without ownership checks
  - WS_NO_REVOCATION:       WebSocket handlers without revocation checks

Exit code 0  = no high/critical violations
Exit code 1  = one or more CRITICAL/HIGH violations found

Output: JSON report + human-readable summary.
"""

import json
import os
import re
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import List

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# ---------------------------------------------------------------------------
# Rule definitions
# ---------------------------------------------------------------------------

@dataclass
class Violation:
    rule: str
    severity: str
    file: str
    line: int
    snippet: str
    message: str


@dataclass
class ScanReport:
    violations: List[Violation] = field(default_factory=list)
    files_scanned: int = 0
    rules_checked: int = 4
    passed: bool = True


# Patterns to detect
_TOKEN_IN_QUERY_RE = re.compile(
    r"""(?:\?|&)(?:token|api_key|access_token|secret)=""",
    re.IGNORECASE,
)

_BIND_ALL_RE = re.compile(
    r"""(?:host\s*=\s*['"]0\.0\.0\.0['"]|"""
    r"""bind\s*=\s*['"]0\.0\.0\.0['"]|"""
    r"""os\.getenv\(\s*['"]API_HOST['"]\s*,\s*['"]0\.0\.0\.0['"]\s*\))""",
    re.IGNORECASE,
)

_RESOURCE_ID_PARAM_RE = re.compile(
    r"""(?:workflow_id|session_id|report_id|bounty_id|target_id|user_id)"""
    r"""\s*[=:]""",
    re.IGNORECASE,
)

_WS_HANDLER_RE = re.compile(
    r"""async\s+def\s+\w+\(.*(?:WebSocket|websocket)""",
    re.IGNORECASE,
)


def _scan_file(filepath: Path, report: ScanReport) -> None:
    """Scan a single Python file for security anti-patterns."""
    try:
        content = filepath.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return

    lines = content.splitlines()
    rel_path = str(filepath.relative_to(PROJECT_ROOT))

    # Skip test files and vendored code
    if "/tests/" in rel_path or "\\tests\\" in rel_path:
        return
    if "node_modules" in rel_path or ".venv" in rel_path:
        return

    for i, line in enumerate(lines, start=1):
        stripped = line.strip()
        if stripped.startswith("#"):
            continue

        # Rule 1: TOKEN_IN_QUERY
        if _TOKEN_IN_QUERY_RE.search(line):
            # Exclude comments and log strings. Query-string fragments are only
            # risky when embedded in URLs or request templates, not when a
            # symbol merely contains a "token" suffix.
            if not stripped.startswith(("#", "logger.", "logging.")):
                report.violations.append(Violation(
                    rule="TOKEN_IN_QUERY",
                    severity="CRITICAL",
                    file=rel_path,
                    line=i,
                    snippet=stripped[:120],
                    message="Token or API key appears in query parameter — use HTTP-only cookies or headers instead",
                ))

        # Rule 2: BIND_ALL_INTERFACES (only in startup/config files)
        if _BIND_ALL_RE.search(line):
            # Allow if preceded by a comment indicating it's intentional
            prev_line = lines[i - 2].strip() if i >= 2 else ""
            if "# bind-all-ok" not in prev_line.lower() and "# nosec" not in prev_line.lower():
                report.violations.append(Violation(
                    rule="BIND_ALL_INTERFACES",
                    severity="HIGH",
                    file=rel_path,
                    line=i,
                    snippet=stripped[:120],
                    message="Server binding to 0.0.0.0 — use 127.0.0.1 or configure via env var",
                ))

    # Rule 3: MISSING_OWNERSHIP — check route files for resource ID params
    #         without check_resource_owner or check_ws_resource_owner
    if "route" in rel_path.lower() or "endpoint" in rel_path.lower() or rel_path.endswith("server.py"):
        has_resource_id = bool(_RESOURCE_ID_PARAM_RE.search(content))
        has_ownership_import = "check_resource_owner" in content or "check_ws_resource_owner" in content
        if has_resource_id and not has_ownership_import:
            report.violations.append(Violation(
                rule="MISSING_OWNERSHIP",
                severity="HIGH",
                file=rel_path,
                line=0,
                snippet="(file-level check)",
                message="File references resource IDs but does not import ownership check functions",
            ))

    # Rule 4: WS_NO_REVOCATION — WebSocket handlers without revocation checks
    ws_matches = _WS_HANDLER_RE.findall(content)
    if ws_matches:
        has_revocation = "is_token_revoked" in content or "is_session_revoked" in content
        if not has_revocation:
            for match in ws_matches:
                report.violations.append(Violation(
                    rule="WS_NO_REVOCATION",
                    severity="MEDIUM",
                    file=rel_path,
                    line=0,
                    snippet=match[:120],
                    message="WebSocket handler found without token/session revocation check",
                ))


def scan_directory(root: Path) -> ScanReport:
    """Scan all Python files under root for security anti-patterns."""
    report = ScanReport()

    py_files = list(root.rglob("*.py"))
    # Exclude virtual environments and node_modules
    py_files = [
        f for f in py_files
        if ".venv" not in f.parts
        and "node_modules" not in f.parts
        and "__pycache__" not in f.parts
    ]

    report.files_scanned = len(py_files)

    for filepath in py_files:
        _scan_file(filepath, report)

    high_plus = [v for v in report.violations if v.severity in ("CRITICAL", "HIGH")]
    report.passed = len(high_plus) == 0

    return report


def main() -> int:
    """Entry point for CI / command-line usage."""
    report = scan_directory(PROJECT_ROOT)

    # JSON output
    report_dict = {
        "passed": report.passed,
        "files_scanned": report.files_scanned,
        "rules_checked": report.rules_checked,
        "violation_count": len(report.violations),
        "violations": [asdict(v) for v in report.violations],
    }

    # Write JSON report
    report_path = PROJECT_ROOT / "reports" / "security_regression_report.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report_dict, indent=2), encoding="utf-8")

    # Human-readable summary
    print(f"\n{'=' * 60}")
    print(f"  Security Regression Scan")
    print(f"{'=' * 60}")
    print(f"  Files scanned: {report.files_scanned}")
    print(f"  Rules checked: {report.rules_checked}")
    print(f"  Violations:    {len(report.violations)}")
    print(f"  Result:        {'PASS' if report.passed else 'FAIL'}")
    print(f"{'=' * 60}\n")

    if report.violations:
        for v in report.violations:
            print(f"  [{v.severity}] {v.rule}")
            print(f"     {v.file}:{v.line}")
            print(f"     {v.message}")
            print(f"     -> {v.snippet}")
            print()

    return 0 if report.passed else 1


if __name__ == "__main__":
    sys.exit(main())
