# PHASE-18 REQUIREMENTS

**Phase:** Phase-18 - Execution State & Provenance Ledger  
**Status:** REQUIREMENTS DEFINED  
**Date:** 2026-01-25T08:35:00-05:00  

---

## 1. EXECUTION RECORD REQUIREMENTS

### 1.1 Every Execution Has Unique ID

| Field | Type | Requirement |
|-------|------|-------------|
| `execution_id` | str | Unique, immutable |
| `request_id` | str | From Phase-17 request |
| `bug_id` | str | Bug identifier |
| `target_id` | str | Target identifier |
| `created_at` | str | ISO timestamp |
| `current_state` | ExecutionState | Current state |

### 1.2 Execution States

| State | Description |
|-------|-------------|
| REQUESTED | Execution requested, pending permission |
| ALLOWED | Phase-16 approved, ready for attempt |
| ATTEMPTED | Sent to executor, awaiting response |
| FAILED | Executor failed (error/timeout) |
| COMPLETED | Executor succeeded with valid evidence |
| ESCALATED | Requires human review |

---

## 2. EVIDENCE RECORD REQUIREMENTS

### 2.1 Evidence Fields

| Field | Type | Requirement |
|-------|------|-------------|
| `evidence_id` | str | Unique evidence ID |
| `execution_id` | str | Linked execution |
| `evidence_hash` | str | Immutable hash |
| `evidence_status` | EvidenceStatus | Current status |
| `linked_at` | str | ISO timestamp |

### 2.2 Evidence Statuses

| Status | Description |
|--------|-------------|
| MISSING | No evidence linked |
| LINKED | Evidence hash attached |
| INVALID | Evidence validation failed |
| VERIFIED | Evidence verified by backend |

---

## 3. CORE RULES (DENY-BY-DEFAULT)

### 3.1 Evidence Rules

| Condition | Result |
|-----------|--------|
| SUCCESS without evidence_hash | ❌ INVALID |
| evidence_hash is empty | ❌ INVALID |
| evidence_hash already used | ❌ DENIED (replay) |
| evidence_hash not matching | ❌ INVALID |

### 3.2 State Transition Rules

| From | To | Condition |
|------|----|-----------| 
| REQUESTED | ALLOWED | Phase-16 approves |
| REQUESTED | ESCALATED | Human required |
| ALLOWED | ATTEMPTED | Sent to executor |
| ATTEMPTED | FAILED | Error/timeout |
| ATTEMPTED | COMPLETED | Valid evidence |
| ATTEMPTED | ESCALATED | Human required |
| Any | ESCALATED | Manual escalation |

### 3.3 Retry Rules

| Condition | RetryDecision |
|-----------|---------------|
| State = FAILED, attempt < max | ALLOWED |
| State = FAILED, attempt >= max | DENIED |
| State = COMPLETED | DENIED |
| State = ESCALATED | HUMAN_REQUIRED |
| Unknown state | DENIED |

### 3.4 Duplicate Prevention

| Condition | Result |
|-----------|--------|
| Multiple SUCCESS for same request | ❌ DENIED |
| Replayed evidence hash | ❌ DENIED |
| Duplicate execution_id | ❌ DENIED |

---

## 4. FUNCTION REQUIREMENTS

| Function | Input | Output |
|----------|-------|--------|
| `create_execution_record()` | request data | ExecutionRecord |
| `record_attempt()` | execution_id | Updated record |
| `attach_evidence()` | execution_id, hash | EvidenceRecord |
| `validate_evidence_linkage()` | execution_id | bool |
| `decide_retry()` | execution_id | RetryDecision |
| `finalize_execution()` | execution_id, outcome | LedgerEntry |

---

## 5. SECURITY REQUIREMENTS

| Requirement | Enforcement |
|-------------|-------------|
| No subprocess | No subprocess module |
| No os.system | No os module |
| No browser | No playwright/selenium |
| No network | No socket/http |
| Immutable records | frozen=True |

---

**END OF REQUIREMENTS**
