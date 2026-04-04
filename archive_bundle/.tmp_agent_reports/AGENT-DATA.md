# AGENT-DATA Report

Scope: `data/`

## Evidence
- `data/` exists and contains 6 files plus the `data/db/` subtree.
- JSON/JSONL integrity checks passed for:
  - `data/approval_ledger.jsonl` -> 105 lines, valid JSONL, hash chain OK.
  - `data/host_action_ledger.jsonl` -> 211 lines, valid JSONL, hash chain OK.
  - `data/field_state.json` -> valid JSON, 23 fields recorded.
  - `data/runtime_status.json` -> valid JSON, reports `data_freshness=fresh`, `determinism_pass=true`, `freeze_valid=true`, `precision_breach=true`.
  - `data/scan_state.json` -> valid JSON.
  - `data/db/targets/27660a49-57b4-4fff-9e11-f8161dd06e33.json` -> valid JSON target record.
- Storage layout check:
  - `data/db/activity_log`, `data/db/bounties`, `data/db/sessions`, and `data/db/users` are empty directories.
  - `data/db/targets/` contains 1 target record.
- Secret sweep:
  - No obvious credentials or private keys were found in `data/`.
  - Generic token-like strings exist in ledgers and field state, but they are expected schema terms rather than secrets.

## Category Scores
- C1 Existence & Completeness: 10.0/10
- C5 Data Quality & Accuracy: 8.5/10
- C8 Scalability & Storage: 7.5/10
- C9 Governance & Security: 7.5/10

## Calculation
- Applicable weights only: C1=5, C5=20, C8=10, C9=5
- Weighted total = `(10.0*5 + 8.5*20 + 7.5*10 + 7.5*5) / 40 = 8.4/10`

## Findings
- HIGH: `data/runtime_status.json` reports `precision_breach: true`, so the latest runtime snapshot is not fully clean even though determinism and freeze validation are passing.
- MEDIUM: `data/db/` is structurally valid but still shallow; most subdirectories are empty and there is no sharding by source/date yet.

## Blockers
- Dedicated secret-scanning tools (`trufflehog`, `gitleaks`) were not run in this pass because the scope is data-only and the local audit environment does not have them installed.

## Tests Run
- 7 validation checks:
  - JSON parse sweep
  - JSONL parse sweep
  - ledger hash-chain verification
  - target record schema check
  - storage layout scan
  - secret-pattern sweep
  - runtime status inspection
