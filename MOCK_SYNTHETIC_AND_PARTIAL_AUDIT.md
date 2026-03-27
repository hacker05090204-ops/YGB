# Mock, Synthetic, and Partial/Broken Code Audit

**Generated:** 2026-03-16  
**Scope:** All mocks, synthetic data paths, and partial/broken implementations across the codebase.

**Update (2026-03-26):** Some findings below are now partially fixed. In particular,
`g14_target_discovery.py`, `g15_cve_api.py`, `g16_gmail_alerts.py`,
`training_reports.py`, `model_registry.py`, and the frontend demo pages have been moved
away from fake-success behavior toward real integrations or explicit unavailable states.

---

## 1. Mocks

### 1.1 Production/runtime mocks (used in non-test code paths)

| Location | What's mocked | Risk |
|----------|----------------|------|
| **impl_v1/phase49/governors/g14_target_discovery.py** | Historical: `_MOCK_PROGRAMS` public program list | Updated: now requires configured source data and returns empty results when unavailable |
| **impl_v1/phase49/governors/g15_cve_api.py** | Historical: passive API path was not implemented | Updated: now performs real NVD requests and returns explicit `OFFLINE` / `DEGRADED` / `INVALID_KEY` states on failure |
| **impl_v1/phase49/governors/g16_gmail_alerts.py** | Historical: SMTP path returned mock success or pending | Updated: now sends via real SMTP when configured and otherwise fails closed |
| **impl_v1/phase49/governors/g19_interactive_browser.py** | `_mock_title`, `_mock_url`, `_mock_text`, `_mock_data` – used when no C++ native; production can hit these if native unavailable | Browser observation can return test-style data |
| **impl_v1/phase49/governors/g37_gpu_training_backend.py** | `GPUBackend.MOCK`, "Mock GPU (CPU Fallback)", mock feature extraction, mock training metrics, mock inference, mock contrastive similarity/loss | Full GPU path is mock when no CUDA/ROCm |
| **impl_v1/phase49/governors/g35_ai_accelerator.py** | `simulate_gpu_training()` returns `TrainingResult` with `is_mock=True`, mock loss/accuracy/time | Training results are simulated |
| **impl_v1/phase49/governors/g38_self_trained_model.py** | `LinuxGPUBackend` / `WindowsGPUBackend`: `check_idle()` → 120, `check_power()` → True ("Mock - real would read /proc or GetSystemPowerStatus") | Idle/power are hardcoded in production |
| **impl_v1/training/monitoring/gpu_thermal_monitor.py** | `get_gpu_status()` → `_mock_status(gpu_id)` when CUDA unavailable; `_get_temperature()` → 65.0 "Default mock value" | Reports fake GPU temp when no CUDA |
| **impl_v1/training/safety/representation_integrity.py** | On `ImportError` (e.g. torch missing): `compute_profile()` → `_mock_profile(checkpoint_id)` with fixed layer profiles | Drift checks can use fake profiles |
| **impl_v1/training/safety/stress_lock.py** | `run_gpu_starvation_test()`: `utilization = 75.0  # Mock` (and same in branch) | Stress test uses fake GPU utilization |
| **impl_v1/phase49/runtime/auto_trainer.py** | `_generate_session_report()`: `samples_processed=epochs_trained * 100  # Mock samples` | Reports show fake sample counts |
| **impl_v1/phase49/runtime/training_reports.py** | Historical: hardcoded calibration/accuracy placeholders | Updated: missing measurements are now emitted as unavailable instead of fake values |
| **impl_v1/governance/model_registry.py** | Historical: missing files produced fake hashes | Updated: missing model files now raise explicit errors |
| **impl_v1/enterprise/checkpoint_sync.py** | Merge only logs; no real weight averaging ("In production: actual weight averaging of tensors") | Sync is protocol-only, no real merge |
| **api/server.py** | Historical: `/api/targets/discover` returned hardcoded targets | Updated: now uses live target records and honest empty-state behavior |

### 1.2 Test-only mocks (appropriate)

- **impl_v1/phase49/tests/test_g25_ungoogled_chromium.py** – `unittest.mock.patch`, `MagicMock` for binary/path/version (tests only).
- **impl_v1/phase49/tests/test_g15_cve_api.py** – `_mock_response` passed explicitly in tests.
- **impl_v1/phase49/tests/test_idle_detector.py** – Mocks for platform/idle (tests only; docstring: "Mocks are allowed ONLY in tests").
- **impl_v1/phase49/tests/test_g06_autonomy.py** – `AutonomyMode.MOCK` used in tests.
- **impl_v1/phase49/tests/test_crossplatform_determinism.py** – `mock_train_epoch()` for determinism tests.
- **impl_v1/phase49/tests/test_g26_forensic_evidence.py** – Assertions on mock render.
- **impl_v1/phase49/tests/test_g30_parallel_tasks.py** – "Mock returns False" for GPU detect in test.

---

## 2. Synthetic

### 2.1 Training data (synthetic / generated)

| Location | What's synthetic | Note |
|----------|------------------|------|
| **impl_v1/training/data/scaled_dataset.py** | `ScaledDatasetGenerator` – generates 20k+ samples in code (difficulty, noise, labels) | No external dataset; deterministic seed |
| **impl_v1/training/data/real_dataset_loader.py** | Uses `ScaledDatasetGenerator`; "real" = pipeline, not data source | Training data is programmatically generated |

