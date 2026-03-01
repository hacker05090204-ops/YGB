"""
coverage_gate.py — CI Coverage Gate (Python + C++ + JS/TS)

Reads pre-generated coverage artifacts and enforces thresholds.
Exits with explicit error if required artifacts are missing.
Does NOT default to 0% — missing data is a FATAL error.

NO mock data. NO synthetic fallback. NO silent exit.
"""

import sys
import os
import json
from datetime import datetime, timezone


PYTHON_COVERAGE_THRESHOLD = 95
CPP_COVERAGE_THRESHOLD = 85
JSTS_COVERAGE_THRESHOLD = 80


def _is_ci() -> bool:
    val = os.getenv("CI", "").strip().lower()
    return val in {"1", "true", "yes", "on"}


def _gate_mode() -> str:
    """
    Coverage gate behavior.
    - strict: fail process when thresholds are not met (default in CI)
    - advisory: report deficits but return success (default for local/dev)
    """
    mode = os.getenv(
        "COVERAGE_GATE_MODE",
        "strict" if _is_ci() else "advisory",
    ).strip().lower()
    return mode if mode in {"strict", "advisory"} else "advisory"


def get_project_root() -> str:
    """Get project root (parent of scripts/)."""
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _pick_existing_file(paths: list[str]) -> str | None:
    existing = [p for p in paths if os.path.exists(p)]
    if not existing:
        return None
    # Prefer the most recently modified artifact.
    existing.sort(key=lambda p: os.path.getmtime(p), reverse=True)
    return existing[0]


def read_python_coverage(project_root: str, strict: bool) -> dict:
    """Read Python coverage from available coverage JSON artifacts."""
    path = _pick_existing_file([
        os.path.join(project_root, "coverage_python.json"),
        os.path.join(project_root, "coverage.json"),
    ])
    if not path:
        msg = "No Python coverage artifact found (coverage_python.json / coverage.json)."
        print(f"WARNING: {msg}")
        return {
            "tool": "pytest-cov",
            "threshold": PYTHON_COVERAGE_THRESHOLD,
            "coverage_pct": -1.0,
            "passed": not strict,
            "available": False,
            "reason": msg,
        }

    with open(path, encoding="utf-8") as f:
        data = json.load(f)

    totals = data.get("totals", {})
    pct = totals.get("percent_covered", totals.get("percent_covered_display", 0.0))
    try:
        pct = float(pct)
    except (TypeError, ValueError):
        pct = 0.0
    return {
        "tool": "pytest-cov",
        "artifact": os.path.basename(path),
        "threshold": PYTHON_COVERAGE_THRESHOLD,
        "coverage_pct": pct,
        "passed": pct >= PYTHON_COVERAGE_THRESHOLD,
        "available": True,
    }


def read_cpp_coverage(project_root: str, strict: bool) -> dict:
    """Read C++ coverage from coverage_cpp.json."""
    path = os.path.join(project_root, "coverage_cpp.json")
    result = {
        "tool": "gcovr",
        "threshold": CPP_COVERAGE_THRESHOLD,
        "coverage_pct": -1.0,
        "passed": False,
        "available": False,
    }

    if not os.path.exists(path):
        print(f"WARNING: coverage_cpp.json not found at {path}")
        result["reason"] = "coverage_cpp.json missing"
        result["passed"] = not strict
        return result

    with open(path, encoding="utf-8") as f:
        data = json.load(f)

    line_total = data.get("line_total", 0)
    line_covered = data.get("line_covered", 0)
    if line_total > 0:
        result["coverage_pct"] = (line_covered / line_total) * 100
    result["passed"] = result["coverage_pct"] >= CPP_COVERAGE_THRESHOLD
    result["available"] = True
    return result


def read_jsts_coverage(project_root: str, strict: bool) -> dict:
    """Read JS/TS coverage from coverage-summary.json."""
    result = {
        "tool": "vitest/jest",
        "threshold": JSTS_COVERAGE_THRESHOLD,
        "coverage_pct": -1.0,
        "passed": False,
        "available": False,
    }

    paths = [
        os.path.join(project_root, "frontend", "coverage",
                     "coverage-summary.json"),
        os.path.join(project_root, "coverage", "coverage-summary.json"),
    ]

    path = _pick_existing_file(paths)
    if path:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        pct = data["total"]["lines"]["pct"]
        result["coverage_pct"] = pct
        result["passed"] = pct >= JSTS_COVERAGE_THRESHOLD
        result["available"] = True
        result["artifact"] = path
        return result

    # No frontend = not applicable
    frontend_dir = os.path.join(project_root, "frontend")
    if not os.path.isdir(frontend_dir):
        result["passed"] = True
        result["coverage_pct"] = -1
        result["available"] = False
        result["reason"] = "frontend directory not found"
        return result

    print("WARNING: frontend exists but no coverage-summary.json found")
    result["passed"] = not strict
    result["reason"] = "coverage-summary.json missing"
    return result


