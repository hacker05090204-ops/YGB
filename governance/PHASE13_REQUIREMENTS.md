# PHASE-13 REQUIREMENTS

**Phase:** Phase-13 - Human Readiness, Safety Gate & Browser Handoff Governance  
**Status:** REQUIREMENTS DEFINED  
**Date:** 2026-01-25T04:25:00-05:00  

---

## 1. OVERVIEW

Phase-13 defines the governance logic for determining when a bug is ready for browser handoff, what human presence is required, and when handoff must be blocked. This is a **pure backend policy module**—NO browser, NO execution.

---

## 2. WHEN A BUG IS SAFE TO PROCEED TO BROWSER

### 2.1 Readiness Criteria

| Criterion | Requirement |
|-----------|-------------|
| **Confidence** | Must be HIGH from Phase-12 |
| **Consistency** | Must be CONSISTENT or REPLAYABLE |
| **Human Review** | Must have passed human review |
| **No Blockers** | Zero active blocking conditions |

### 2.2 Readiness Decision Table

| Confidence | Consistency | Human Review | Blockers | → ReadinessState |
|------------|-------------|--------------|----------|------------------|
| LOW | Any | Any | Any | NOT_READY |
| MEDIUM | Any | Any | Any | NOT_READY |
| HIGH | INCONSISTENT | Any | Any | NOT_READY |
| HIGH | UNVERIFIED | Any | Any | NOT_READY |
| HIGH | RAW | Any | Any | REVIEW_REQUIRED |
| HIGH | CONSISTENT | NO | Any | REVIEW_REQUIRED |
| HIGH | CONSISTENT | YES | YES | NOT_READY |
| HIGH | CONSISTENT | YES | NO | READY_FOR_BROWSER |
| HIGH | REPLAYABLE | YES | NO | READY_FOR_BROWSER |

---

## 3. MANDATORY HUMAN PRESENCE RULES

### 3.1 Human Presence Enum

| Level | Meaning |
|-------|---------|
| `REQUIRED` | Human MUST be present and approve |
| `OPTIONAL` | Human may observe but not required |
| `BLOCKING` | Human absence blocks all progress |

### 3.2 Human Presence Decision Table

| ReadinessState | Bug Severity | Target Type | → HumanPresence |
|----------------|--------------|-------------|-----------------|
| NOT_READY | Any | Any | BLOCKING |
| REVIEW_REQUIRED | Any | Any | REQUIRED |
| READY_FOR_BROWSER | CRITICAL | Any | REQUIRED |
| READY_FOR_BROWSER | HIGH | PRODUCTION | REQUIRED |
| READY_FOR_BROWSER | HIGH | STAGING | OPTIONAL |
| READY_FOR_BROWSER | MEDIUM | Any | OPTIONAL |
| READY_FOR_BROWSER | LOW | Any | OPTIONAL |

---

## 4. ALLOWED VS BLOCKED HANDOFF STATES

### 4.1 Allowed Handoff

Handoff is ALLOWED when ALL conditions are met:
1. ReadinessState == READY_FOR_BROWSER
2. HumanPresence != BLOCKING
3. If HumanPresence == REQUIRED, human has confirmed
4. No active blocking conditions

### 4.2 Blocked Handoff

Handoff is BLOCKED when ANY condition is met:
1. ReadinessState == NOT_READY
2. HumanPresence == BLOCKING
3. Human required but not confirmed
4. Any active blocker exists

### 4.3 Blocking Conditions

| Condition | Blocks Handoff |
|-----------|----------------|
| Confidence < HIGH | YES |
| Evidence INCONSISTENT | YES |
| Human review pending | YES |
| Active escalation | YES |
| Previous failure on same target | YES |
| Rate limit exceeded | YES |

---

## 5. EXPLICIT STOP CONDITIONS

### 5.1 Immediate Stop

| Condition | Action |
|-----------|--------|
| Confidence drops | STOP immediately |
| New conflicting evidence | STOP immediately |
| Human revokes approval | STOP immediately |
| System error detected | STOP immediately |

### 5.2 Never Proceed When

- Confidence is not HIGH
- Evidence is INCONSISTENT or UNVERIFIED
- Human review was not completed
- Any blocking condition exists
- Human presence is BLOCKING

---

## 6. DENY-BY-DEFAULT RULE

### 6.1 Core Principle

> **CRITICAL:** If ANY condition is uncertain, ambiguous, or unknown:
> - ReadinessState → REVIEW_REQUIRED (not READY)
> - HumanPresence → REQUIRED (not OPTIONAL)
> - HandoffDecision → BLOCKED (not ALLOWED)

### 6.2 Unknown Input Handling

| Input | Result |
|-------|--------|
| Unknown confidence | NOT_READY |
| Unknown consistency | NOT_READY |
| Unknown severity | REVIEW_REQUIRED |
| Unknown target type | REQUIRED human presence |

---

## 7. DATA TYPES REQUIRED

| Type | Kind | Frozen |
|------|------|--------|
| `ReadinessState` | Enum | N/A (enum) |
| `HumanPresence` | Enum | N/A (enum) |
| `BugSeverity` | Enum | N/A (enum) |
| `TargetType` | Enum | N/A (enum) |
| `HandoffContext` | Dataclass | ✅ `frozen=True` |
| `HandoffDecision` | Dataclass | ✅ `frozen=True` |

---

## 8. FUNCTIONAL REQUIREMENTS

### 8.1 Required Functions

| Function | Input | Output |
|----------|-------|--------|
| `check_readiness()` | context | `ReadinessState` |
| `determine_human_presence()` | readiness, context | `HumanPresence` |
| `make_handoff_decision()` | context | `HandoffDecision` |
| `is_blocked()` | context | `bool` |

### 8.2 Function Constraints

All functions MUST be:
- Pure (no side effects)
- Deterministic (same input → same output)
- Total (handle all possible inputs)
- Deny-by-default (unknown → blocked)

---

## 9. SECURITY REQUIREMENTS

| Requirement | Enforcement |
|-------------|-------------|
| No execution logic | No `exec()`, `eval()`, `subprocess` |
| No network access | No `socket`, `http`, `requests` |
| No browser automation | No Playwright, Selenium |
| No filesystem write | No `open(..., 'w')` |
| No async/threading | No `asyncio`, `threading` |

---

**END OF REQUIREMENTS**
