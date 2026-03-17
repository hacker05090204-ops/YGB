# Risk Scan: Pipeline & Operational Issues

**Scan Date:** 2026-03-15  
**Status:** REMEDIATED  

---

## Summary Table

| # | Risk Area | Severity | Status |
|---|-----------|----------|--------|
| 1 | Scan status not wired | HIGH | ✅ FIXED — `set_scan_active()` wired into scanner start/stop endpoints; file-backed persistence added |
| 2 | Target discovery mock data | MEDIUM | ✅ ALREADY FIXED — `get_all_targets()` reads from real SQLite DB |
| 3 | Session report mock sample count | MEDIUM | ✅ ALREADY FIXED — uses `_real_samples_processed` from ingestion |
| 4 | Silent failure risks (`except: pass`) | MEDIUM | ✅ FIXED — all bare `except: pass` blocks now log with `logger.warning`/`logger.debug` |
| 5 | Database null handling | LOW | ✅ FIXED — defense-in-depth `or []` guard added in `discover_targets` |
| 6 | Legacy/deprecated code | LOW | ✅ FIXED — `abort_training_legacy()` deprecated with `warnings.warn()`, redirects to `abort_training()` |
| 7 | Optional dependency surfacing | MEDIUM | ✅ FIXED — `get_status()` now returns `dependencies` dict (pytorch/cuda/safetensors/amp/numpy) |
| 8 | BROKEN_CHAIN / EVIDENCE_CHAIN_BROKEN | HIGH | ✅ ALREADY ENFORCED — both defined and tested with HALT behavior |
| 9 | Idle detector placeholder comment | LOW | ✅ FIXED — replaced with "file-backed with in-memory fast-path" section |
| 10 | Scan duration placeholder | LOW | ✅ FIXED — `stop_target_session` now computes real duration from timestamps |

---

## Detailed Findings & Fixes

### 1. Scan Status Not Wired (FIXED)

**Problem:** `is_scan_active()` / `set_scan_active()` in `idle_detector.py` used a plain in-memory global
that no real scanner ever called. Training could run during a scan.

**Fix:**
- `idle_detector.py`: Added file-backed persistence (`data/scan_state.json`) with in-memory cache
- `server.py`: Wired `set_scan_active(True)` into `start_hunter`, `start_bounty`, `start_target_session`
- `server.py`: Wired `set_scan_active(False)` into `stop_target_session` (only when no sessions remain active)

### 2. Target Discovery (ALREADY FIXED)

**Finding:** `/api/targets/discover` calls `get_all_targets()` which queries real SQLite DB.
No mock data in production path. Added `or []` guard for defense-in-depth.

### 3. Session Report (ALREADY FIXED)

**Finding:** `_generate_session_report()` uses `getattr(self, '_real_samples_processed', 0)` —
the real ingestion count, not `epochs_trained * 100`.

### 4. Silent Failure Risks (FIXED)

**Problem:** Multiple `except Exception: pass` blocks could silently swallow errors.

**Fixes applied:**
- `server.py` L427: CVE scheduler shutdown → `logger.warning("[SHUTDOWN] CVE scheduler stop failed")`
- `server.py` L5829: Device alerting → `logger.warning("Device tracking/alerting failed")`
- `voice_gateway.py` L155, L219: Metrics recording → `logger.debug("Metrics recording unavailable")`
- `voice_routes.py` L151: Metrics recording → `logger.debug("Metrics recording unavailable")`

### 5. Database Null Handling (FIXED)

**Finding:** `_fetch_all` already returns `[]` and `_fetch_one` returns `None`. Added `or []` 
guard in `discover_targets` endpoint for defense-in-depth.

### 6. Legacy Code (FIXED)

**Problem:** `abort_training_legacy()` existed alongside `abort_training()`.

**Fix:** Added `warnings.warn(DeprecationWarning)` and redirected to `abort_training()`.
No callers need to change — the method still works but emits a deprecation warning.

### 7. Optional Dependency Surfacing (FIXED)

**Problem:** When PyTorch/numpy/psutil missing, `get_status()` returned zeros implying success.

**Fix:** Added `"dependencies"` dict to `get_status()` return:
```json
{
  "dependencies": {
    "pytorch": "AVAILABLE|UNAVAILABLE",
    "pytorch_backend": "AVAILABLE|UNAVAILABLE",
    "safetensors": "AVAILABLE|UNAVAILABLE",
    "cuda": "AVAILABLE|UNAVAILABLE",
    "amp": "AVAILABLE|UNAVAILABLE",
    "numpy": "AVAILABLE"
  }
}
```

### 8. BROKEN_CHAIN / EVIDENCE_CHAIN_BROKEN (ALREADY ENFORCED)

Both are defined as enum values and tested:
- `InvariantViolation.BROKEN_CHAIN` in `phase21_types.py` — tested in `test_phase21_engine.py`
- `StopCondition.EVIDENCE_CHAIN_BROKEN` in `phase31_types.py` — tested in `test_stop_conditions.py`

### 9. Not Implemented / Deferred Features

The following are documented as not yet implemented and are outside the scope of this remediation:
- CVE API (g15), SMTP/Gmail alerts (g16), bounty rules NR-001/002/003
- Screen inspection (g18), video/render (g26, g32)
- Native browser bindings, jurisdiction signatures, supply-chain lock

These should be addressed in dedicated implementation phases.

---

## Files Modified

| File | Changes |
|------|---------|
| `impl_v1/phase49/runtime/idle_detector.py` | File-backed scan state, removed placeholder comment |
| `impl_v1/phase49/runtime/auto_trainer.py` | Deprecated legacy abort, added dependencies to get_status() |
| `api/server.py` | Wired scan_active, added logging, null guard, real duration calc |
| `api/voice_gateway.py` | Added debug logging to metrics fallbacks |
| `api/voice_routes.py` | Added debug logging to metrics fallback |
