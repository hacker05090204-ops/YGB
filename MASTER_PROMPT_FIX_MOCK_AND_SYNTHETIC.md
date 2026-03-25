# Master Prompt: Fix Mock and Synthetic Usage Across Codebase

Use this document as the single source of truth to fix all mock/simulated/synthetic data and implementations so that production paths use real data, real integrations, or explicit feature flags—while keeping tests and governance checks intact.

---

## 1. Scope and Rules

- **Do not remove** test-only mocks (e.g. `unittest.mock`, `_mock_*` parameters used only in tests). Keep them for testability.
- **Do fix** production/runtime code that:
  - Returns mock data when real data could be obtained (e.g. GPU temp, metrics).
  - Uses hardcoded mock values in reports or observability.
  - Relies on synthetic data in training/reporting instead of real datasets or real APIs.
- **Governance layer**: Many governors are explicitly "mock for governance testing" with C++/native deferred. Either:
  - Replace with real integrations where available, or
  - Document clearly and gate behind an env flag (e.g. `YGB_USE_REAL_G14=1`) so production can opt into real behavior.
- **Preserve** intentional synthesis that is domain logic (e.g. Phase-27 Instruction Synthesis, AMSE Method Synthesis). Do not change those.

---

## 2. Training (`impl_v1/training/`)

### 2.1 `monitoring/gpu_thermal_monitor.py`
- **Current:** `get_gpu_status()` returns `_mock_status(gpu_id)` when CUDA is unavailable or on exception; `_get_temperature()` falls back to `65.0` as "Default mock value".
- **Fix:** When CUDA/nvidia-smi are unavailable, return a distinct "unavailable" or "unknown" state (e.g. `state=ThermalState.UNKNOWN` or a new enum value) and do not report fake temperatures. Callers should treat unknown as "cannot make thermal decision" rather than "65°C". Keep `_mock_status` only for unit tests (e.g. call it only when a test flag or test-only path is set).

### 2.2 `safety/representation_integrity.py`
- **Current:** On `ImportError` (e.g. torch missing), returns `_mock_profile(checkpoint_id)` with fixed layer profiles.
- **Fix:** On missing torch, return an explicit "profile unavailable" result (e.g. optional `None` or a `ProfileUnavailable` variant) instead of a fake profile. Callers must not use fake profiles for drift decisions. Keep `_mock_profile` for tests only.

### 2.3 `safety/stress_lock.py`
- **Current:** `run_gpu_starvation_test()` uses `utilization = 75.0  # Mock` when "Would use nvidia-smi in production".
- **Fix:** Call nvidia-smi (or PyTorch CUDA utilization if available) to get real GPU utilization. If unavailable, fail the test or return "unavailable" rather than a fixed 75%.

### 2.4 `safety/adversarial_drift.py`
- **Current:** Docstring says "Generate synthetic adversarial payloads" for robustness testing.
- **Decision:** This is intentional test payload generation. No change required unless product decides robustness tests must use only recorded real payloads.

### 2.5 `impl_v1/phase49/runtime/auto_trainer.py`
- **Current:** `_generate_session_report()` uses `samples_processed=epochs_trained * 100  # Mock samples`.
- **Fix:** Compute real sample count from the dataloader (e.g. `epochs_trained * batch_size * batches_per_epoch` or track actual samples in the session). Pass the real count into `generate_training_report()`.

### 2.6 `impl_v1/phase49/runtime/training_reports.py`
- **Current:** `confidence_calibration=0.85  # Mock calibration`.
- **Fix:** Either compute calibration from real validation metrics (e.g. from last checkpoint eval) or pass through from caller; if unavailable, use a sentinel (e.g. `None` or "unavailable") and document in report schema.

---

## 3. Governors (`impl_v1/phase49/governors/`)

For each governor listed below, choose one of:
- **A)** Replace with real API / real C++ integration where possible.
- **B)** Keep Python mock but gate behind env (e.g. `YGB_USE_REAL_<FEATURE>=1`). When unset, document "mock mode" in logs and responses.
- **C)** Leave as mock only if it is test-only (e.g. `_mock_response` used only from tests).

Apply consistently:

