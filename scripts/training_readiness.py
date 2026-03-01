"""
training_readiness.py — Automated Training Readiness Verification

Validates all CI coverage gates, infrastructure, and telemetry components
are in place before training can begin.

Usage:
    python scripts/training_readiness.py

Exit codes:
    0 = All checks pass, READY for training
    1 = One or more checks failed
"""

import json
import os
import sys
import re


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _read_text(path: str) -> str:
    """Read text robustly across mixed encodings in this repository."""
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        return f.read()


def check(name, condition, detail=""):
    status = "PASS" if condition else "FAIL"
    icon = "+" if condition else "x"
    print(f"  [{icon}] {name}")
    if detail and not condition:
        print(f"      -> {detail}")
    return condition


def main():
    print("=" * 60)
    print("TRAINING READINESS VERIFICATION")
    print("=" * 60)
    results = []

    # ---- 1. C++ Test Harness ----
    print("\n[1/7] C++ Test Infrastructure")
    results.append(check(
        "run_cpp_tests.cpp exists",
        os.path.isfile(os.path.join(ROOT, "native", "run_cpp_tests.cpp")),
        "Missing native/run_cpp_tests.cpp"
    ))
    results.append(check(
        "build_cpp_tests.sh exists",
        os.path.isfile(os.path.join(ROOT, "scripts", "build_cpp_tests.sh")),
        "Missing scripts/build_cpp_tests.sh"
    ))

    # Check all 10 wrapper files
    wrappers = [
        "tw_precision_monitor", "tw_drift_monitor", "tw_freeze_invalidator",
        "tw_shadow_merge_validator", "tw_dataset_entropy", "tw_curriculum_scheduler",
        "tw_cross_device_validator", "tw_hunt_precision", "tw_hunt_duplicate",
        "tw_hunt_scope",
    ]
    wrapper_dir = os.path.join(ROOT, "native", "test_wrappers")
    wrapper_count = sum(
        1 for w in wrappers
        if os.path.isfile(os.path.join(wrapper_dir, f"{w}.cpp"))
    )
    results.append(check(
        f"C++ test wrappers ({wrapper_count}/10)",
        wrapper_count == 10,
        f"Only {wrapper_count}/10 wrappers found in native/test_wrappers/"
    ))

    # ---- 2. JS/TS Coverage ----
    print("\n[2/7] JS/TS Test Infrastructure")
    results.append(check(
        "ygb-api.test.ts exists",
        os.path.isfile(os.path.join(ROOT, "frontend", "__tests__", "ygb-api.test.ts")),
        "Missing frontend/__tests__/ygb-api.test.ts"
    ))
    results.append(check(
        "utils.test.ts exists",
        os.path.isfile(os.path.join(ROOT, "frontend", "__tests__", "utils.test.ts")),
        "Missing frontend/__tests__/utils.test.ts"
    ))
    results.append(check(
        "vitest.config.ts exists",
        os.path.isfile(os.path.join(ROOT, "frontend", "vitest.config.ts")),
        "Missing frontend/vitest.config.ts"
    ))

    # ---- 3. Training Telemetry (C++) ----
    print("\n[3/7] Training Telemetry Module")
    telemetry_path = os.path.join(ROOT, "native", "training_runtime", "training_telemetry.cpp")
    results.append(check(
        "training_telemetry.cpp exists",
        os.path.isfile(telemetry_path),
        "Missing native/training_runtime/training_telemetry.cpp"
    ))
    if os.path.isfile(telemetry_path):
        content = _read_text(telemetry_path)
        results.append(check(
            "Has run_tests() self-validation",
            "run_tests()" in content,
            "training_telemetry.cpp must include run_tests()"
        ))
        results.append(check(
            "Has atomic persist (fopen/rename)",
            "rename" in content and "fopen" in content,
            "No atomic persist pattern found"
        ))
        # Validate fields written by native telemetry payload.
        required_fields = [
            "epoch",
            "loss",
            "precision",
            "ece",
            "kl_divergence",
            "gpu_temperature",
            "determinism_status",
            "freeze_status",
            "wall_clock_unix",
            "monotonic_start_time",
            "training_duration_seconds",
            "samples_per_second",
        ]
        missing = [f for f in required_fields if f not in content]
        results.append(check(
            f"All 12 telemetry fields present ({12 - len(missing)}/12)",
            len(missing) == 0,
            f"Missing fields: {', '.join(missing)}"
        ))

    # ---- 4. Backend Runtime API ----
    print("\n[4/7] Backend Runtime API")
    api_path = os.path.join(ROOT, "backend", "api", "runtime_api.py")
    results.append(check(
        "runtime_api.py exists",
        os.path.isfile(api_path),
        "Missing backend/api/runtime_api.py"
    ))
    if os.path.isfile(api_path):
        content = _read_text(api_path)
        results.append(check(
            "HMAC signing implemented",
            "hmac" in content.lower() and "sha256" in content.lower(),
            "No HMAC-SHA256 signing found"
        ))
        results.append(check(
            "Staleness detection",
            "stale" in content.lower(),
            "No staleness detection"
        ))

    test_path = os.path.join(ROOT, "backend", "tests", "test_runtime_api.py")
    results.append(check(
        "test_runtime_api.py exists",
        os.path.isfile(test_path),
        "Missing backend/tests/test_runtime_api.py"
    ))

    # ---- 5. Frontend Control Panel ----
    print("\n[5/7] Frontend Control Panel")
    page_path = os.path.join(ROOT, "frontend", "app", "control", "page.tsx")
    if os.path.isfile(page_path):
        content = _read_text(page_path)
        results.append(check(
            "Polls /runtime/status",
            "/runtime/status" in content,
            "No /runtime/status polling in page.tsx"
        ))
        runtime_poll_interval_ok = bool(
            re.search(r"setInterval\s*\(\s*fetchRuntimeStatus\s*,\s*(1000|3000|30000)\s*\)", content)
        )
        results.append(check(
            "Runtime polling interval configured",
            runtime_poll_interval_ok,
            "No recognized setInterval(fetchRuntimeStatus, N) found"
        ))
        results.append(check(
            "Stale warning displayed",
            "STALE" in content,
            "No stale data warning in UI"
        ))
        results.append(check(
            "Determinism status displayed",
            "determinism_status" in content,
            "Determinism not shown in UI"
        ))
    else:
        results.append(check("control/page.tsx exists", False, "Missing"))

    # ---- 6. CI Coverage Gate ----
    print("\n[6/7] CI Coverage Enforcement")
    gate_path = os.path.join(ROOT, "scripts", "coverage_gate.py")
    results.append(check(
        "coverage_gate.py exists",
        os.path.isfile(gate_path),
        "Missing scripts/coverage_gate.py"
    ))
    if os.path.isfile(gate_path):
        content = _read_text(gate_path)
        results.append(check(
            "Python threshold >=95%",
            "PYTHON_COVERAGE_THRESHOLD = 95" in content,
            "Python threshold not set to 95"
        ))
        results.append(check(
            "C++ threshold >=85%",
            "CPP_COVERAGE_THRESHOLD = 85" in content,
            "C++ threshold not set to 85"
        ))
        results.append(check(
            "JS/TS threshold >=80%",
            "JSTS_COVERAGE_THRESHOLD = 80" in content,
            "JS/TS threshold not set to 80"
        ))

    ci_path = os.path.join(ROOT, ".github", "workflows", "coverage-gate.yml")
    results.append(check(
        "coverage-gate.yml exists",
        os.path.isfile(ci_path),
        "Missing .github/workflows/coverage-gate.yml"
    ))

    # ---- 7. Coverage Reports Infra ----
    print("\n[7/7] Coverage Report Configuration")
    pyproject = os.path.join(ROOT, "pyproject.toml")
    results.append(check(
        "pyproject.toml exists",
        os.path.isfile(pyproject),
        "Missing pyproject.toml"
    ))

    # ---- Final Verdict ----
    total = len(results)
    passed = sum(results)
    failed = total - passed

    print("\n" + "=" * 60)
    print(f"READINESS: {passed}/{total} checks passed")
    print("-" * 60)

    if failed == 0:
        print("STATUS: [+] READY FOR TRAINING")
        print("All infrastructure, coverage gates, and telemetry verified.")
        print("=" * 60)
        return 0
    else:
        print(f"STATUS: [x] NOT READY ({failed} check(s) failed)")
        print("Fix the failing checks above before starting training.")
        print("=" * 60)
        return 1


if __name__ == "__main__":
    sys.exit(main())
