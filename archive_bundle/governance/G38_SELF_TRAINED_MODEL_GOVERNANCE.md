# G38 GOVERNANCE: Large Self-Trained Intelligence Model

**Status:** ACTIVE  
**Phase:** 49  
**Document Type:** Governor Governance  
**Date:** 2026-02-02  
**Authority:** Human-Only

---

## Purpose

G38 implements Option-A: Large Self-Trained Intelligence Model running locally with:
- ZERO authority
- ZERO false positives
- ZERO silent fallbacks
- ZERO dependency on external AI during normal operation

---

## Model Design

### Architecture
- **Type:** Large encoder-based model (NOT chat/LLM)
- **Tokenizer:** Script-aware, Unicode-safe
- **Multi-Head Outputs:**
  - `real_probability` — P(bug is real)
  - `duplicate_probability` — P(bug is duplicate)
  - `noise_probability` — P(bug is noise/false positive)
  - `report_style_id` — Recommended report style

### Training Data Sources
1. G33 verified REAL bugs
2. G36 auto-verified REAL bugs
3. Rejected findings
4. Duplicate clusters (G34)
5. Human corrections
6. Accepted platform reports (structure only)

---

## Operating System Compatibility

G38 supports both **Windows** and **Linux** with identical behavior.

### OS Detection
```python
import platform
def detect_os() -> str:
    return platform.system().lower()
```

### Backend Adapters
| Platform | Backend Class |
|----------|---------------|
| Linux | `LinuxGPUBackend` |
| Windows | `WindowsGPUBackend` |

Both backends expose **IDENTICAL interfaces**.

---

## Idle Training Rules

Training starts **ONLY** when ALL conditions are met:
1. ✅ System idle ≥ 60 seconds
2. ✅ No active scan
3. ✅ No human interaction
4. ✅ Power plugged in
5. ✅ GPU available (CPU fallback allowed)

These rules apply **equally** on Windows and Linux.

---

## External AI Failover Rules

### STATUS: FAILOVER-ONLY

External AI is used **ONLY** when:
- ❌ Local model fails integrity check
- ❌ Checkpoint corruption detected
- ❌ Training/inference throws unrecoverable error
- ❌ Model enters REPAIR MODE

### Failover Behavior
- Used **temporarily**
- Used **read-only**
- Used **ONLY** to recover/bootstrap
- **Automatically disabled** once local model recovers

### Absolute Prohibitions
- ❌ NEVER primary
- ❌ NEVER parallel
- ❌ NEVER preferred
- ❌ NEVER silent
- ❌ NEVER cloud training
- ❌ NEVER telemetry
- ❌ NEVER continuous usage

Every failover MUST be:
- ✅ Logged
- ✅ Visible in dashboard
- ✅ In explicit "REPAIR MODE" state

---

## AI Limitations

### AI CAN:
- Rank findings
- Suggest confidence
- Suggest report phrasing
- Reduce noise
- Learn report structure patterns

### AI CANNOT:
- ❌ Verify bugs (G33/G36 only)
- ❌ Approve bugs
- ❌ Submit bugs
- ❌ Execute payloads
- ❌ Override governance
- ❌ Change scope
- ❌ Mask failures

---

## Required Guards (ALL Return False)

| Guard | Status | Purpose |
|-------|--------|---------|
| `can_ai_execute()` | ✅ FALSE | AI cannot execute |
| `can_ai_submit()` | ✅ FALSE | AI cannot submit |
| `can_ai_override_governance()` | ✅ FALSE | AI cannot override |
| `can_ai_verify_bug()` | ✅ FALSE | Only G33/G36 |
| `can_ai_expand_scope()` | ✅ FALSE | Human-defined scope |
| `can_ai_train_while_active()` | ✅ FALSE | Idle only |
| `can_ai_use_network()` | ✅ FALSE | Local only |
| `can_ai_leak_data()` | ✅ FALSE | No data leakage |
| `can_ai_enable_failover_without_error()` | ✅ FALSE | Error required |
| `can_ai_hide_external_usage()` | ✅ FALSE | All logged |

---

## AUTO-MODE Integration

```
Scan → Candidate → AI Ranking (G38) → Proof Verification (G36)
    → Duplicate Check (G34) → Evidence (G26) → Reasoning (G32)
    → Adaptive Report (G38) → FINAL REPORT (NO HUMAN)
```

### Accuracy Targets
- ≥ 97% precision
- False positives → ~0
- Duplicates → ~0
- Hallucination → NONE

---

## Files

| File | Purpose |
|------|---------|
| `g38_adaptive_reporting.py` | Report pattern rotation |
| `g38_self_trained_model.py` | Core model + idle training |
| `g38_external_failover.py` | Failover governance |

---

## Testing

- **Test Count:** 114 new tests
- **Total Suite:** 5139 tests (exceeds 4986 requirement)
- **Coverage:** 100% for G38 modules

---

## Document Control

| Version | Date | Author | Change |
|---------|------|--------|--------|
| 1.0 | 2026-02-02 | System | Initial G38 governance |

---

**END OF G38 GOVERNANCE**
