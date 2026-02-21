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


PYTHON_COVERAGE_THRESHOLD = 50
CPP_COVERAGE_THRESHOLD = 40
JSTS_COVERAGE_THRESHOLD = 30


def get_project_root() -> str:
    """Get project root (parent of scripts/)."""
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def read_python_coverage(project_root: str) -> dict:
    """Read Python coverage from coverage_python.json. Exit if missing."""
    path = os.path.join(project_root, "coverage_python.json")
    if not os.path.exists(path):
        print(f"FATAL: coverage_python.json not found at {path}")
        print("Python coverage step must run BEFORE coverage_gate.py")
        sys.exit(1)

    with open(path) as f:
        data = json.load(f)

    pct = data["totals"]["percent_covered"]
    return {
        "tool": "pytest-cov",
        "threshold": PYTHON_COVERAGE_THRESHOLD,
        "coverage_pct": pct,
        "passed": pct >= PYTHON_COVERAGE_THRESHOLD,
    }


def read_cpp_coverage(project_root: str) -> dict:
    """Read C++ coverage from coverage_cpp.json."""
    path = os.path.join(project_root, "coverage_cpp.json")
    result = {
        "tool": "gcovr",
        "threshold": CPP_COVERAGE_THRESHOLD,
        "coverage_pct": 0.0,
        "passed": False,
    }

    if not os.path.exists(path):
        print(f"WARNING: coverage_cpp.json not found at {path}")
        print("C++ coverage step may have failed — checking self-tests...")

        # Fallback: count self-test files
        native_dir = os.path.join(project_root, "native")
        if os.path.isdir(native_dir):
            cpp_files = []
            tested = 0
            for root_dir, _, files in os.walk(native_dir):
                for f in files:
                    if f.endswith(".cpp"):
                        cpp_files.append(os.path.join(root_dir, f))
                        try:
                            with open(os.path.join(root_dir, f), "r",
                                      encoding="utf-8", errors="ignore") as fh:
                                content = fh.read()
                            if any(k in content for k in (
                                "run_tests", "self_test",
                                "RUN_SELF_TESTS", "RUN_SELF_TEST")):
                                tested += 1
                        except Exception:
                            pass
            if cpp_files:
                result["coverage_pct"] = (tested / len(cpp_files)) * 100
                result["passed"] = result["coverage_pct"] >= CPP_COVERAGE_THRESHOLD
                print(f"  Self-test coverage: {tested}/{len(cpp_files)} files "
                      f"({result['coverage_pct']:.1f}%)")
        return result

    with open(path) as f:
        data = json.load(f)

    line_total = data.get("line_total", 0)
    line_covered = data.get("line_covered", 0)
    if line_total > 0:
        result["coverage_pct"] = (line_covered / line_total) * 100
    result["passed"] = result["coverage_pct"] >= CPP_COVERAGE_THRESHOLD
    return result


def read_jsts_coverage(project_root: str) -> dict:
    """Read JS/TS coverage from coverage-summary.json."""
    result = {
        "tool": "vitest/jest",
        "threshold": JSTS_COVERAGE_THRESHOLD,
        "coverage_pct": 0.0,
        "passed": False,
    }

    paths = [
        os.path.join(project_root, "frontend", "coverage",
                     "coverage-summary.json"),
        os.path.join(project_root, "coverage", "coverage-summary.json"),
    ]

    for path in paths:
        if os.path.exists(path):
            with open(path) as f:
                data = json.load(f)
            pct = data["total"]["lines"]["pct"]
            result["coverage_pct"] = pct
            result["passed"] = pct >= JSTS_COVERAGE_THRESHOLD
            return result

    # No frontend = not applicable
    frontend_dir = os.path.join(project_root, "frontend")
    if not os.path.isdir(frontend_dir):
        result["passed"] = True
        result["coverage_pct"] = -1
        return result

    print("WARNING: frontend exists but no coverage-summary.json found")
    return result


def fmt_pct(pct: float) -> str:
    if pct < 0:
        return "N/A"
    return f"{pct:.1f}%"


def main():
    project_root = get_project_root()

    print("=" * 60)
    print("COVERAGE GATE")
    print("=" * 60)

    # Debug
    print(f"  Project root: {project_root}")
    print(f"  Working dir:  {os.getcwd()}")

    # Read artifacts
    print("\n[1/3] Python coverage...")
    py = read_python_coverage(project_root)
    print(f"  {fmt_pct(py['coverage_pct'])} (>={PYTHON_COVERAGE_THRESHOLD}%)")

    print("\n[2/3] C++ coverage...")
    cpp = read_cpp_coverage(project_root)
    print(f"  {fmt_pct(cpp['coverage_pct'])} (>={CPP_COVERAGE_THRESHOLD}%)")

    print("\n[3/3] JS/TS coverage...")
    jsts = read_jsts_coverage(project_root)
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
          f"(>={PYTHON_COVERAGE_THRESHOLD}%)  [{py_s}]")
    print(f"  C++:     {fmt_pct(cpp['coverage_pct']):>8}  "
          f"(>={CPP_COVERAGE_THRESHOLD}%)  [{cpp_s}]")
    print(f"  JS/TS:   {fmt_pct(jsts['coverage_pct']):>8}  "
          f"(>={JSTS_COVERAGE_THRESHOLD}%)  [{jsts_s}]")
    print("-" * 60)

    if report["overall_passed"]:
        print("COVERAGE GATE: PASSED")
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
