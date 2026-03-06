# Risk Register — YGB 18-Category Audit

| # | Category | Risk | Severity | Status | Evidence |
|---|----------|------|----------|--------|----------|
| 1 | **Functional** | Sync engine had no `--watch` entry point | Medium | ✅ Fixed | `start_full_stack.ps1` auto-starts sync |
| 2 | **Integration** | Duplicate routes `/health` vs `/api/health` | Low | ✅ Fixed | `/health` is alias, both work |
| 3 | **Dependency** | `requirements.txt` uses `>=` not `==` | Medium | ✅ Mitigated | `requirements-lock.txt` exists with `==` pins |
| 4 | **Security** | `.env_secrets.txt` tracked in git | **Critical** | ✅ Fixed | `git rm --cached`, added to `.gitignore` |
| 5 | **Security** | Vault unlock bypass (no session required) | **Critical** | ✅ Fixed | `vault_session.py` L66: mandatory ADMIN session |
| 6 | **Security** | OAuth JWT token in URL query params | **Critical** | ✅ Fixed | Token moved to HTTP-only cookies |
| 7 | **Security** | Video filename path traversal via JWT | **Critical** | ✅ Fixed | `video_streamer.py` L265: basename + char filter |
| 8 | **Security** | WS auth skips session revocation check | High | ✅ Fixed | `auth_guard.py` L89: session revocation parity |
| 9 | **Security** | Video JWT import-time crash | High | ✅ Fixed | Deferred to `_get_jwt_secret()` on first use |
| 10 | **Security** | IDOR: no ownership on workflows/sessions | High | ✅ Fixed | `owner_id` on 6 creation sites, 3 access checks |
| 11 | **Security** | Startup binds `0.0.0.0` + `Everyone` SMB | High | ✅ Fixed | Default `127.0.0.1`, `-LanShare` opt-in |
| 12 | **Security** | Secrets could leak into logs | Medium | ✅ Fixed | `log_config.py`: regex redaction of password/token/key |
| 13 | **Privacy** | GeoIP/email exposed in URL params | Medium | ✅ Fixed | Profile moved to cookies, cleared after read |
| 14 | **Data Integrity** | DB writes lack transaction boundaries | Medium | ✅ Fixed | `db_safety.py`: `db_transaction()` + `safe_db_write()` |
| 15 | **Accuracy** | Synthetic `recall = accuracy * 0.95` | High | ✅ Fixed | Returns `null` + `is_measured: false` |
| 16 | **Accuracy** | Hardcoded `ece: 0.0`, `determinism: True` | High | ✅ Fixed | Returns `null` for unmeasured fields |
| 17 | **Accuracy** | Fabricated `loss_trend: -0.001` | Medium | ✅ Fixed | Returns `null` |
| 18 | **Stability** | 82+ `except Exception: pass` blocks | High | ✅ Mitigated | Typed `YGBError` hierarchy + global handler |
| 19 | **Availability** | No readiness probe | Medium | ✅ Fixed | `/readyz` checks DB + storage |
| 20 | **Concurrency** | 5 global vars without locks | High | ✅ Fixed | `runtime_state.py`: threaded Lock + atomic ops |
| 21 | **Configuration** | `.env` missing on new devices = crash | High | ✅ Fixed | `.env.example` + `bootstrap-env.ps1` + `validate-env.ps1` |
| 22 | **Configuration** | No startup env validation | Medium | ✅ Fixed | `start_full_stack.ps1` validates required vars |
| 23 | **Deployment** | Sync engine requires manual start | Medium | ✅ Fixed | Auto-starts in `start_full_stack.ps1` |
| 24 | **Observability** | No structured log format | Medium | ✅ Fixed | `log_config.py`: JSON format with correlation IDs |
| 25 | **Test Coverage** | No IDOR/ownership regression tests | High | ✅ Fixed | 45 tests across 10 risk categories |
| 26 | **Maintainability** | API version not tracked | Medium | ✅ Fixed | `api_version: 2` in accuracy/runtime responses |
| 27 | **Compliance** | Secret rotation not documented | Low | ✅ Fixed | `docs/ENV_SETUP.md` documents secret management |
| 28 | **Scalability** | In-memory workflow state (no persistence) | Low | 🟡 Deferred | Acceptable for single-node; needs Redis for multi-node |
| 29 | **Performance** | No HTTP connection pooling for GitHub API | Low | 🟡 Deferred | Reuse `_github_http` session exists |
