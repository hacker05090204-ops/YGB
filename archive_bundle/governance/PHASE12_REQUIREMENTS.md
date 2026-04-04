# PHASE-12 REQUIREMENTS

**Phase:** Phase-12 - Evidence Consistency, Replay & Confidence Governance  
**Status:** REQUIREMENTS DEFINED  
**Date:** 2026-01-25T04:00:00-05:00  

---

## 1. OVERVIEW

Phase-12 defines the governance logic for evidence consistency verification, replay readiness assessment, and confidence level assignment. This is a **pure backend** module—NO browser, NO execution.

---

## 2. EVIDENCE CONSISTENCY RULES

### 2.1 Consistency Principles

| Principle | Description |
|-----------|-------------|
| **Multi-source** | Evidence from multiple sources increases consistency |
| **Deterministic** | Same inputs must produce same consistency result |
| **Timestamp-aware** | Evidence recency affects consistency |
| **No guessing** | Unknown state → UNVERIFIED, never inferred |

### 2.2 Consistency Decision Table

| Sources Count | All Match | Any Conflict | → State |
|---------------|-----------|--------------|---------|
| 0 | N/A | N/A | UNVERIFIED |
| 1 | N/A | N/A | RAW |
| 2+ | YES | NO | CONSISTENT |
| 2+ | NO | YES | INCONSISTENT |

---

## 3. MULTI-SOURCE CONFIRMATION LOGIC

### 3.1 Confirmation Rules

| Rule ID | Rule | Effect |
|---------|------|--------|
| `MC-001` | Single source | Cannot confirm, state = RAW |
| `MC-002` | Two matching sources | Confirmed, state = CONSISTENT |
| `MC-003` | Three+ matching sources | Strongly confirmed |
| `MC-004` | Any conflicting source | state = INCONSISTENT |
| `MC-005` | No sources | state = UNVERIFIED |

### 3.2 Source Matching Criteria

| Criterion | Match Requirement |
|-----------|-------------------|
| Finding hash | Exact match required |
| Target ID | Must match exactly |
| Severity claim | Must match or be compatible |
| Evidence type | Must be same category |

---

## 4. REPLAY-READINESS CRITERIA

### 4.1 Replay Requirements

| Requirement | Description |
|-------------|-------------|
| **Determinism** | Same environment → same result |
| **Completeness** | All steps documented |
| **Reproducibility** | Human can follow steps |
| **No external deps** | No uncontrolled external state |

### 4.2 Replay Decision Table

| Steps Complete | All Deterministic | External Deps | → Replayable |
|----------------|-------------------|---------------|--------------|
| NO | Any | Any | NO |
| YES | NO | Any | NO |
| YES | YES | YES | NO |
| YES | YES | NO | YES |

---

## 5. CONFIDENCE LEVELS

### 5.1 Confidence Enum (NOT SEVERITY)

| Level | Meaning | Requirements |
|-------|---------|--------------|
| `LOW` | Evidence exists but uncertain | Single source OR inconsistent |
| `MEDIUM` | Evidence consistent | Multi-source confirmed |
| `HIGH` | Evidence replayable | Consistent + replayable |

### 5.2 Confidence Assignment Rules

| Consistency State | Replayable | → Confidence |
|-------------------|------------|--------------|
| UNVERIFIED | Any | LOW |
| RAW | NO | LOW |
| RAW | YES | MEDIUM |
| INCONSISTENT | Any | LOW |
| CONSISTENT | NO | MEDIUM |
| CONSISTENT | YES | HIGH |
| REPLAYABLE | YES | HIGH |

**CRITICAL:** There is NO "100% confidence" or "CERTAIN" level.

---

## 6. EXPLICIT DENY CONDITIONS

### 6.1 Deny-by-Default Rules

| Condition | Result |
|-----------|--------|
| Unknown evidence state | UNVERIFIED |
| Unknown confidence level | LOW |
| Missing source data | Cannot evaluate |
| Conflicting sources | INCONSISTENT (not averaged) |
| No replay steps | Not replayable |

### 6.2 Human Review Required

| Condition | Reason |
|-----------|--------|
| INCONSISTENT state | Human must resolve conflict |
| HIGH confidence claim | Human must validate |
| Replay assertion | Human must verify steps |

---

## 7. DATA TYPES REQUIRED

| Type | Kind | Frozen |
|------|------|--------|
| `EvidenceState` | Enum | N/A (enum) |
| `ConfidenceLevel` | Enum | N/A (enum) |
| `EvidenceSource` | Dataclass | ✅ `frozen=True` |
| `EvidenceBundle` | Dataclass | ✅ `frozen=True` |
| `ConsistencyResult` | Dataclass | ✅ `frozen=True` |
| `ReplayReadiness` | Dataclass | ✅ `frozen=True` |
| `ConfidenceAssignment` | Dataclass | ✅ `frozen=True` |

---

## 8. FUNCTIONAL REQUIREMENTS

### 8.1 Required Functions

| Function | Input | Output |
|----------|-------|--------|
| `check_consistency()` | evidence_bundle | `ConsistencyResult` |
| `check_replay_readiness()` | evidence_bundle | `ReplayReadiness` |
| `assign_confidence()` | consistency, replay | `ConfidenceAssignment` |
| `evaluate_evidence()` | bundle | Full evaluation result |

### 8.2 Function Constraints

All functions MUST be:
- Pure (no side effects)
- Deterministic (same input → same output)
- Total (handle all possible inputs)

---

## 9. SECURITY REQUIREMENTS

| Requirement | Enforcement |
|-------------|-------------|
| No execution logic | No `exec()`, `eval()`, `subprocess` |
| No network access | No `socket`, `http`, `requests` |
| No filesystem write | No `open(..., 'w')` |
| No async/threading | No `asyncio`, `threading` |
| No scoring inflation | No "100%" or "CERTAIN" levels |

---

**END OF REQUIREMENTS**
