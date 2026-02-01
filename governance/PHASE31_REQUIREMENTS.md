# PHASE-31 REQUIREMENTS

**Phase:** Phase-31 — Runtime Observation & Controlled Execution Evidence Capture  
**Type:** DESIGN-ONLY (NO CODE)  
**Version:** 1.0  
**Date:** 2026-01-25  
**Authority:** Human-Only  

---

## EXECUTIVE SUMMARY

Phase-31 defines the **observation layer** between governance and real execution. This is the boundary where the system's pure policy model meets hostile reality. The requirements below specify what can and cannot be observed, what evidence means, and when to HALT.

---

## FUNCTIONAL REQUIREMENTS

### REQ-01: Observation Attachment Points

The observation layer SHALL attach to the following execution loop states:

| From State | To State | Observation Point |
|------------|----------|-------------------|
| INIT | DISPATCHED | `PRE_DISPATCH` |
| DISPATCHED | AWAITING_RESPONSE | `POST_DISPATCH` |
| AWAITING_RESPONSE | EVALUATED | `PRE_EVALUATE` |
| EVALUATED | DISPATCHED | `POST_EVALUATE` |
| ANY | HALTED | `HALT_ENTRY` |

**Each observation point SHALL:**
- Capture immutable timestamp
- Capture state transition metadata
- NOT modify execution flow
- NOT interpret captured data

---

### REQ-02: Evidence Definition

#### REQ-02.1: What Execution Evidence IS

| Evidence Type | Description | Source |
|---------------|-------------|--------|
| StateTransitionRecord | Observed state change | ExecutionLoopContext |
| ExecutorOutputSnapshot | Raw bytes from executor | Executor (untrusted) |
| TimestampedEvent | Immutable observation time | System clock |
| HashChainEntry | Cryptographic linkage | Prior evidence |
| ResourceMeasurement | Memory/CPU at observation | OS metrics (untrusted) |

#### REQ-02.2: What Execution Evidence IS NOT

| NOT Evidence | Why |
|--------------|-----|
| Executor claims | Untrusted source |
| Success/failure interpretation | Requires human judgment |
| Retry recommendations | Requires governance decision |
| Confidence scores | Already captured in Phase-30 |
| Bug classifications | Requires human analysis |

---

### REQ-03: STOP Conditions

The following conditions SHALL cause immediate HALT **before** execution begins:

| ID | Condition | Default |
|----|-----------|---------|
| STOP-01 | Missing human authorization | HALT |
| STOP-02 | Executor not registered | HALT |
| STOP-03 | Envelope hash mismatch | HALT |
| STOP-04 | Observation context uninitialized | HALT |
| STOP-05 | Evidence chain broken | HALT |
| STOP-06 | Resource limits exceeded | HALT |
| STOP-07 | Timestamp validation failure | HALT |
| STOP-08 | Prior execution not finalized | HALT |
| STOP-09 | Ambiguous execution intent | HALT |
| STOP-10 | Human abort signal received | HALT |

**Default behavior:** If any condition is unknown or ambiguous → **HALT**

---

### REQ-04: Observation Boundaries

#### REQ-04.1: Observation SHALL

| ID | Requirement |
|----|-------------|
| OBS-01 | Capture state transitions passively |
| OBS-02 | Record timestamps at defined points |
| OBS-03 | Hash all captured evidence |
| OBS-04 | Chain evidence entries cryptographically |
| OBS-05 | Store raw executor output without parsing |
| OBS-06 | Preserve all data for human review |

#### REQ-04.2: Observation SHALL NOT

| ID | Prohibition |
|----|-------------|
| OBS-N01 | Modify execution flow |
| OBS-N02 | Interpret executor output |
| OBS-N03 | Make retry decisions |
| OBS-N04 | Truncate or filter evidence |
| OBS-N05 | Grant authority to any component |
| OBS-N06 | Cache interpreted results |
| OBS-N07 | Execute code in observation path |

---

### REQ-05: Evidence Immutability

| Requirement | Enforcement |
|-------------|-------------|
| Evidence records frozen | `@dataclass(frozen=True)` |
| Evidence chain append-only | No modification after creation |
| Timestamps immutable | Captured at observation time |
| Hashes cryptographic | SHA-256 minimum |
| Raw data preserved | Never parsed in evidence layer |

---

### REQ-06: Human Authority Requirements

| Action | Authority |
|--------|-----------|
| Initiate execution | Human ONLY |
| Interpret evidence | Human ONLY |
| Decide retry | Human ONLY |
| Override HALT | Human ONLY |
| Finalize execution | Human ONLY |

**AI systems MAY:**
- Report evidence
- Surface anomalies
- Calculate statistics

**AI systems MAY NOT:**
- Make execution decisions
- Interpret success/failure
- Recommend actions without human trigger

---

## NON-FUNCTIONAL REQUIREMENTS

### REQ-NF01: Performance

- Observation overhead MUST NOT exceed 5% of execution time
- Evidence serialization MUST complete within 100ms
- HALT signal propagation MUST complete within 10ms

### REQ-NF02: Storage

- All evidence retained until human expunges
- Evidence chain MUST be reconstructible from storage
- No evidence garbage collection without human authorization

### REQ-NF03: Audit Trail

- Every observation point MUST be auditable
- Evidence chain MUST be verifiable offline
- Hash chain integrity MUST be testable without execution

---

## TESTING REQUIREMENTS

### Mock vs Real

| Component | Test With |
|-----------|-----------|
| ExecutionLoopContext | REAL (from Phase-29) |
| ExecutorRawResponse | MOCK (never real execution) |
| Timestamps | MOCK (deterministic in tests) |
| Hash computation | REAL (actual SHA-256) |
| State transitions | REAL (from Phase-29) |

### Forbidden Imports Check

Tests MUST explicitly verify absence of:

```python
FORBIDDEN = [
    "os", "subprocess", "socket", "asyncio",
    "playwright", "selenium", "requests", "httpx",
    "phase32", "phase33", "phase34"
]
```

### Coverage Requirement

- **100%** statement coverage
- **100%** branch coverage
- All STOP conditions have explicit tests
- All observation points have explicit tests

---

## ACCEPTANCE CRITERIA

| Criterion | Verification |
|-----------|--------------|
| All 10 STOP conditions implemented | Unit test per condition |
| All 5 observation points defined | Unit test per point |
| Evidence immutability enforced | Mutation tests |
| No forbidden imports | Static analysis + tests |
| Human authority preserved | Design review |
| No execution logic | Code review |
| 100% test coverage | Coverage report |

---

**END OF REQUIREMENTS**