### 2.2 Intentional synthesis (domain logic – keep as-is)

- **Phase-27** – Instruction synthesis (envelope/metadata); frozen.
- **AMSE** – Method synthesis (synthesized methods, human approval); intentional.
- **HUMANOID_HUNTER** – `synthesize_instructions`, instruction envelopes; intentional.
- **impl_v1/training/safety/adversarial_drift.py** – "Generate synthetic adversarial payloads" for robustness testing; intentional.

### 2.3 Anti-synthetic enforcement (no synthetic fallback)

- **impl_v1/phase49/runtime/auto_trainer.py** – Comments: "NO synthetic data", "Real data only", "no synthetic data"; uses `real_dataset_loader` only.
- **impl_v1/training/tests/test_no_synthetic_fallback.py** – Enforces no `random.random()` for training data, use of `real_dataset_loader`, `validate_dataset_integrity`, min 18000 samples.

---

## 3. Partial or broken code

### 3.1 Explicit "not implemented" or degraded production paths

| Location | Issue |
|----------|--------|
| **impl_v1/phase49/governors/g15_cve_api.py** | Production API path returns `DEGRADED` with message "API call not implemented in governance layer - use mock for testing". |
| **impl_v1/phase49/governors/g16_gmail_alerts.py** | Error message: "SMTP not implemented in governance layer". |
| **python/phase09_bounty/bounty_engine.py** | Docstring: NR-001 "not implemented - requires partial matching", NR-002 "not implemented - requires ML", NR-003 "Partial duplicate overlap (not implemented)". |

### 3.2 Abstract / stub bodies (`pass` or minimal)

| Location | What's stubbed |
|----------|----------------|
| **impl_v1/phase49/governors/g38_self_trained_model.py** | `GPUBackendInterface`: `detect_gpu`, `check_idle`, `check_power`, `get_memory_mb` – abstract; `LinuxGPUBackend`/`WindowsGPUBackend` implement with mocks (idle=120, power=True). |
| **impl_v1/phase49/governors/g25_ungoogled_chromium.py** | `pass` in one branch (line 319). |
| **impl_v1/phase49/governors/g24_system_evolution.py** | `pass` in branch (line 301). |
| **impl_v1/aviation/decision_trace.py** | `pass` in exception handler; "Chain broken at ..." in another path. |
| **impl_v1/enterprise/checkpoint_sync.py** | `except Exception: pass` when loading sync history. |
| **impl_v1/training/safety/final_gate.py** | `pass` in branch (line 68). |
| **impl_v1/enterprise/training_controller.py** | `pass` in branch (line 87). |
| **impl_v1/phase50/monitoring/dependency_monitor.py** | `pass` (lines 66, 97). |
| **impl_v1/training/automode/automode_controller.py** | `pass` (line 62). |
| **impl_v1/governance/human_override.py** | `pass` in branches (65, 227). |
| **impl_v1/phase49/runtime/auto_trainer.py** | `pass` in branches (265, 465). |
| **impl_v1/phase49/runtime/idle_detector.py** | Multiple `pass` in unsupported-platform branches. |
| **impl_v1/phase49/runtime/security_monitor.py** | `pass` (line 115). |
| **impl_v1/training/checkpoints/checkpoint_hardening.py** | `pass` in exception (line 63). |
| **impl_v1/governance/model_registry.py** | `pass` in branch (line 59). |
| **api/phase_runner.py** | Multiple `pass` in exception/empty branches. |
| **api/server.py** | `pass` in exception branches. |
| **api/database.py** | `pass` (line 76 – likely stub). |
| **impl_v1/phase49/runtime/runtime_attestation.py** | Multiple `pass` in branches. |

### 3.3 "Broken" or "partial" in names (by design – tests or types)

- **impl_v1/phase21** – `BROKEN_CHAIN` type; tests for "broken chain".
- **impl_v1/phase30** – `ExecutorResponseType.PARTIAL`; "partial returns escalate".
- **impl_v1/phase31** – "broken hash chain" tests.
- **HUMANOID_HUNTER/observation** – "broken evidence chain" tests.
- **impl_v1/production/legal/scope_enforcement_proof.py** – "Chain broken" in validation message.
- **python/phase09_bounty/bounty_engine.py** – "partial matching", "Partial duplicate" in docstring (features not implemented).

These are type/contract names or tests, not necessarily broken production logic.

---

## 4. Summary

| Category | Count (approx) | Action |
|----------|----------------|--------|
| **Production mocks** | 15+ locations | Prefer real integrations or env gates; document mock mode; avoid fake values in observability. |
| **Test-only mocks** | 7+ files | Keep; used only in tests. |
| **Synthetic data** | Training pipeline uses generated data (scaled_dataset); no external dataset. | Optional: add real data source; keep synthesis for tests/adversarial. |
| **Intentional synthesis** | Phase-27, AMSE, instructions, adversarial payloads | No change. |
| **Not implemented / stub** | 3 explicit "not implemented" messages; 20+ `pass` or minimal branches. | Implement or return explicit "unavailable" instead of mock; replace bare `pass` with logging or clear behavior where appropriate. |

**Reference:** `MASTER_PROMPT_FIX_MOCK_AND_SYNTHETIC.md` already specifies fixes for many of these (env gates, real API, "unavailable" instead of mock, etc.). This audit aligns with that and adds partial/broken code locations.
