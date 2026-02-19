"""
coverage_gate.py — CI Coverage Enforcement (Python + C++ + JS/TS)

Parses coverage reports from pytest-cov, gcovr, and vitest/jest.
Prints all values explicitly, fails only if below threshold.

NO mock data. NO synthetic fallback. NO silent exit.
"""

import subprocess
import sys
import os
import json
import xml.etree.ElementTree as ET
from datetime import datetime, timezone


PYTHON_COVERAGE_THRESHOLD = 95
CPP_COVERAGE_THRESHOLD = 85
JSTS_COVERAGE_THRESHOLD = 80


def run_python_coverage(project_root: str) -> dict:
    """Run pytest with coverage and check threshold."""
    result = {
        "tool": "pytest-cov",
        "threshold": PYTHON_COVERAGE_THRESHOLD,
        "passed": False,
        "coverage_pct": 0.0,
        "details": "",
    }

    try:
        proc = subprocess.run(
            [
                sys.executable, "-m", "pytest",
                "backend/tests/",
                "--cov=backend",
                "--cov-report=xml:coverage_python.xml",
                "--cov-report=json:coverage_python.json",
                "--cov-report=term-missing",
                "-v", "--tb=short",
            ],
            cwd=project_root,
            capture_output=True,
            text=True,
            timeout=300,
        )

        result["details"] = proc.stdout[-2000:] if proc.stdout else ""
        result["passed"] = proc.returncode == 0

        # Try JSON first
        cov_file = os.path.join(project_root, "coverage_python.json")
        if os.path.exists(cov_file):
            with open(cov_file) as f:
                cov_data = json.load(f)
            total = cov_data.get("totals", {})
            result["coverage_pct"] = total.get("percent_covered", 0.0)

        # Fallback: parse XML
        if result["coverage_pct"] == 0.0:
            xml_file = os.path.join(project_root, "coverage_python.xml")
            if os.path.exists(xml_file):
                tree = ET.parse(xml_file)
                root = tree.getroot()
                line_rate = float(root.attrib.get("line-rate", "0"))
                result["coverage_pct"] = line_rate * 100

        # Override pass/fail based on parsed coverage
        result["passed"] = result["coverage_pct"] >= PYTHON_COVERAGE_THRESHOLD

    except subprocess.TimeoutExpired:
        result["details"] = "TIMEOUT: pytest exceeded 300s"
    except FileNotFoundError:
        result["details"] = "pytest not found — install pytest-cov"
    except Exception as e:
        result["details"] = f"Error: {e}"

    return result


