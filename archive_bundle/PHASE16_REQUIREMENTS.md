# PHASE-16 REQUIREMENTS

**Phase:** Phase-16 - Execution Boundary & Browser Invocation Authority  
**Status:** REQUIREMENTS DEFINED  
**Date:** 2026-01-25T06:15:00-05:00  

---

## 1. OVERVIEW

Phase-16 determines IF browser execution is permitted based on signals from Phase-13 (Handoff) and Phase-15 (Contract). It is a **pure permission layer** that outputs ALLOWED or DENIED.

---

## 2. PRECONDITIONS FOR ALLOWING EXECUTION

### 2.1 Required Signals

| Source | Signal | Required Value |
|--------|--------|----------------|
| Phase-13 | `readiness` | READY_FOR_BROWSER |
| Phase-13 | `can_proceed` | True |
| Phase-13 | `is_blocked` | False |
| Phase-13 | `human_presence` | OPTIONAL (or human present) |
| Phase-15 | `is_valid` | True |
| Phase-15 | `status` | VALID |

### 2.2 All Must Be True

ALL of the above conditions must be TRUE for execution to be ALLOWED.
If ANY condition is FALSE → execution is DENIED.

---

## 3. EXPLICIT DENY CASES

| Condition | Result | Code |
|-----------|--------|------|
| readiness = NOT_READY | DENIED | EX-001 |
| readiness = REVIEW_REQUIRED | DENIED | EX-002 |
| can_proceed = False | DENIED | EX-003 |
| is_blocked = True | DENIED | EX-004 |
| human_presence = REQUIRED but absent | DENIED | EX-005 |
| human_presence = BLOCKING | DENIED | EX-006 |
| contract is_valid = False | DENIED | EX-007 |
| contract status = DENIED | DENIED | EX-008 |
| context is None | DENIED | EX-009 |
| Unknown/invalid signals | DENIED | EX-010 |

---

## 4. HUMAN OVERRIDE RULES

### 4.1 Human Override Allowed

| Condition | Override Allowed |
|-----------|------------------|
| Human explicitly confirms | ✅ Can proceed |
| Human provides override token | ✅ Can proceed |

### 4.2 Human Override NOT Allowed

| Condition | Override |
|-----------|----------|
| Contract validation failed | ❌ NO |
| Phase-13 is_blocked = True | ❌ NO |
| readiness = NOT_READY | ❌ NO |

### 4.3 Override Rule

> **RULE:** Human override can bypass REVIEW_REQUIRED but NEVER:
> - Contract failures (Phase-15)
> - Blocked states (Phase-13)
> - NOT_READY states (Phase-13)

---

## 5. TIMEOUT / STALE DECISION HANDLING

### 5.1 Stale Decision Detection

| Condition | Result |
|-----------|--------|
| Decision age > max_age | DENIED |
| No timestamp | DENIED |
| Invalid timestamp format | DENIED |

### 5.2 Timeout Values

| Parameter | Value | Description |
|-----------|-------|-------------|
| `MAX_DECISION_AGE_SECONDS` | 300 | 5 minutes |

### 5.3 Stale Handling Rule

> **RULE:** If a decision is older than MAX_DECISION_AGE_SECONDS,
> it is considered STALE and execution is DENIED.
> A fresh decision must be obtained from Phase-13/15.

---

## 6. DATA TYPES REQUIRED

| Type | Kind | Frozen |
|------|------|--------|
| `ExecutionPermission` | Enum | N/A |
| `ExecutionContext` | Dataclass | ✅ `frozen=True` |
| `ExecutionDecision` | Dataclass | ✅ `frozen=True` |

---

## 7. FUNCTIONAL REQUIREMENTS

### 7.1 Required Functions

| Function | Input | Output |
|----------|-------|--------|
| `check_handoff_signals()` | HandoffDecision | bool |
| `check_contract_signals()` | ContractValidationResult | bool |
| `check_human_present()` | ExecutionContext | bool |
| `check_stale_decision()` | ExecutionContext | bool |
| `decide_execution()` | ExecutionContext | ExecutionDecision |

### 7.2 Function Constraints

All functions MUST be:
- Pure (no side effects)
- Deterministic (same input → same output)
- Deny-by-default (unknown → denied)

---

## 8. SECURITY REQUIREMENTS

| Requirement | Enforcement |
|-------------|-------------|
| No subprocess | No subprocess module |
| No os.system | No os module |
| No eval/exec | No dynamic execution |
| No network | No socket/http |

---

**END OF REQUIREMENTS**