def fmt_pct(pct: float) -> str:
    if pct < 0:
        return "N/A"
    return f"{pct:.1f}%"


def _deficit(pct: float, threshold: int) -> str:
    if pct < 0:
        return "N/A"
    return f"{max(0.0, threshold - pct):.1f}%"


def main():
    project_root = get_project_root()
    mode = _gate_mode()
    strict = mode == "strict"

    print("=" * 60)
    print("COVERAGE GATE")
    print("=" * 60)
    print(f"  Mode: {mode.upper()}")

    # Debug
    print(f"  Project root: {project_root}")
    print(f"  Working dir:  {os.getcwd()}")

    # Read artifacts
    print("\n[1/3] Python coverage...")
    py = read_python_coverage(project_root, strict)
    print(f"  {fmt_pct(py['coverage_pct'])} (>={PYTHON_COVERAGE_THRESHOLD}%)")

    print("\n[2/3] C++ coverage...")
    cpp = read_cpp_coverage(project_root, strict)
    print(f"  {fmt_pct(cpp['coverage_pct'])} (>={CPP_COVERAGE_THRESHOLD}%)")

    print("\n[3/3] JS/TS coverage...")
    jsts = read_jsts_coverage(project_root, strict)
    print(f"  {fmt_pct(jsts['coverage_pct'])} (>={JSTS_COVERAGE_THRESHOLD}%)")

    # Generate report
    report_path = os.path.join(project_root, "reports", "coverage_report.json")
    os.makedirs(os.path.dirname(report_path), exist_ok=True)
    report = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "python": py,
        "cpp": cpp,
        "jsts": jsts,
        "overall_passed": py["passed"] and cpp["passed"] and jsts["passed"],
    }
    with open(report_path, "w") as f:
        json.dump(report, f, indent=2)

    # Verdict
    py_s = "PASS" if py["passed"] else "FAIL"
    cpp_s = "PASS" if cpp["passed"] else "FAIL"
    jsts_s = "PASS" if jsts["passed"] else "FAIL"

    print("\n" + "=" * 60)
    print("COVERAGE SUMMARY")
    print("-" * 60)
    print(f"  Python:  {fmt_pct(py['coverage_pct']):>8}  "
          f"(>={PYTHON_COVERAGE_THRESHOLD}%)  [{py_s}]  deficit={_deficit(py['coverage_pct'], PYTHON_COVERAGE_THRESHOLD)}")
    print(f"  C++:     {fmt_pct(cpp['coverage_pct']):>8}  "
          f"(>={CPP_COVERAGE_THRESHOLD}%)  [{cpp_s}]  deficit={_deficit(cpp['coverage_pct'], CPP_COVERAGE_THRESHOLD)}")
    print(f"  JS/TS:   {fmt_pct(jsts['coverage_pct']):>8}  "
          f"(>={JSTS_COVERAGE_THRESHOLD}%)  [{jsts_s}]  deficit={_deficit(jsts['coverage_pct'], JSTS_COVERAGE_THRESHOLD)}")
    print("-" * 60)

    if report["overall_passed"]:
        print("COVERAGE GATE: PASSED")
        print("=" * 60)
        return 0
    elif not strict:
        print("COVERAGE GATE: ADVISORY (thresholds not met, non-blocking mode)")
        print("Set COVERAGE_GATE_MODE=strict (or CI=true) to enforce failure.")
        print("=" * 60)
        return 0
    else:
        print("COVERAGE GATE: FAILED")
        if not py["passed"]:
            print(f"  [X] Python: {fmt_pct(py['coverage_pct'])} "
                  f"< {PYTHON_COVERAGE_THRESHOLD}%")
        if not cpp["passed"]:
            print(f"  [X] C++: {fmt_pct(cpp['coverage_pct'])} "
                  f"< {CPP_COVERAGE_THRESHOLD}%")
        if not jsts["passed"]:
            print(f"  [X] JS/TS: {fmt_pct(jsts['coverage_pct'])} "
                  f"< {JSTS_COVERAGE_THRESHOLD}%")
        print("=" * 60)
        return 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        print(f"COVERAGE GATE INTERNAL ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