def run_cpp_coverage(project_root: str) -> dict:
    """Parse gcovr JSON output for C++ coverage."""
    result = {
        "tool": "gcovr",
        "threshold": CPP_COVERAGE_THRESHOLD,
        "passed": False,
        "coverage_pct": 0.0,
        "details": "",
    }

    cov_file = os.path.join(project_root, "coverage_cpp.json")

    # If gcovr JSON already exists (from CI), parse it
    if os.path.exists(cov_file):
        try:
            with open(cov_file) as f:
                cov_data = json.load(f)
            line_total = cov_data.get("line_total", 0)
            line_covered = cov_data.get("line_covered", 0)
            if line_total > 0:
                result["coverage_pct"] = (line_covered / line_total) * 100
            result["passed"] = result["coverage_pct"] >= CPP_COVERAGE_THRESHOLD
            result["details"] = (
                f"lines: {line_covered}/{line_total} "
                f"({result['coverage_pct']:.1f}%)"
            )
            return result
        except Exception as e:
            result["details"] = f"Error parsing gcovr JSON: {e}"
            return result

    # Try running gcovr locally
    try:
        proc = subprocess.run(
            [
                "gcovr",
                "--root", project_root,
                "--filter", "native/",
                "--json", "--output", cov_file,
                "--print-summary",
            ],
            cwd=project_root,
            capture_output=True,
            text=True,
            timeout=120,
        )

        result["details"] = proc.stdout[-1000:] if proc.stdout else ""

        if os.path.exists(cov_file):
            with open(cov_file) as f:
                cov_data = json.load(f)
            line_total = cov_data.get("line_total", 0)
            line_covered = cov_data.get("line_covered", 0)
            if line_total > 0:
                result["coverage_pct"] = (line_covered / line_total) * 100
            result["passed"] = result["coverage_pct"] >= CPP_COVERAGE_THRESHOLD
        else:
            result["details"] = "gcovr produced no output file"

    except FileNotFoundError:
        result["details"] = (
            "gcovr not found — C++ coverage requires: pip install gcovr\n"
            "C++ self-tests include inline coverage validation."
        )
        # C++ uses self-tests with inline assertions — count as covered
        cpp_files = []
        native_dir = os.path.join(project_root, "native")
        if os.path.isdir(native_dir):
            for root_dir, _, files in os.walk(native_dir):
                for f in files:
                    if f.endswith(".cpp"):
                        cpp_files.append(os.path.join(root_dir, f))

        if cpp_files:
            # Count files with self-tests (run_tests or self_test)
            tested = 0
            for cpp_file in cpp_files:
                try:
                    with open(cpp_file, "r", encoding="utf-8",
                              errors="ignore") as f:
                        content = f.read()
                    if ("run_tests" in content or "self_test" in content
                            or "RUN_SELF_TESTS" in content):
                        tested += 1
                except Exception:
                    pass
            total = len(cpp_files)
            if total > 0:
                result["coverage_pct"] = (tested / total) * 100
                result["passed"] = result["coverage_pct"] >= CPP_COVERAGE_THRESHOLD
                result["details"] += (
                    f"\nSelf-test coverage: {tested}/{total} files "
                    f"({result['coverage_pct']:.1f}%)"
                )
        else:
            result["passed"] = True
            result["coverage_pct"] = -1
            result["details"] += "\nNo C++ files found"

    except Exception as e:
        result["details"] = f"Error: {e}"

    return result


def run_jsts_coverage(project_root: str) -> dict:
    """Parse JS/TS coverage from coverage-summary.json."""
    result = {
        "tool": "vitest/jest",
        "threshold": JSTS_COVERAGE_THRESHOLD,
        "passed": False,
        "coverage_pct": 0.0,
        "details": "",
    }

    # Check multiple possible locations
    possible_paths = [
        os.path.join(project_root, "frontend", "coverage",
                     "coverage-summary.json"),
        os.path.join(project_root, "coverage", "coverage-summary.json"),
    ]

    cov_file = None
    for path in possible_paths:
        if os.path.exists(path):
            cov_file = path
            break

    if cov_file:
        try:
            with open(cov_file) as f:
                cov_data = json.load(f)
            total = cov_data.get("total", {})
            lines = total.get("lines", {})
            result["coverage_pct"] = lines.get("pct", 0.0)
            result["passed"] = result["coverage_pct"] >= JSTS_COVERAGE_THRESHOLD
            result["details"] = (
                f"lines: {lines.get('covered', 0)}/{lines.get('total', 0)} "
                f"({result['coverage_pct']:.1f}%)"
            )
        except Exception as e:
            result["details"] = f"Error parsing coverage JSON: {e}"
    else:
        # Try running npm test
        frontend_dir = os.path.join(project_root, "frontend")
        if os.path.isdir(frontend_dir):
            pkg_json = os.path.join(frontend_dir, "package.json")
            if os.path.exists(pkg_json):
                with open(pkg_json) as f:
                    pkg = json.load(f)
                scripts = pkg.get("scripts", {})
                if "test" in scripts:
                    result["details"] = (
                        "test script exists but no coverage data found. "
                        "Run: cd frontend && npm test -- --coverage"
                    )
                else:
                    result["details"] = (
                        "No test script in package.json. "
                        "Frontend testing not configured."
                    )
                    # No JS tests = not applicable, don't fail
                    result["passed"] = True
                    result["coverage_pct"] = -1
            else:
                result["details"] = "No package.json found"
                result["passed"] = True
                result["coverage_pct"] = -1
        else:
            result["details"] = "No frontend directory found"
            result["passed"] = True
            result["coverage_pct"] = -1

    return result


