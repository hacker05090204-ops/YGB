# Remediation Plan — Priority Order

## Execution Order (by blast radius)

### Phase 1: Security + Data Integrity (Critical/High)
1. Remove `.env_secrets.txt` from git — prevents credential exposure
2. Vault unlock bypass — enforces ADMIN auth on most privileged operation
3. OAuth token leakage — moves secrets from URL to cookies
4. Video path traversal — sanitizes attacker-controlled filenames
5. WS session revocation — closes auth parity gap
6. IDOR ownership — blocks cross-user resource access
7. Startup hardening — secure defaults, opt-in LAN

### Phase 2: Stability + Accuracy (High/Medium)
8. Typed exceptions — structured error chain replaces `except Exception: pass`
9. Synthetic defaults — null/degraded semantics replace fabricated values
10. Concurrency guards — thread-safe state for 5 global variables
11. Transaction safety — explicit BEGIN/COMMIT/ROLLBACK for DB writes

### Phase 3: Observability + Configuration (Medium)
12. Structured logging — JSON format with secret redaction
13. Readiness probe — `/readyz` for availability monitoring
14. Env validation — preflight checks on startup
15. Cross-device onboarding — `.env.example` + bootstrap script

### Phase 4: Deferred (Low)
16. In-memory workflow persistence (needs Redis for multi-node)
17. Remaining 70+ `except Exception` blocks (phased migration)
18. HTTP connection pooling optimization

## Rationale
- Security first: credential exposure and auth bypass have highest blast radius
- Data integrity second: concurrent state corruption can cause data loss
- Observability last: monitoring fails gracefully without impacting users
