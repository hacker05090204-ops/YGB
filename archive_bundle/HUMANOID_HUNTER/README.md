# HUMANOID_HUNTER

## Browser Executor Adapter & Safety Harness

> **CRITICAL:** This folder contains the INTERFACE for a C/C++ browser executor.
> It does NOT contain browser execution code.
> All execution happens EXTERNAL to this repository.

---

## Purpose

The HUMANOID_HUNTER provides:
- Instruction envelope construction
- Response envelope validation
- Safety enforcement

---

## Executor Authority

The executor:
- ✅ Can EXECUTE browser actions
- ❌ CANNOT DECIDE success/failure
- ❌ CANNOT assign evidence
- ❌ CANNOT bypass governance

---

## Directory Structure

```
HUMANOID_HUNTER/
├── interface/       # Python adapter interface
├── contracts/       # C/C++ contract headers
├── tests/           # Test suite
└── README.md        # This file
```

---

## Phase

**Phase-20** — HUMANOID HUNTER Executor Adapter & Safety Harness

---

🔒 **THIS IS AN INTERFACE LAYER ONLY**
