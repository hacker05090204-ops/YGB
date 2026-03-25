# Risk Scan: Pipeline, Integration & Operational Risks

Read-only scan of the codebase for risks such as **pipelines not working**, **missing integrations**, **silent failures**, **placeholders**, and **deferred implementations**. No code was changed.

---

## 1. Pipeline & flow risks

### 1.1 Scan status not wired (idle / training pipeline)

| Location | Risk | Impact |
|----------|------|--------|
| **impl_v1/phase49/runtime/idle_detector.py** | `# SCAN STATUS (placeholder - to be integrated)`. `is_scan_active()` / `set_scan_active()` use a **global `_scan_active = False`** that is never set by a real scanner. | Training and auto-trigger logic rely on “no scan active”; if the real scanner never calls `set_scan_active(True)`, the pipeline can train **during** a scan or never know a scan is running. Pipeline is effectively **not integrated** with scanner. |

**Recommendation:** Have the real scan runner (e.g. phase_runner or scanner entrypoint) call `set_scan_active(True)` at start and `set_scan_active(False)` at end so idle/training sees real scan state.

---

### 1.2 Target discovery pipeline returns mock only

| Location | Risk | Impact |
|----------|------|--------|
| **api/server.py** | `/api/targets/discover` returns hardcoded `mock_targets`; no call to G14 or real discovery. | Full “discover targets” pipeline is **not working** with real data; UI and downstream flows see only fake programs. |

See also **MASTER_PROMPT_FIX_MOCK_AND_SYNTHETIC.md** for fix.

---

### 1.3 Real data pipeline vs reporting

| Location | Risk | Impact |
|----------|------|--------|
| **impl_v1/phase49/runtime/auto_trainer.py** | `_generate_session_report()` uses `samples_processed=epochs_trained * 100  # Mock samples`. | Training **pipeline** uses real data (after prior fix), but **reporting pipeline** still emits a fake sample count; dashboards/audit see wrong numbers. |

---

### 1.4 Workflow / state machine usage

