# PHASE-22 REQUIREMENTS

**Phase:** Phase-22 - Native Runtime Boundary & OS Isolation Contract  
**Status:** REQUIREMENTS DEFINED  
**Date:** 2026-01-25T16:16:00-05:00  

---

## 1. NATIVE PROCESS STATES

| State | Description |
|-------|-------------|
| PENDING | Not yet started |
| RUNNING | Currently executing |
| EXITED | Normal exit |
| CRASHED | Process crashed |
| TIMED_OUT | Execution timed out |
| KILLED | Process was killed |

---

## 2. NATIVE EXIT REASONS

| Reason | Description | Trusted |
|--------|-------------|---------|
| NORMAL | Clean exit (code 0) | ⚠️ VERIFY |
| ERROR | Non-zero exit | NO |
| CRASH | Segfault, etc. | NO |
| TIMEOUT | Exceeded limit | NO |
| KILLED | External kill | NO |
| UNKNOWN | Unknown reason | NO |

---

## 3. ISOLATION DECISIONS

| Decision | Description |
|----------|-------------|
| ACCEPT | Result accepted |
| REJECT | Result rejected |
| QUARANTINE | Needs investigation |

---

## 4. NATIVE EXECUTION CONTEXT

```python
@dataclass(frozen=True)
class NativeExecutionContext:
    execution_id: str
    process_id: str
    command_hash: str
    timeout_ms: int
    timestamp: str
```

---

## 5. NATIVE EXECUTION RESULT

```python
@dataclass(frozen=True)
class NativeExecutionResult:
    execution_id: str
    process_state: NativeProcessState
    exit_reason: NativeExitReason
    exit_code: int
    evidence_hash: str
    output_hash: str
    duration_ms: int
```

---

## 6. DECISION RULES

| State | Exit Reason | Evidence | Decision |
|-------|-------------|----------|----------|
| EXITED | NORMAL | Present | ACCEPT |
| EXITED | NORMAL | Missing | REJECT |
| EXITED | ERROR | Any | REJECT |
| CRASHED | Any | Any | REJECT |
| TIMED_OUT | Any | Any | REJECT |
| KILLED | Any | Any | QUARANTINE |
| PENDING | Any | Any | REJECT |
| RUNNING | Any | Any | REJECT |

---

## 7. FUNCTION REQUIREMENTS

| Function | Input | Output |
|----------|-------|--------|
| `classify_native_exit()` | exit_code, state | NativeExitReason |
| `evaluate_isolation_result()` | result | IsolationDecision |
| `decide_native_outcome()` | result, context | IsolationDecisionResult |
| `is_native_result_valid()` | result | bool |

---

## 8. SECURITY REQUIREMENTS

| Requirement | Enforcement |
|-------------|-------------|
| No subprocess | No subprocess module |
| No os.system | No os module |
| No browser | No playwright/selenium |
| No execution | Policy only |
| Immutable | frozen=True |

---

**END OF REQUIREMENTS**
