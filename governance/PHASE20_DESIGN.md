# PHASE-20 DESIGN

**Phase:** Phase-20 - HUMANOID HUNTER Executor Adapter & Safety Harness  
**Status:** DESIGN COMPLETE  
**Date:** 2026-01-25T15:30:00-05:00  

---

## 1. ENUMS

### 1.1 ExecutorCommandType Enum

```python
class ExecutorCommandType(Enum):
    """Executor command types. CLOSED."""
    NAVIGATE = auto()
    CLICK = auto()
    READ = auto()
    SCROLL = auto()
    SCREENSHOT = auto()
    EXTRACT = auto()
    SHUTDOWN = auto()
```

### 1.2 ExecutorResponseType Enum

```python
class ExecutorResponseType(Enum):
    """Executor response types. CLOSED."""
    SUCCESS = auto()
    FAILURE = auto()
    TIMEOUT = auto()
    ERROR = auto()
    REFUSED = auto()
```

### 1.3 ExecutorStatus Enum

```python
class ExecutorStatus(Enum):
    """Executor status. CLOSED."""
    READY = auto()
    BUSY = auto()
    OFFLINE = auto()
    ERROR = auto()
```

---

## 2. DATACLASSES

### 2.1 ExecutorInstructionEnvelope (frozen=True)

```python
@dataclass(frozen=True)
class ExecutorInstructionEnvelope:
    instruction_id: str
    execution_id: str
    command_type: ExecutorCommandType
    target_url: str
    target_selector: str
    timestamp: str
    timeout_ms: int = 30000
```

### 2.2 ExecutorResponseEnvelope (frozen=True)

```python
@dataclass(frozen=True)
class ExecutorResponseEnvelope:
    instruction_id: str
    response_type: ExecutorResponseType
    evidence_hash: str
    error_message: str
    timestamp: str
```

### 2.3 ExecutionSafetyResult (frozen=True)

```python
@dataclass(frozen=True)
class ExecutionSafetyResult:
    is_safe: bool
    reason_code: str
    reason_description: str
```

---

## 3. SAFETY DECISION TABLE

| Response Type | evidence_hash | instruction_id match | Result |
|---------------|---------------|----------------------|--------|
| SUCCESS | Present | Yes | ✅ SAFE |
| SUCCESS | Missing | Yes | ❌ DENIED |
| SUCCESS | Present | No | ❌ DENIED |
| FAILURE | Any | Yes | ✅ SAFE |
| TIMEOUT | Any | Yes | ✅ SAFE |
| ERROR | Any | Yes | ✅ SAFE |
| REFUSED | Any | Yes | ✅ SAFE |
| Any | Any | No | ❌ DENIED |
| Unknown | Any | Any | ❌ DENIED |

---

## 4. MODULE STRUCTURE

```
HUMANOID_HUNTER/
├── README.md
├── interface/
│   ├── __init__.py
│   ├── executor_types.py
│   ├── executor_context.py
│   └── executor_adapter.py
├── contracts/
│   └── executor_contract.h  (C/C++ header placeholder)
└── tests/
    ├── __init__.py
    ├── test_executor_instruction.py
    ├── test_executor_response.py
    ├── test_safety_harness.py
    ├── test_deny_by_default.py
    └── test_no_browser_imports.py
```

---

## 5. INVARIANTS

1. **Executor is UNTRUSTED**
2. **SUCCESS requires evidence**
3. **instruction_id must match**
4. **Default deny** for unknown
5. **Immutable envelopes**

---

**END OF DESIGN**
