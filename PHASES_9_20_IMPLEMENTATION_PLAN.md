# Phases 9-20 Implementation & Verification Plan

**Date:** 2026-04-15  
**Status:** EXECUTION IN PROGRESS  
**Phases 0-8:** COMPLETE (per PHASE_STATUS_REPORT.md)

---

## Phase 9: Opportunistic Trainer ✓ ALREADY IMPLEMENTED

**Location:** `impl_v1/phase49/runtime/auto_trainer.py`, `impl_v1/training/automode/automode_controller.py`

**Implementation Status:**
- ✓ Auto-trainer with idle detection exists
- ✓ Idle threshold: 60 seconds
- ✓ Guard system: ALL_GUARDS verification
- ✓ Auto-mode unlock controller with requirements
- ✓ Training trigger logic operational

**Gate Requirements:**
1. Verify auto_trainer imports successfully
2. Verify idle detection works
3. Verify guard system blocks unauthorized training
4. Verify auto-mode unlock logic
5. Test opportunistic training trigger

**Files:**
- `impl_v1/phase49/runtime/auto_trainer.py` (2162 lines)
- `impl_v1/training/automode/automode_controller.py` (180 lines)
- `impl_v1/phase49/governors/g38_self_trained_model.py` (guards)

---

## Phase 10: Production Voice Pipeline ✓ PARTIALLY IMPLEMENTED

**Location:** `native/voice_capture/voice_capture.cpp`, `native/voice_capture/audio_capture_bridge.py`

**Implementation Status:**
- ✓ Native C++ voice capture with WASAPI
- ✓ VAD (Voice Activity Detection) implemented
- ✓ PCM16 @ 16kHz mono (STT-optimal)
- ⚠️ WASAPI capture thread not fully implemented (fail-closed)
- ⚠️ Python bridge exists but needs verification

**Gate Requirements:**
1. Verify voice_capture.cpp compiles
2. Verify VAD logic works
3. Verify Python bridge imports
4. Test audio buffer management
5. Verify fail-closed behavior when WASAPI unavailable

**Files:**
- `native/voice_capture/voice_capture.cpp` (270 lines)
- `native/voice_capture/voice_capture.h`
- `native/voice_capture/audio_capture_bridge.py`

---

## Phase 11: Component Wiring Verification ✓ NEEDS VERIFICATION

**Scope:** Verify all impl_v1/ and backend/ components wire correctly

**Components to Verify:**
1. MoE → Training Controller
2. Auto Trainer → Idle Detector
3. Storage Bridge → HDD Engine
4. Auth Guard → Server
5. Parallel Autograbber → Ingestion
6. Compression Engine → Checkpoints
7. Deep RL Agent → Training Loop

**Gate Requirements:**
1. All imports resolve without circular dependencies
2. No missing module errors
3. All critical paths tested
4. Integration smoke tests pass

---

## Phase 12: Server Startup + .env.benchmark ⚠️ NEEDS FIX

**Issue Identified:** JWT_SECRET loading fails when importing auto_trainer

**Current Error:**
```
RuntimeError: JWT_SECRET must be set before startup and must not use a placeholder value
```

**Root Cause:** 
- `.env.benchmark` has valid JWT_SECRET
- `backend/auth/auth.py` loads at import time
- Environment not loaded before import chain

**Fix Required:**
1. Ensure .env.benchmark loads before any imports
2. Fix import order in auto_trainer.py
3. Add environment validation gate
4. Test server startup with .env.benchmark

**Gate Requirements:**
1. Server starts without errors
2. .env.benchmark values load correctly
3. JWT_SECRET validates
4. Auth system initializes
5. All endpoints respond

---

## Phase 13: Live Server Benchmark ⚠️ BLOCKED BY PHASE 12

**Depends On:** Phase 12 server startup fix

**Benchmark Checks:**
1. Server startup time < 5 seconds
2. Auth endpoints respond < 100ms
3. WebSocket connections stable
4. Training API endpoints functional
5. Storage operations work
6. No memory leaks over 5 minutes

**Gate Requirements:**
1. All benchmark checks pass
2. Performance metrics within targets
3. No errors in logs
4. Resource usage acceptable

---

## Phase 14: impl_v1/ + scripts/ Restoration ✓ ALREADY EXISTS

**Status:** Paths already exist and populated

**Verification Needed:**
1. Confirm all impl_v1/ modules import
2. Confirm all scripts/ utilities work
3. Run test suite for impl_v1/
4. Run test suite for scripts/

**Files to Verify:**
- `impl_v1/` (extensive structure exists)
- `scripts/` (device_manager, colab_setup, etc.)

---

## Phase 15: Governance Hard Blockers ⚠️ NEEDS IMPLEMENTATION

**Current:** Governance uses logging warnings  
**Required:** Convert to hard blockers (raise exceptions)

**Modules to Harden:**
1. `impl_v1/governance/incident_automation.py`
2. `impl_v1/phase49/governors/g27_integrity_chain.py`
3. `impl_v1/phase49/governors/g38_*` (all governors)
4. Auth guards in `backend/auth/auth_guard.py`

