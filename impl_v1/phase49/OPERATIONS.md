# YGB SYSTEM OPERATIONS DOCUMENTATION

## 1. System Architecture

```
┌─────────────────────────────────────────────────────────┐
│                     YGB SYSTEM                          │
├─────────────────────────────────────────────────────────┤
│  GOVERNANCE LAYER (Python)                              │
│  ├── G33 Proof Verification                             │
│  ├── G34 Duplicate Intelligence                         │
│  ├── G35 AI Accelerator                                 │
│  ├── G36 Auto Proof Verifier                           │
│  ├── G37 Autonomous Hunter + PyTorch                   │
│  └── G38 Adaptive Reporting                            │
├─────────────────────────────────────────────────────────┤
│  EXECUTION LAYER (C++ / GPU)                           │
│  ├── PyTorch Neural Network                            │
│  ├── CUDA / CPU Training                               │
│  └── Video/Screenshot Processing                       │
├─────────────────────────────────────────────────────────┤
│  OUTPUT LAYER                                          │
│  ├── report.json (machine-readable)                    │
│  ├── report.md (human-readable)                        │
│  ├── poc_video.webm                                    │
│  └── evidence_bundle.json                              │
└─────────────────────────────────────────────────────────┘
```

---

## 2. Auto-Mode Standard Operating Procedure

### Pipeline Flow
```
Browser Discovery → Candidate Finding → AI Ranking (G35)
→ Auto Proof Verification (G36) → Duplicate Check (G34)
→ Reasoning (G32) → Evidence (G26) → Adaptive Report (G38)
→ FINAL OUTPUT
```

### Quality Gates
- Confidence ≥ 97%
- Duplicate probability < 30%
- Proof signals present
- Evidence verified

### If gates fail:
- Mark as `NEEDS_HUMAN`
- Do NOT finalize

---

## 3. Evidence Chain SOP

1. Capture screenshot before action
2. Execute observation (read-only)
3. Capture screenshot after
4. Record video timeline
5. Generate integrity hash
6. Bundle all evidence

---

## 4. Model Training SOP

### When: IDLE mode only
### Data sources:
- G33 verified bugs
- Rejected findings
- Duplicate findings
- Human corrections

### Process:
1. Check `can_train_without_idle()` → must be False
2. Prepare batch with `prepare_training_batch()`
3. Train with `train_full()`
4. Save checkpoint with `save_model_checkpoint()`

---

## 5. Report Submission Guidelines (MANUAL)

1. Review auto-generated report
2. Verify evidence matches claims
3. Check PoC video timestamps
4. Confirm no duplicates
5. **Human submits manually**

---

## 6. Guard Summary

| Guard | Always Returns |
|-------|----------------|
| `can_auto_submit_bug()` | **False** |
| `can_auto_execute_payloads()` | **False** |
| `can_auto_bypass_governance()` | **False** |
| All 47+ guards | **False** |

---

## 7. System Status

| Metric | Value |
|--------|-------|
| Tests | 4987 passed |
| Governors | 40 |
| Guards | 47+ |
| Auto-Mode | Ready |
| Training | Ready (IDLE) |

# STATUS: STABLE & COMPLETE ✅
