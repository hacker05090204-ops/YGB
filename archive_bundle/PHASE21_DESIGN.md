# PHASE-21 DESIGN

**Phase:** Phase-21 - HUMANOID HUNTER Runtime Sandbox & Fault Isolation  
**Status:** DESIGN COMPLETE  
**Date:** 2026-01-25T16:00:00-05:00  

---

## 1. ENUMS

### 1.1 ExecutionFaultType Enum

```python
class ExecutionFaultType(Enum):
    """Execution fault types. CLOSED."""
    CRASH = auto()
    TIMEOUT = auto()
    PARTIAL = auto()
    INVALID_RESPONSE = auto()
    RESOURCE_EXHAUSTED = auto()
    SECURITY_VIOLATION = auto()
```

### 1.2 SandboxDecision Enum

```python
class SandboxDecision(Enum):
    """Sandbox decisions. CLOSED."""
    TERMINATE = auto()
    RETRY = auto()
    ESCALATE = auto()
```

### 1.3 RetryPolicy Enum

```python
class RetryPolicy(Enum):
    """Retry policies. CLOSED."""
    NO_RETRY = auto()
    RETRY_ONCE = auto()
    RETRY_LIMITED = auto()
    HUMAN_DECISION = auto()
```

---

## 2. DATACLASSES

### 2.1 SandboxContext (frozen=True)

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

### 2.2 FaultReport (frozen=True)

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

### 2.3 SandboxDecisionResult (frozen=True)

```python
@dataclass(frozen=True)
class SandboxDecisionResult:
    decision: SandboxDecision
    retry_policy: RetryPolicy
    reason_code: str
    reason_description: str
```

---

## 3. FAULT DECISION TABLE

| Fault | Retryable | Max | Decision |
|-------|-----------|-----|----------|
| CRASH | YES | 3 | RETRY/TERMINATE |
| TIMEOUT | YES | 3 | RETRY/TERMINATE |
| PARTIAL | NO | - | TERMINATE |
| INVALID_RESPONSE | NO | - | TERMINATE |
| RESOURCE_EXHAUSTED | NO | - | ESCALATE |
| SECURITY_VIOLATION | NO | - | TERMINATE |

---

## 4. MODULE STRUCTURE

```
HUMANOID_HUNTER/
├── sandbox/
│   ├── __init__.py
│   ├── sandbox_types.py
│   ├── sandbox_context.py
│   ├── sandbox_engine.py
│   └── tests/
│       ├── __init__.py
│       ├── test_fault_classification.py
│       ├── test_sandbox_decision.py
│       ├── test_retry_policy.py
│       ├── test_deny_by_default.py
│       └── test_no_browser_imports.py
```

---

## 5. INVARIANTS

1. **Crash ≠ success**
2. **Timeout ≠ success**
3. **Partial ≠ success**
4. **Faults NEVER escalate privileges**
5. **Max retries enforced**

---

**END OF DESIGN**
