# PHASE-22 DESIGN

**Phase:** Phase-22 - Native Runtime Boundary & OS Isolation Contract  
**Status:** DESIGN COMPLETE  
**Date:** 2026-01-25T16:16:00-05:00  

---

## 1. ENUMS

### 1.1 NativeProcessState Enum

```python
class NativeProcessState(Enum):
    """Native process states. CLOSED."""
    PENDING = auto()
    RUNNING = auto()
    EXITED = auto()
    CRASHED = auto()
    TIMED_OUT = auto()
    KILLED = auto()
```

### 1.2 NativeExitReason Enum

```python
class NativeExitReason(Enum):
    """Native exit reasons. CLOSED."""
    NORMAL = auto()
    ERROR = auto()
    CRASH = auto()
    TIMEOUT = auto()
    KILLED = auto()
    UNKNOWN = auto()
```

### 1.3 IsolationDecision Enum

```python
class IsolationDecision(Enum):
    """Isolation decisions. CLOSED."""
    ACCEPT = auto()
    REJECT = auto()
    QUARANTINE = auto()
```

---

## 2. DATACLASSES

### 2.1 NativeExecutionContext (frozen=True)

```python
@dataclass(frozen=True)
class NativeExecutionContext:
    execution_id: str
    process_id: str
    command_hash: str
    timeout_ms: int
    timestamp: str
```

### 2.2 NativeExecutionResult (frozen=True)

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

### 2.3 IsolationDecisionResult (frozen=True)

```python
@dataclass(frozen=True)
class IsolationDecisionResult:
    decision: IsolationDecision
    reason_code: str
    reason_description: str
```

---

## 3. ISOLATION DECISION TABLE

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

## 4. MODULE STRUCTURE

```
HUMANOID_HUNTER/
├── native/
│   ├── __init__.py
│   ├── native_types.py
│   ├── native_context.py
│   ├── native_engine.py
│   └── tests/
│       ├── __init__.py
│       ├── test_native_exit.py
│       ├── test_isolation_decision.py
│       ├── test_native_validation.py
│       ├── test_deny_by_default.py
│       └── test_no_browser_imports.py
```

---

## 5. INVARIANTS

1. **Native code NEVER decides success**
2. **Exit code alone is insufficient**
3. **Crash ≠ failure ≠ success**
4. **Evidence must be structured**
5. **Unknown states → DENIED**

---

**END OF DESIGN**