**Gate Requirements:**
1. All governance violations raise exceptions
2. No silent failures
3. Audit trail for all blocks
4. Tests verify blocking behavior

---

## Phase 16: Incremental Model Scaling ✓ DESIGN EXISTS

**Current:** 52M params/expert (1.2B total)  
**Target:** 130M params/expert (3B total)  
**Hardware:** Requires 12GB+ VRAM

**Implementation:**
1. Add scaling configuration
2. Implement parameter scaling logic
3. Add VRAM detection
4. Auto-scale based on available memory
5. Test on different GPU tiers

**Gate Requirements:**
1. Scaling logic works
2. Memory estimation accurate
3. Graceful degradation on low VRAM
4. Tests pass on multiple GPU types

---

## Phase 17: HDD-Paged Context Memory ✓ PARTIALLY IMPLEMENTED

**Location:** `native/hdd_engine/hdd_engine.py`

**Current Implementation:**
- ✓ Append-only JSONL storage
- ✓ Binary hash index
- ✓ Atomic writes with fsync
- ⚠️ Context paging not implemented
- ⚠️ Memory-mapped access not implemented

**Required Extensions:**
1. Add context window paging
2. Implement LRU cache for hot contexts
3. Add memory-mapped file access
4. Implement context compression
5. Add context retrieval API

**Gate Requirements:**
1. Context paging works
2. Memory usage stays bounded
3. Retrieval performance acceptable
4. Tests verify correctness

---

## Phase 18: Parallel Expert Coordination ✓ ALREADY IMPLEMENTED

**Location:** `impl_v1/training/distributed/production_training_orchestrator.py`

**Implementation Status:**
- ✓ DDP (Distributed Data Parallel) support
- ✓ Multi-GPU coordination
- ✓ Expert routing and scheduling
- ✓ Checkpoint consensus
- ✓ Weight synchronization

**Verification Needed:**
1. Test multi-GPU training
2. Verify expert coordination
3. Test checkpoint sync
4. Verify weight consensus

**Files:**
- `impl_v1/training/distributed/production_training_orchestrator.py`
- `impl_v1/training/distributed/weight_consensus.py`
- `impl_v1/training/distributed/checkpoint_consensus.py`

---

## Phase 19: Final Full-Suite Test Gate ⚠️ NEEDS EXECUTION

**Test Categories:**
1. Unit tests (backend/, impl_v1/)
2. Integration tests (end-to-end flows)
3. Performance tests (benchmarks)
4. Security tests (auth, guards)
5. Governance tests (hard blockers)

**Gate Requirements:**
1. All unit tests pass
2. All integration tests pass
3. Code coverage > 80%
4. No critical security issues
5. All governance guards verified

**Commands:**
```bash
pytest backend/tests/ -v
pytest impl_v1/ -v --cov=impl_v1
pytest scripts/ -v
python scripts/test_phase0_1_2.py
python scripts/test_phase3.py
python scripts/test_phase4.py
```

---

## Phase 20: Final Self-Analysis & Scorecard ⚠️ NEEDS EXECUTION

**Deliverables:**
1. System health scorecard
2. Performance metrics summary
3. Security audit results
4. Governance compliance report
5. Known issues and limitations
6. Deployment readiness assessment

**Scorecard Metrics:**
- Code quality: violations, coverage
- Performance: latency, throughput
- Security: vulnerabilities, hardening
- Governance: compliance, audit trail
- Reliability: uptime, error rates
- Scalability: resource usage, limits

**Gate Requirements:**
1. All metrics collected
2. Scorecard generated
3. Issues documented
4. Recommendations provided
5. Sign-off criteria met

---

## Execution Order

1. **Phase 9:** Verify opportunistic trainer (VERIFY ONLY)
2. **Phase 10:** Verify voice pipeline (VERIFY + FIX WASAPI)
3. **Phase 11:** Component wiring verification (TEST)
4. **Phase 12:** Fix server startup (FIX + TEST) ← **CRITICAL BLOCKER**
5. **Phase 13:** Live server benchmark (TEST)
6. **Phase 14:** Verify impl_v1/scripts paths (VERIFY)
7. **Phase 15:** Governance hard blockers (IMPLEMENT)
8. **Phase 16:** Model scaling (IMPLEMENT)
9. **Phase 17:** HDD context paging (IMPLEMENT)
10. **Phase 18:** Parallel expert coordination (VERIFY)
11. **Phase 19:** Full test suite (EXECUTE)
12. **Phase 20:** Final scorecard (GENERATE)

---

## Critical Path

**BLOCKER:** Phase 12 must be fixed before Phase 13 can run.

**Fix Strategy:**
1. Move environment loading earlier in import chain
2. Make auth.py lazy-load JWT_SECRET
3. Add environment validation script
4. Test with .env.benchmark

**Success Criteria:**
- All 12 phases complete
- All gates pass
- System production-ready
- Scorecard shows green status

---

**Next Action:** Fix Phase 12 server startup issue
