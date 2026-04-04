# Release Notes — Risk Remediation Sprint

## Version: 2.0.0

### Breaking Changes

**API v2 response contract** — Status endpoints now return `api_version: 2`:
- `/api/runtime/status`: `ece`, `drift_kl`, `duplicate_rate`, `determinism_status`, `freeze_status`, `loss_trend` → `null` when not measured (was hardcoded `0.0`/`true`/`-0.001`)
- `/api/accuracy/snapshot`: `recall`, `ece_score`, `dup_suppression_rate` → `null` when not measured (was fabricated from accuracy)
- New fields: `is_measured: bool`, `source: string`, `api_version: int`

**Migration**: Frontend should check `if (field !== null)` before display. Show "—" or "N/A" for null metrics.

**OAuth callback**: Token/session no longer in URL query params (moved to HTTP-only cookies). Frontend reads from cookies, falls back to URL params for backward compat.

### Security Fixes (Critical)
- Vault unlock requires mandatory ADMIN session (was optional)
- OAuth JWT moved from URL params to HTTP-only cookies
- Video filename from JWT sanitized against path traversal
- `.env_secrets.txt` removed from git tracking

### Security Fixes (High)
- WS auth now checks session revocation (parity with HTTP)
- Video JWT check deferred from import-time to first use
- IDOR ownership enforced on 6 creation + 3 access sites
- Default binding changed to `127.0.0.1` (was `0.0.0.0`)
- SMB share requires `-LanShare` flag (was auto-created `Everyone/FullAccess`)

### New Modules
- `backend/auth/ownership.py` — Resource ownership checks
- `backend/api/exceptions.py` — Typed exception hierarchy
- `backend/api/runtime_state.py` — Thread-safe shared state
- `backend/api/db_safety.py` — Transaction wrappers
- `backend/observability/log_config.py` — Structured JSON logging with secret redaction

### New Endpoints
- `GET /readyz` — Kubernetes-style readiness probe (returns 200/503)

### New Scripts
- `scripts/bootstrap-env.ps1` — One-command device onboarding
- `scripts/validate-env.ps1` — Pre-start config validation

### New Documentation
- `.env.example` — Complete env var template (committed, no secrets)
- `docs/ENV_SETUP.md` — Multi-device setup guide

### Rollback Steps
1. Revert `api_version: 2` responses: restore `0.0` defaults in `server.py`
2. Revert cookie OAuth: re-add token/session to redirect URL params
3. Revert ownership: remove `owner_id` fields from workflow dicts
4. Revert runtime_state: restore `global` keyword patterns in mode endpoints
