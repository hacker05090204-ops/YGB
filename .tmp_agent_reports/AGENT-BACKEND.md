# AGENT-BACKEND Report

Scope: `backend/` excluding `backend/ingestion/`

## Summary
- Python files: 234
- LOC: 56919
- Test files: 102
- Source files: 132
- Test ratio: 0.4359

## Category Scores
- C1 Existence & Completeness: 10.0/10 (PASS)
- C2 Static Analysis: 0.0/10 (BLOCKED)
- C3 Unit Tests: 6.5/10 (PASS_WITH_ONE_FAIL)
- C4 Integration Tests: 10.0/10 (PASS)
- C5 Data Quality & Accuracy: 0.0/10 (BLOCKED)
- C6 Performance & Load: 0.0/10 (BLOCKED)
- C7 Stability & Resilience: 0.0/10 (BLOCKED)
- C8 Scalability: 0.0/10 (BLOCKED)
- C9 Governance & Security: 8.0/10 (PASS_WITH_TOOLS_MISSING)

## Weighted Score
- Protocol-weighted backend score: 3.4/10
- Main reason it is low: categories 2 and 5-8 were blocked/unverified in this backend-only pass.

## Evidence
- Full pytest run: 1,982 collected, 1,976 passed, 5 skipped, 1 failed in 56.26s.
- Slowest tests: backend/tests/test_reliability.py::TestDependencyChecker::test_timeout_check (5.00s), backend/tests/test_ingestion.py::test_hackerone_adapter_skips_empty_and_caps (4.50s), backend/tests/test_label_injector.py::test_label_helpers_and_guard_paths (2.48s), backend/tests/test_training_trigger.py::test_incremental_trainer_run_epoch_emits_metrics (1.63s), backend/tests/test_coverage_boost3.py::TestAuthPasswordHashing::test_verify_password_v2_format (1.42s)
- Live health probe: /healthz 200, /readyz 503 because storage is INACTIVE.
- Circuit breaker probe: OPEN after 5 failures, HALF_OPEN after cooldown, CLOSED after 2 successes.

## Findings
- CRITICAL: `backend/tests/test_wiring_audit.py:47` fails because `CRITICAL_METRICS` includes GPU runtime metrics that are not part of the infrastructure/training-only union.
- HIGH: `backend/observability/metrics.py:51` defines GPU runtime metrics outside the union expected by the wiring audit.

## Blockers
- Coverage collection is blocked by `pytest-cov`/`coverage` throwing `PermissionError` on `C:\Users\Unkno`.
- Static-analysis and load-test tools are missing from the venv.
- `trufflehog` and `gitleaks` are missing.