| Governor | Current mock/synthetic | Recommended fix |
|----------|------------------------|-----------------|
| **g04_voice_proxy** | Mock implementation; URL build doesn't call API | B: env gate for real voice API; else log "mock". |
| **g06_autonomy_modes** | `MOCK` mode – "Everything is mocked" | Keep MOCK as a valid mode; ensure no production default to MOCK unless configured. |
| **g07_cve_intelligence** | Mock implementation | B or A with real CVE source. |
| **g08_licensing** | Mock implementation; mock valid keys | B: env gate for real license check. |
| **g09_device_trust** | Mock expiry date | Use real expiry from device or config; no hardcoded mock date in prod path. |
| **g14_target_discovery** | `_MOCK_PROGRAMS`; mock implementation | A or B: real discovery (e.g. G14 API) when available; else env-gated mock. |
| **g15_cve_api** | `_mock_response`, `_handle_mock_response` | Keep `_mock_response` for tests only; production path must call real API or return "unavailable". |
| **g16_gmail_alerts** | `_mock_send` | B: when real send is disabled, log "mock send" and do not report as "sent"; or require env for real SMTP. |
| **g18_screen_inspection** | `_mock_findings` | Keep for tests; production path must use real capture or return "no inspection available". |
| **g19_interactive_browser** | `_mock_title`, `_mock_url`, `_mock_text`, `_mock_data` | Test-only params only; production must use C++/native or explicit "unavailable". |
| **g21_auto_update** | `_mock_update`, mock verification, mock path | B: real update check when configured; mock only when explicitly in test or dev mode. |
| **g25_ungoogled_chromium** | Mock version for testing | Production: call real binary for version; mock only in tests. |
| **g26_forensic_evidence** | MOCK capture/render, mock video/metadata | B: real C++ when available; else return "evidence unavailable" instead of fake data. |
| **g29_voice_stt** | Mock noise filtering | B or A: real audio pipeline when available. |
| **g30_parallel_tasks** | Mock task execution, mock GPU detect | Real task execution or "not supported"; real GPU detection or explicit "no GPU". |
| **g32_reasoning_scope_engine** | MOCK rendering | B: real render when C++ available. |
| **g35_ai_accelerator** | `simulate_gpu_training`, `is_mock` | Keep `is_mock` in result; production should prefer real GPU path when available. |
| **g37_gpu_training_backend** | MOCK backend, mock device, mock features/metrics/inference | Prefer g37_pytorch_backend (real PyTorch) when possible; use MOCK only when no GPU and document. |
| **g37_pytorch_backend** | Fallback mock metrics when PyTorch unavailable | When PyTorch missing, return "training unavailable" or empty metrics, not fake improving metrics. |
| **g38_self_trained_model** | Mock uptime/power/idle; deterministic mock inference | Real OS calls for idle/power where possible; inference: use real model when loaded, else return "model not loaded". |
| **g39_environment_fingerprint** | Env fallbacks "mock-gpu", "ungoogled-chromium-mock" | Use real detection when possible; only use mock strings in tests or when explicitly configured. |

---

## 4. API and Native

### 4.1 `api/server.py`
- **Current:** `/api/targets/discover` returns hardcoded `mock_targets` list.
- **Fix:** Call real target discovery (e.g. G14 or configured source). If no source configured, return empty list and a message "Target discovery not configured" instead of fake programs.

### 4.2 `impl_v1/phase49/native/browser_bindings.py`
- **Current:** Full mock (mock PIDs, mock launch).
- **Fix:** B: when real C++ bindings are available, use them; when not, document "browser bindings mock" and do not expose mock PIDs as real process IDs to production callers.

---

## 5. Production and Validation

### 5.1 `impl_v1/production/observability/metrics_exporter.py`
- **Current:** "Collect all metrics (mock values for now)".
- **Fix:** Wire to real metrics (training stats, GPU stats, request counts). If a metric has no source yet, expose it as "unavailable" or omit it instead of a fake number.

### 5.2 `impl_v1/production/validation/burn_test.py`
- **Current:** MOCK COLLECTORS; mock return values.
- **Fix:** Use real collectors for burn test (e.g. real GPU temp, real load). If only for demos, rename to "demo_burn_test" and document.

### 5.3 `impl_v1/phase49/validation/stability_tests.py`
- **Current:** Mock scan, mock values for "framework demonstration".
- **Fix:** Use real scan hook or real stability metrics; or mark as "demo" and exclude from production stability gates.

### 5.4 `impl_v1/production/validation/large_scale_validation.py`
- **Current:** "MOCK SCANNER (realistic behavior)".
- **Fix:** Use real scanner when available; otherwise document and gate so production does not rely on mock results for go/no-go.

---

## 6. Frontend and Config

- **Frontend:** `MOCK` mode in autonomy selector is valid; ensure backend does not default to MOCK for production tenants.
- **Config/docs:** Any code_summary or docs that say "mock" for a feature should align with the above (mock = test/demo or env-gated).

---

## 7. Implementation Order (Suggested)

1. **Training and reports:** Fix `auto_trainer` report sample count, `training_reports` calibration, then GPU thermal monitor and representation_integrity (so training pipeline and reports use real or explicit-unavailable only).
2. **Safety:** Fix stress_lock GPU utilization to real or unavailable.
3. **API:** Replace `mock_targets` in target discovery with real or empty + message.
4. **Governors:** Apply A/B/C per table; start with g14 (target discovery), g15 (CVE), g09 (device trust), then others.
5. **Production/observability:** Real metrics and validation behavior or explicit "unavailable"/demo labeling.

---

## 8. Acceptance Criteria

- No production code path returns fake numbers (temperature, utilization, sample counts, calibration) as if they were real.
- Reports and observability either show real data or clearly "unavailable" / "not configured".
- Target discovery returns real results or empty + message, not hardcoded mock programs.
- Governors that are still mock are either test-only or explicitly gated (env or config) and documented.
- All existing tests that rely on mocks continue to pass; new tests or fixtures only where needed for real paths.

Use this master prompt as the single specification for fixing mock and synthetic usage across the codebase.
