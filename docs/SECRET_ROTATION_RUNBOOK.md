# Secret Rotation Runbook — YGB

## Context

Historical `.env` and `.env.connected` files were committed to git and have since
been staged for deletion from the tracked index. However, **secrets remain in git
history** and must be treated as compromised.

> [!CAUTION]
> Do NOT rewrite git history unless explicitly authorized by the repository owner.
> Until history is cleaned, assume all secrets listed below are **compromised**.

## Secrets Requiring Rotation

| Secret | Source File(s) | Purpose |
|---|---|---|
| `JWT_SECRET` | `.env`, `.env.connected` | JWT token signing for auth |
| `YGB_HMAC_SECRET` | `.env`, `.env.connected` | HMAC telemetry integrity |
| `YGB_VIDEO_JWT_SECRET` | `.env`, `.env.connected` | Video streamer token signing |
| `SMTP_PASS` / `SMTP_PASSWORD` | `.env.connected` | SMTP email delivery |
| `GITHUB_CLIENT_SECRET` | `.env.connected` | GitHub OAuth app secret |

## Rotation Timeline

### Phase 1 — Immediate (within 1 hour)

1. **Revoke GitHub OAuth App Secret**
   - Go to GitHub → Settings → Developer settings → OAuth Apps → YGB
   - Regenerate the client secret
   - Update `.env` locally with the new value

2. **Rotate JWT secrets**
   ```bash
   # Generate new secrets (64 hex chars each)
   python -c "import secrets; print(secrets.token_hex(32))"
   ```
   Update in `.env`:
   - `JWT_SECRET=<new_value>`
   - `YGB_HMAC_SECRET=<new_value>`
   - `YGB_VIDEO_JWT_SECRET=<new_value>`

3. **Rotate SMTP password**
   - Log into your email provider's admin panel
   - Generate a new app-specific password
   - Update `SMTP_PASS` in `.env`

### Phase 2 — Invalidate (within 2 hours)

4. **Invalidate all active sessions**
   - Restart the backend server — all in-memory sessions will be cleared
   - Any JWTs signed with the old `JWT_SECRET` will fail validation automatically

5. **Invalidate video tokens**
   - Restart the video streamer — old `YGB_VIDEO_JWT_SECRET` tokens will fail

### Phase 3 — Redeploy (within 4 hours)

6. **Redeploy services**
   ```bash
   # Stop all services
   # Update .env with new secrets
   # Restart backend
   python -m uvicorn api.server:app --host 127.0.0.1 --port 8000
   # Restart frontend
   npm --prefix frontend run dev
   ```

7. **Verify health**
   ```bash
   curl http://localhost:8000/runtime/status
   curl http://localhost:8011/health
   ```

### Phase 4 — Audit (within 24 hours)

8. **Verify no old secrets in use**
   ```bash
   python scripts/ci_security_scan.py
   ```

9. **Check auth flow**
   ```bash
   pytest backend/tests/test_oauth_regression.py -v
   ```

10. **Document rotation in incident log**
    - Record date, time, operator, and confirmation of successful rotation

## Preventive Measures

- `.env` and `.env.connected` are in `.gitignore` and staged for deletion
- `.env.example` contains **placeholder-only** values
- `backend/config/config_validator.py` rejects placeholder secrets at startup
- `ci_security_scan.py` runs in CI to catch hardcoded secrets

## Optional: Git History Cleanup

If authorized, clean git history with:
```bash
# WARNING: This rewrites history and requires force-push
git filter-branch --force --index-filter \
  'git rm --cached --ignore-unmatch .env .env.connected' \
  --prune-empty --tag-name-filter cat -- --all
git push origin --force --all
```

> [!WARNING]
> Force-pushing rewrites history for all collaborators. Coordinate with the team first.

## Operator Checklist

Use this checklist during an actual rotation event:

- [ ] **1. Revoke** GitHub OAuth App secret (GitHub → Settings → Developer settings)
- [ ] **2. Generate** new JWT_SECRET, YGB_HMAC_SECRET, YGB_VIDEO_JWT_SECRET (`python -c "import secrets; print(secrets.token_hex(32))"`)
- [ ] **3. Rotate** SMTP_PASS via email provider admin panel
- [ ] **4. Update** `.env` with all new values
- [ ] **5. Stop** all running services (backend + frontend + video streamer)
- [ ] **6. Restart** backend: `python -m uvicorn api.server:app --host 127.0.0.1 --port 8000`
- [ ] **7. Restart** frontend: `npm --prefix frontend run dev`
- [ ] **8. Verify** health: `curl http://localhost:8000/runtime/status` → 200
- [ ] **9. Verify** auth: `pytest backend/tests/test_oauth_regression.py -v` → all pass
- [ ] **10. Scan** for leftover secrets: `python scripts/ci_security_scan.py` → PASS
- [ ] **11. Log** rotation in incident log with date, operator, confirmation

### Severity Classification

| Secret | Severity | Impact if Compromised |
|--------|----------|-----------------------|
| `JWT_SECRET` | **CRITICAL** | Full auth bypass — attacker can forge any JWT |
| `GITHUB_CLIENT_SECRET` | **HIGH** | OAuth impersonation — attacker can authenticate as any GitHub user |
| `YGB_VIDEO_JWT_SECRET` | **MEDIUM** | Unauthorized video access — attacker can stream any video |
| `YGB_HMAC_SECRET` | **MEDIUM** | Telemetry tampering — attacker can forge integrity signatures |
| `SMTP_PASS` | **LOW** | Email abuse — attacker can send emails from the service account |

