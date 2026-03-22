# AGENT-SCRIPTS Report

Scope: `scripts/`

## Summary
- Files: 22 total
- Python files: 15
- PowerShell files: 6
- Shell files: 1
- README/docs: none
- Bare `pass` hits: 5, all in exception-handling/cleanup paths
- Import probe: 13/15 Python scripts imported cleanly, 2 timed out

## Evidence
- `pytest scripts -q -p no:warnings` -> `no tests ran in 0.10s` (exit 1)
- `python -m compileall scripts` -> passed
- Per-file import probe:
  - `scripts/antigravity_harness.py` OK
  - `scripts/ci_banned_tokens.py` OK
  - `scripts/ci_security_scan.py` OK
  - `scripts/coverage_gate.py` OK
  - `scripts/db_backup.py` OK
  - `scripts/ingestion_bootstrap.py` OK
  - `scripts/migrate_checkpoint_to_v2.py` OK
  - `scripts/migrate_pt_to_safetensors.py` OK
  - `scripts/reliability_gate.py` OK
  - `scripts/remediation_scan.py` OK
  - `scripts/security_regression_scan.py` OK
  - `scripts/training_readiness.py` OK
  - `scripts/wireguard_config.py` OK
  - `scripts/bulk_nvd_ingest.py` TIMEOUT
  - `scripts/fast_bridge_ingest.py` TIMEOUT
- Static-analysis tool check from the shared environment:
  - `ruff`, `flake8`, `pylint`, `mypy`, `pyright`, `radon`, `vulture`, `bandit`, `semgrep`, `locust`, `memory-profiler` are missing from `.venv`

## Category Scores
- C1 Existence & Completeness: 8.0/10
- C2 Static Analysis: 0.0/10
- C3 Unit Tests: 0.0/10
- C4 Integration Tests: 0.0/10
- C5 Data Quality & Accuracy: 0.0/10
- C6 Performance & Load: 0.0/10
- C7 Stability & Resilience: 0.0/10
- C8 Scalability: 0.0/10
- C9 Governance & Security: 3.0/10

## Weighted Score
- Weighted total: 0.6/10
- Tag: `🔴 RED`
- Sub-tags: none

## Findings
- HIGH: `scripts/bulk_nvd_ingest.py:253-288` executes a full ingestion/reporting path at module import time, which caused the import probe to time out.
- HIGH: `scripts/fast_bridge_ingest.py:249-284` executes persistence/reporting work at module import time, which caused the import probe to time out.

## Hollow Code
- No hollow/pass-only functions found.
- The five bare `pass` lines are in exception handlers or cleanup blocks:
  - `scripts/ci_security_scan.py:170`
  - `scripts/fast_bridge_ingest.py:57`
  - `scripts/ingestion_bootstrap.py:82`
  - `scripts/migrate_pt_to_safetensors.py:144`
  - `scripts/remediation_scan.py:284`

## Blockers
- No formal `scripts/` test suite exists.
- Static-analysis tooling is not installed locally.
- `bulk_nvd_ingest.py` and `fast_bridge_ingest.py` are not import-safe.

## Total Checks Run
- 1 pytest command
- 1 compileall command
- 15 per-file import probes
- 1 TODO/FIXME/stub scan
- 1 bare-`pass` scan