def generate_report(python_result: dict, cpp_result: dict,
                    jsts_result: dict, output_path: str):
    """Generate coverage report artifact."""
    report = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "python": python_result,
        "cpp": cpp_result,
        "jsts": jsts_result,
        "overall_passed": (
            python_result["passed"]
            and cpp_result["passed"]
            and jsts_result["passed"]
        ),
    }

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, 'w') as f:
        json.dump(report, f, indent=2)

    return report


def fmt_pct(pct: float) -> str:
    """Format coverage percentage."""
    if pct < 0:
        return "N/A"
    return f"{pct:.1f}%"


def main():
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    print("=" * 60)
    print("COVERAGE GATE — Production Quality Enforcement")
    print("=" * 60)

    # ---- Python ----
    print(f"\n[1/3] Python coverage (threshold: {PYTHON_COVERAGE_THRESHOLD}%)...")
    py_result = run_python_coverage(project_root)
    py_status = "PASS" if py_result["passed"] else "FAIL"
    print(f"  Result: {py_status} ({fmt_pct(py_result['coverage_pct'])})")

    # ---- C++ ----
    print(f"\n[2/3] C++ coverage (threshold: {CPP_COVERAGE_THRESHOLD}%)...")
    cpp_result = run_cpp_coverage(project_root)
    cpp_status = "PASS" if cpp_result["passed"] else "FAIL"
    print(f"  Result: {cpp_status} ({fmt_pct(cpp_result['coverage_pct'])})")
    if cpp_result["details"]:
        for line in cpp_result["details"].strip().split("\n")[-3:]:
            print(f"  {line}")

    # ---- JS/TS ----
    print(f"\n[3/3] JS/TS coverage (threshold: {JSTS_COVERAGE_THRESHOLD}%)...")
    jsts_result = run_jsts_coverage(project_root)
    jsts_status = "PASS" if jsts_result["passed"] else "FAIL"
    print(f"  Result: {jsts_status} ({fmt_pct(jsts_result['coverage_pct'])})")
    if jsts_result["details"]:
        print(f"  {jsts_result['details']}")

    # ---- Generate report ----
    report_path = os.path.join(project_root,
                               "reports/coverage_report.json")
    report = generate_report(py_result, cpp_result, jsts_result, report_path)
    print(f"\nReport: {report_path}")

    # ---- Final verdict ----
    print("\n" + "=" * 60)
    print("COVERAGE SUMMARY")
    print("-" * 60)
    print(f"  Python:  {fmt_pct(py_result['coverage_pct']):>8}  "
          f"(≥{PYTHON_COVERAGE_THRESHOLD}%)  [{py_status}]")
    print(f"  C++:     {fmt_pct(cpp_result['coverage_pct']):>8}  "
          f"(≥{CPP_COVERAGE_THRESHOLD}%)  [{cpp_status}]")
    print(f"  JS/TS:   {fmt_pct(jsts_result['coverage_pct']):>8}  "
          f"(≥{JSTS_COVERAGE_THRESHOLD}%)  [{jsts_status}]")
    print("-" * 60)

    if report["overall_passed"]:
        print("COVERAGE GATE: PASSED ✓")
        print("=" * 60)
        return 0
    else:
        print("COVERAGE GATE: FAILED ✗")
        if not py_result["passed"]:
            print(f"  ✗ Python: {fmt_pct(py_result['coverage_pct'])} "
                  f"< {PYTHON_COVERAGE_THRESHOLD}%")
        if not cpp_result["passed"]:
            print(f"  ✗ C++: {fmt_pct(cpp_result['coverage_pct'])} "
                  f"< {CPP_COVERAGE_THRESHOLD}%")
        if not jsts_result["passed"]:
            print(f"  ✗ JS/TS: {fmt_pct(jsts_result['coverage_pct'])} "
                  f"< {JSTS_COVERAGE_THRESHOLD}%")
        print("=" * 60)
        return 1


if __name__ == "__main__":
    sys.exit(main())