- **python/phase05_workflow/** and **impl_v1/phase39**, **phase37** define workflow states and decision flows. No evidence of **broken** state transitions in this scan; risk is only if callers skip states or never transition (would need call-site audit).

---

## 2. “Not implemented” / deferred (pipeline or feature broken)

| Location | What’s not implemented | Pipeline/feature risk |
|----------|------------------------|------------------------|
| **impl_v1/phase49/governors/g15_cve_api.py** | “API call not implemented in governance layer - use mock for testing”. No HTTP request to NVD. | **CVE lookup pipeline** does not work in production; all real CVE checks fail or use mock. |
| **impl_v1/phase49/governors/g16_gmail_alerts.py** | “SMTP not implemented in governance layer”. `_mock_send` and no real smtplib. | **Alert pipeline** (email) does not send; alerts are not delivered. |
| **python/phase09_bounty/bounty_engine.py** | NR-001, NR-002, NR-003 explicitly “not implemented” (scope ambiguity, novel vuln type, partial duplicate). | **Bounty review pipeline** cannot auto-decide those cases; may always require human or use fallback. |
| **impl_v1/phase49/governors/g18_screen_inspection.py** | “This is a Python stub - actual screen capture would be done by C++ native code.” | **Screen inspection pipeline** is stub-only; no real capture. |
| **impl_v1/phase49/governors/g32_reasoning_scope_engine.py** | “Reasoning engine cannot render video - deferred to C++”. “MOCK IMPLEMENTATION: Real rendering deferred to C++.” | **Video/render pipeline** does not work in Python; depends on C++ for real output. |
| **impl_v1/phase49/governors/g26_forensic_evidence.py** | “MOCK FOR TESTING, REAL C++ INTEGRATION LATER”. “Actual video rendering is deferred to C++ backend.” | **Forensic evidence pipeline** (capture/render) is mock until C++ wired. |
| **impl_v1/phase49/native/browser_bindings.py** | “Real implementation would load shared library via ctypes”. “Would call C++ via ctypes”. | **Browser launch/control pipeline** is mock; no real process management. |
| **impl_v1/phase46/mutex_contracts.py** | “Global lock registry (simulated - in real impl would be persistent)”. | **Lock pipeline** is process-local; multi-process or distributed flows can have **races** or inconsistent state. |
| **impl_v1/phase37/capability_validator.py** | “In-memory set for replay detection (would be persistent in real system)”. | **Replay detection** is lost on restart; pipeline can allow replayed requests after restart. |
| **HUMANOID_HUNTER/intent/intent_engine.py** | “In real implementation, this would be persisted”. | Intent state not persisted; **intent pipeline** across restarts may be broken or inconsistent. |
| **impl_v1/production/legal/jurisdiction_check.py** | “Simplified signature check (would use GPG/RSA in production)”. | **Legal/signature pipeline** is weak; not production-grade. |
| **impl_v1/phase49/ci/supply_chain_lock.py** | “This would use pip download + hashdist in production”. | **Supply chain verification pipeline** may not be fully implemented. |
| **impl_v1/phase49/ci/fuzz_testing.py** | “executions=0  # Would be parsed from output”. | **Fuzz metrics pipeline** may not be wired to real execution count. |
| **impl_v1/aviation/no_silent_failure.py** | “Would integrate with alert_router in production”. | **Alert pipeline** for no-silent-failure may not be connected to real alerting. |
| **impl_v1/governance/incident_automation.py** | “Get placeholder scan metrics.” | **Incident/scan metrics pipeline** uses placeholders; dashboards/automation see fake data. |

---

## 3. Placeholder / “to be integrated”

| Location | Detail |
|----------|--------|
| **impl_v1/phase49/runtime/idle_detector.py** | “SCAN STATUS (placeholder - to be integrated)” – see §1.1. |
| **impl_v1/governance/incident_automation.py** | “Get placeholder scan metrics.” |
| **impl_v1/phase31/tests/test_phase31_engine.py** | `self_hash="placeholder"` in test – test-only; no prod risk. |

---

## 4. Silent failure risks (`except` + `pass` or weak fallback)

These can hide failures and make pipelines **appear** to work while they do not.

| Location | What’s swallowed / fallback | Risk |
|----------|----------------------------|------|
| **impl_v1/phase49/runtime/auto_trainer.py** | `except ImportError: pass` (around line 464). | Import failure in a code path is ignored; that path may never run and no one is notified. |
| **impl_v1/phase49/runtime/idle_detector.py** | `except (ImportError, AttributeError, OSError): pass` in Linux/Windows idle detection. | Idle time can fall back to default without logging; training trigger may use wrong “idle” state. |
| **impl_v1/phase49/runtime/idle_detector.py** | `except (subprocess.SubprocessError, ValueError, FileNotFoundError): pass` for xprintidle. | Idle detection fails silently; pipeline continues with no idle data. |
| **impl_v1/training/monitoring/gpu_thermal_monitor.py** | `except Exception: return self._mock_status(gpu_id)`. | Any GPU/thermal error returns **mock** status; pipeline thinks GPU is fine. |
| **impl_v1/training/safety/representation_integrity.py** | `except ImportError: return self._mock_profile(...)`. | Missing torch yields **mock** profile; drift/quality pipeline can use fake data. |
| **impl_v1/training/safety/stress_lock.py** | `except ImportError: utilization = 75.0; passed = True`. | No GPU → fake 75% utilization and test “passed”; **stress pipeline** reports wrong result. |
| **impl_v1/production/validation/burn_test.py** | `except ImportError: return 256.0, 0.1`. | Missing dependency → fixed mock values; **burn-test pipeline** is not real. |
| **api/server.py** | Multiple `except: pass` (e.g. around 228, 245, 1315, 1413, 1422). | Request or lifecycle errors can be swallowed; **API pipeline** may fail silently. |
| **impl_v1/phase50/monitoring/dependency_monitor.py** | `except: pass` (66, 97). | Dependency check failures not surfaced; **monitoring pipeline** can miss broken deps. |
| **impl_v1/phase49/runtime/runtime_attestation.py** | Multiple `except ImportError` with fallback checks. | Attestation pipeline reports “unavailable” for some checks; ensure callers handle “unavailable” and do not assume success. |
| **impl_v1/enterprise/training_controller.py** | `except: pass` (87). | Training controller can swallow errors; **enterprise training pipeline** may be inconsistent. |
| **impl_v1/aviation/decision_trace.py** | `except: pass` (70). | Trace append can fail silently; **audit/chain pipeline** may have gaps. |
| **impl_v1/training/safety/final_gate.py** | `except: pass` (68). | Final gate can ignore exceptions; **safety pipeline** may not block when it should. |
| **impl_v1/governance/human_override.py** | `except: pass` (65, 227). | Override logic can hide errors; **governance pipeline** may be inconsistent. |

**Recommendation:** Replace bare `except: pass` with at least logging and, where appropriate, re-raise or return an explicit error/unavailable result so pipelines do not silently continue with wrong state.

---

## 5. Database / storage (pipelines that depend on persistence)

| Location | Risk | Impact |
|----------|------|--------|
| **api/database.py** | `_load()` returns `None` when file missing; `_load_all()` returns `[]` when table dir missing. | By design for file-based DB; **risk** is if API or callers assume “always a record” and do not handle `None`/empty. Can cause 500s or broken **user/target/session pipelines** if not checked. |
| **api/database.py** | `close_pool()` is no-op. | Fine for file DB; no pipeline break. |

**Recommendation:** Ensure every API path that uses `database._load` / `_load_all` handles `None` and `[]` and returns 404 or empty list with correct HTTP status.

---

## 6. Legacy / deprecated (wrong path or obsolete behavior)

| Location | Detail | Risk |
|----------|--------|-------|
| **impl_v1/phase49/runtime/auto_trainer.py** | `abort_training_legacy()` – “Legacy abort - use abort_training() instead.” | Callers still using `abort_training_legacy` may be on a **deprecated path**; confirm no critical pipeline relies only on legacy. |
| **impl_v1/phase49/governors/g24_system_evolution.py** | `DEPRECATED` Python versions; “Target version … is DEPRECATED - requires human approval”. | Pipelines that depend on deprecated versions should require human approval or block; ensure this is enforced. |
| **impl_v1/phase42/intel_types.py** | `TechAge.LEGACY` (10+ years). | Domain enum; pipeline risk only if legacy targets are treated as “skip” or “low priority” by mistake. |

---

## 7. Broken chain / evidence chain (integrity pipelines)

| Location | Detail | Risk |
|----------|--------|------|
| **impl_v1/phase21/** | `InvariantViolation.BROKEN_CHAIN`; “Enforced + no prior → BROKEN_CHAIN”. | Correct handling of broken chain; **risk** is if any caller ignores the violation and continues (would break **invariant pipeline**). |
| **impl_v1/phase49/governors/g27_integrity_chain.py** | `ChainStatus.BROKEN`; tampered or wrong hash sets BROKEN. | Same as above; callers must not proceed on BROKEN. |
| **impl_v1/aviation/decision_trace.py** | “Chain broken at {trace_file.name}”. | Trace pipeline correctly detects break; ensure **all** consumers stop or escalate. |
| **impl_v1/production/legal/scope_enforcement_proof.py** | “Record … Chain broken”. | Legal/proof pipeline should not accept broken chain; verify enforcement. |
| **HUMANOID_HUNTER/observation/** | `StopCondition.EVIDENCE_CHAIN_BROKEN`. | Observation pipeline halts on broken chain; ensure no path bypasses this. |

No code in this scan showed callers **ignoring** BROKEN status; recommend a single audit of “if status == BROKEN / EVIDENCE_CHAIN_BROKEN: do we always stop or escalate?”

---

## 8. Import / optional dependency (pipeline only runs when deps present)

| Location | Behavior when import fails | Pipeline risk |
|----------|----------------------------|----------------|
| **impl_v1/phase49/governors/g37_pytorch_backend.py** | `PYTORCH_AVAILABLE = False`; later code returns mock metrics or “unavailable”. | **Training pipeline** falls back to mock or no training; document and ensure UI/API show “unavailable” not “success”. |
| **impl_v1/phase49/runtime/auto_trainer.py** | `TORCH_AVAILABLE = False` → GPU init/training paths skip or fail. | Same as above; pipeline does not “work” on CPU-only without PyTorch unless explicitly designed for it. |
| **impl_v1/phase49/training/deterministic_training.py** | `TORCH_AVAILABLE`, `NUMPY_AVAILABLE` false. | Deterministic training pipeline is disabled; no silent wrong result if callers check flags. |
| **impl_v1/phase49/runtime/stability_tests.py** | Fallbacks when psutil or `/proc` missing (e.g. return 0.0). | **Stability pipeline** may report 0.0 instead of real metrics; callers should treat 0 as “unknown” on unsupported platforms. |

---

## 9. Summary: “Pipeline not working” and “many more” risks

| Category | Count (approx) | Severity (if unfixed) |
|-----------|----------------|------------------------|
| Scan status / idle not integrated | 1 | High – training can run during scan or never see scan. |
| Target discovery mock only | 1 | High – discovery pipeline is fake. |
| Not implemented (CVE, SMTP, bounty rules, screen, render, browser, etc.) | 14+ | High–medium – each listed pipeline is partial or mock. |
| Placeholder / to be integrated | 2 | Medium – metrics and scan status. |
| Silent failure (except pass / mock fallback) | 15+ | Medium – pipelines can appear to work with wrong or no data. |
| Database None/[] not handled | 1 (caller responsibility) | Medium – can cause 500 or wrong responses. |
| Legacy/deprecated usage | 2 | Low–medium – ensure no critical path depends only on legacy. |
| Broken chain handling | 0 (callers must not ignore) | Low if all callers enforce; medium if any ignore. |
| Import/optional deps | 4 | Documented; risk is UI/API claiming success when pipeline is unavailable. |

---

## 10. Suggested next steps (read-only; no code change)

1. **Wire scan status:** Have the real scanner (or phase_runner) call `set_scan_active(True/False)` so idle/training pipeline sees real scan state.  
2. **Replace or gate mocks:** Use **MASTER_PROMPT_FIX_MOCK_AND_SYNTHETIC.md** for target discovery, CVE, SMTP, and other mock/deferred pieces.  
3. **Reduce silent failures:** Replace `except: pass` and “return mock on any error” with logging + explicit “unavailable” or error result so pipelines do not silently use wrong data.  
4. **API/database:** Audit all API routes that use `database._load` / `_load_all` and ensure they handle `None` and `[]` and return correct HTTP status.  
5. **Single audit:** For every “not implemented” or “deferred to C++” governor, either implement, env-gate, or document “pipeline unavailable” in API/UI so operators know what is not working.

This document is a **read-only risk scan**; apply fixes in separate changes following the above and the master prompt.
