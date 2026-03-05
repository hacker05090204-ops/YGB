"""
Antigravity Runtime Harness — Deterministic Safety/Stability Gate Verification

Runs all critical gates and reports GO/NO-GO for training readiness.
Must exit 0 for GO, 1 for NO-GO.

Usage:
    python scripts/antigravity_harness.py
"""

import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent


def _run(cmd: list[str], label: str) -> dict:
    """Run a command and capture result."""
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd=str(PROJECT_ROOT),
            timeout=300,
            env={**os.environ, "PYTHONPATH": str(PROJECT_ROOT)},
        )
        return {
            "label": label,
            "exit_code": result.returncode,
            "passed": result.returncode == 0,
            "stdout_tail": result.stdout[-500:] if result.stdout else "",
            "stderr_tail": result.stderr[-500:] if result.stderr else "",
        }
    except subprocess.TimeoutExpired:
        return {"label": label, "exit_code": -1, "passed": False, "reason": "TIMEOUT"}
    except FileNotFoundError as e:
        return {"label": label, "exit_code": -1, "passed": False, "reason": "command not found"}


def check_bind_host_default() -> dict:
    """Verify API_HOST defaults to 127.0.0.1, not 0.0.0.0."""
    server_path = PROJECT_ROOT / "api" / "server.py"
    content = server_path.read_text(encoding="utf-8", errors="ignore")
    # Check the uvicorn.run default
    secure = 'os.getenv("API_HOST", "127.0.0.1")' in content
    insecure = 'os.getenv("API_HOST", "0.0.0.0")' in content
    return {
        "label": "bind_host_default",
        "passed": secure and not insecure,
        "detail": "127.0.0.1" if secure else "0.0.0.0 (INSECURE)",
    }


def check_revocation_durability() -> dict:
    """Verify revocation store defaults to durable backend."""
    store_path = PROJECT_ROOT / "backend" / "auth" / "revocation_store.py"
    content = store_path.read_text(encoding="utf-8", errors="ignore")
    durable = '"file"' in content and 'REVOCATION_BACKEND", "file"' in content
    return {
        "label": "revocation_durability",
        "passed": durable,
        "detail": "Default=file (durable)" if durable else "Default=memory (NOT durable)",
    }


def check_no_error_leakage() -> dict:
    """Verify no exception text leaks into API responses."""
    files_to_check = [
        PROJECT_ROOT / "api" / "server.py",
        PROJECT_ROOT / "backend" / "api" / "training_progress.py",
        PROJECT_ROOT / "backend" / "api" / "runtime_api.py",
    ]
    leaks = []
    import re
    leak_patterns = [
        re.compile(r'(reason|detail|message|error).*f["\'].*\{(e|exc|err)\}'),
        re.compile(r'(reason|detail|message|error).*str\((e|exc|err)\)'),
    ]
    for fpath in files_to_check:
        if not fpath.exists():
            continue
        content = fpath.read_text(encoding="utf-8", errors="ignore")
        for i, line in enumerate(content.splitlines(), 1):
            # Skip comments and log lines
            stripped = line.strip()
            if stripped.startswith("#") or "logger." in stripped or "print(" in stripped:
                continue
            for pat in leak_patterns:
                if pat.search(line):
                    leaks.append(f"{fpath.name}:{i}")
    return {
        "label": "no_error_leakage",
        "passed": len(leaks) == 0,
        "leaks": leaks,
    }


def check_incident_recursive_search() -> dict:
    """Verify incident reconciler uses recursive search."""
    path = PROJECT_ROOT / "backend" / "governance" / "incident_reconciler.py"
    content = path.read_text(encoding="utf-8", errors="ignore")
    uses_rglob = ".rglob(" in content
    return {
        "label": "incident_recursive_search",
        "passed": uses_rglob,
        "detail": "rglob" if uses_rglob else "glob (non-recursive)",
    }


def check_governance_classification() -> dict:
    """Verify backend/governance Python is PRODUCTION, not CONFIG/DOCS."""
    sys.path.insert(0, str(PROJECT_ROOT))
    from scripts.remediation_scan import classify_path
    test_path = str(PROJECT_ROOT / "backend" / "governance" / "incident_reconciler.py")
    classification = classify_path(test_path)
    return {
        "label": "governance_classification",
        "passed": classification == "PRODUCTION",
        "detail": f"backend/governance/incident_reconciler.py => {classification}",
    }


def main():
    print("=" * 60)
    print("  ANTIGRAVITY RUNTIME HARNESS")
    print("=" * 60)
    print(f"  Timestamp: {datetime.now(timezone.utc).isoformat()}")
    print(f"  Project:   {PROJECT_ROOT}")
    print()

    checks = []

    # Static checks
    checks.append(check_bind_host_default())
    checks.append(check_revocation_durability())
    checks.append(check_no_error_leakage())
    checks.append(check_incident_recursive_search())
    checks.append(check_governance_classification())

    # Scanner checks
    checks.append(_run(
        [sys.executable, "scripts/ci_security_scan.py"],
        "ci_security_scan",
    ))
    checks.append(_run(
        [sys.executable, "scripts/remediation_scan.py"],
        "remediation_scan",
    ))

    # Print results
    print("-" * 60)
    all_pass = True
    for c in checks:
        status = "PASS" if c["passed"] else "FAIL"
        marker = "✓" if c["passed"] else "✗"
        print(f"  {marker} [{status}] {c['label']}")
        if not c["passed"]:
            all_pass = False
            detail = c.get("detail") or c.get("reason") or c.get("leaks") or ""
            if detail:
                print(f"      {detail}")

    print("-" * 60)

    # Save report
    report_path = PROJECT_ROOT / "reports" / "antigravity_harness_report.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "verdict": "GO" if all_pass else "NO-GO",
        "checks": checks,
    }
    report_path.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")

    if all_pass:
        print("VERDICT: GO")
        print("=" * 60)
        return 0
    else:
        print("VERDICT: NO-GO")
        print("=" * 60)
        return 1


if __name__ == "__main__":
    sys.exit(main())
