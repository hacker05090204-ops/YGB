# PHASE-21 REQUIREMENTS

**Phase:** Phase-21 - HUMANOID HUNTER Runtime Sandbox & Fault Isolation  
**Status:** REQUIREMENTS DEFINED  
**Date:** 2026-01-25T16:00:00-05:00  

---

## 1. FAULT TYPES

| Fault | Description | Retry Allowed |
|-------|-------------|---------------|
| CRASH | Executor crashed | YES (limited) |
| TIMEOUT | Execution timed out | YES (limited) |
| PARTIAL | Partial output | NO |
| INVALID_RESPONSE | Malformed response | NO |
| RESOURCE_EXHAUSTED | Out of resources | NO |
| SECURITY_VIOLATION | Security breach | NO (immediate terminate) |

---

## 2. SANDBOX DECISIONS

| Decision | Description |
|----------|-------------|
| TERMINATE | Stop execution, no retry |
| RETRY | Retry allowed |
| ESCALATE | Human required |

---

## 3. RETRY POLICIES

| Policy | Description |
|--------|-------------|
| NO_RETRY | Never retry |
| RETRY_ONCE | Retry exactly once |
| RETRY_LIMITED | Retry up to max_retries |
| HUMAN_DECISION | Human must decide |

---

## 4. SANDBOX CONTEXT

```python
@dataclass(frozen=True)
class SandboxContext:
    execution_id: str
    instruction_id: str
    attempt_number: int
    max_retries: int
    timeout_ms: int
    timestamp: str
```

---

## 5. FAULT REPORT

```python
@dataclass(frozen=True)
class FaultReport:
    fault_id: str
    execution_id: str
    fault_type: ExecutionFaultType
    fault_message: str
    occurred_at: str
    attempt_number: int
```

---

## 6. DECISION RULES

| Fault Type | Attempt | Max | Decision |
|------------|---------|-----|----------|
| CRASH | < max | 3 | RETRY |
| CRASH | >= max | 3 | TERMINATE |
| TIMEOUT | < max | 3 | RETRY |
| TIMEOUT | >= max | 3 | TERMINATE |
| PARTIAL | Any | Any | TERMINATE |
| INVALID_RESPONSE | Any | Any | TERMINATE |
| RESOURCE_EXHAUSTED | Any | Any | ESCALATE |
| SECURITY_VIOLATION | Any | Any | TERMINATE |

---

## 7. FUNCTION REQUIREMENTS

| Function | Input | Output |
|----------|-------|--------|
| `classify_fault()` | fault_type, context | RetryPolicy |
| `decide_sandbox_outcome()` | fault, context | SandboxDecisionResult |
| `is_retry_allowed()` | context | bool |
| `enforce_retry_limit()` | context | bool |

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
