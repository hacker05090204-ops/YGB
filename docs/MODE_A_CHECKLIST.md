# MODE_A Pre-Launch Checklist

**Date:** ___________
**Operator:** ___________
**Sign-off Required:** YES — Do NOT start MODE_A until ALL items are checked.

---

## 1. Device Identity (Phase 2)
- [ ] `config/device_identity.json` exists on every node
- [ ] Each `device_id` is unique (SHA-256 of hardware-bound key)
- [ ] No two nodes share the same identity file

## 2. Pairing & Certificates (Phase 3-4)
- [ ] All devices are paired via one-time token
- [ ] `reports/pairing_log.json` shows `PAIRING_SUCCESS` for every device
- [ ] No `PAIRING_FAILED` entries from unknown sources
- [ ] Rate limiter active — verify with a test of 6 invalid tokens from same IP

## 3. WireGuard Mesh (Phase 4-5)
- [ ] `wg show` on every node shows active peers
- [ ] All peer allowed-IPs match `config/devices.json`
- [ ] Key rotation state persisted to `config/wg_key_state.json`
- [ ] Firewall rules: only 51820/UDP open

## 4. Cluster Roles (Phase 1)
- [ ] At least 1 AUTHORITY node assigned
- [ ] At least 1 STORAGE node assigned
- [ ] At least 1 WORKER node assigned
- [ ] `config/cluster_role.json` present on each node
- [ ] Run quorum check: all roles satisfied

## 5. HMAC & Secrets (Phase 5)
- [ ] `config/hmac_secret.key` exists and is non-empty
- [ ] `hmac_version = 1` in telemetry payloads
- [ ] `YGB_HMAC_SECRET` environment variable set in CI

## 6. Secure Storage (Phase 7)
- [ ] LUKS (Linux) or BitLocker (Windows) enabled on storage nodes
- [ ] Verify: `curl http://127.0.0.1:PORT` from WORKER → DENIED_LOCALHOST
- [ ] Verify: request from non-mesh IP → DENIED_IP
- [ ] Verify: request with WORKER role → DENIED_ROLE
- [ ] Verify: path traversal `../` → DENIED_PATH

## 7. Registry & Heartbeat (Phase 9)
- [ ] All devices appear in `config/devices.json`
- [ ] `status: "online"` for all active devices
- [ ] Disconnect one device → verify it becomes "offline" within 2 min
- [ ] Revoke test device → verify `is_allowed` returns false
- [ ] `reports/cluster_health.json` shows `quorum: true`

## 8. Training Gate (Phase 8)
- [ ] Run `can_start_training()` with all inputs true → PASS
- [ ] Disable one gate (e.g., unset HMAC) → verify FAIL
- [ ] `reports/training_gate.json` records all gate checks

## 9. Governance
- [ ] `freeze_status = false` in all telemetry payloads
- [ ] Governance lock test: set `freeze_status = true` → training blocked
- [ ] GPU temperature test: confirm 88°C thermal halt works

## 10. Final Smoke Test
- [ ] Start one training epoch on WORKER node
- [ ] Verify telemetry appears in `reports/training_telemetry.json`
- [ ] Validate via `/runtime/status` endpoint → `status: "ok"`
- [ ] Check all logs for clean entries (no errors)
- [ ] Cluster health reports quorum maintained throughout

---

## Sign-off

| Role | Name | Date | Signature |
|------|------|------|-----------|
| Operator | | | |
| Reviewer | | | |

**ONCE ALL ITEMS CHECKED → MODE_A AUTHORIZED**
