# PHASE-17 DESIGN

**Phase:** Phase-17 - Browser Execution Interface Contract  
**Status:** DESIGN COMPLETE  
**Date:** 2026-01-25T07:05:00-05:00  

---

## 1. ENUMS

### 1.1 ActionType Enum

```python
class ActionType(Enum):
    """Allowed action types. CLOSED.
    """
    NAVIGATE = "NAVIGATE"
    CLICK = "CLICK"
    FILL = "FILL"
    SCREENSHOT = "SCREENSHOT"
    EXTRACT = "EXTRACT"
```

### 1.2 ResponseStatus Enum

```python
class ResponseStatus(Enum):
    """Response status values. CLOSED.
    """
    SUCCESS = auto()
    FAILURE = auto()
    TIMEOUT = auto()
```

### 1.3 ContractStatus Enum

```python
class ContractStatus(Enum):
    """Contract validation status. CLOSED.
    """
    VALID = auto()
    DENIED = auto()
```

---

## 2. DATACLASSES

### 2.1 ExecutionRequest (frozen=True)

```python
@dataclass(frozen=True)
class ExecutionRequest:
    """Request sent to executor."""
    request_id: str
    bug_id: str
    target_id: str
    action_type: ActionType
    timestamp: str
    execution_permission: str  # Must be "ALLOWED"
    parameters: Optional[dict] = None
    timeout_seconds: int = 300
    session_id: Optional[str] = None
```

### 2.2 ExecutionResponse (frozen=True)

```python
@dataclass(frozen=True)
class ExecutionResponse:
    """Response from executor (untrusted)."""
    request_id: str
    status: ResponseStatus
    timestamp: str
    evidence_hash: Optional[str] = None
    error_code: Optional[str] = None
    error_message: Optional[str] = None
    execution_time_ms: Optional[int] = None
```

### 2.3 ContractValidationResult (frozen=True)

```python
@dataclass(frozen=True)
class ContractValidationResult:
    """Result of contract validation."""
    status: ContractStatus
    is_valid: bool
    reason_code: str
    reason_description: str
    denied_fields: tuple = ()
```

---

## 3. DECISION TABLES

### 3.1 Request Validation

| Condition | Result | Code |
|-----------|--------|------|
| request is None | DENIED | RQ-000 |
| Missing request_id | DENIED | RQ-001 |
| Missing bug_id | DENIED | RQ-002 |
| Missing target_id | DENIED | RQ-003 |
| Missing action_type | DENIED | RQ-004 |
| Missing timestamp | DENIED | RQ-005 |
| Missing execution_permission | DENIED | RQ-006 |
| execution_permission != ALLOWED | DENIED | RQ-007 |
| Invalid action_type | DENIED | RQ-008 |
| Forbidden field present | DENIED | RQ-009 |
| All valid | VALID | RQ-OK |

### 3.2 Response Validation

| Condition | Result | Code |
|-----------|--------|------|
| response is None | DENIED | RS-000 |
| Missing request_id | DENIED | RS-001 |
| Missing status | DENIED | RS-002 |
| Missing timestamp | DENIED | RS-003 |
| Mismatched request_id | DENIED | RS-004 |
| Invalid status | DENIED | RS-005 |
| SUCCESS without evidence_hash | DENIED | RS-006 |
| Forbidden field present | DENIED | RS-007 |
| All valid | VALID | RS-OK |

---

## 4. MODULE STRUCTURE

```
python/phase17_interface/
├── __init__.py
├── interface_types.py     # Enums
├── interface_context.py   # Dataclasses
├── interface_engine.py    # Validation logic
└── tests/
    ├── __init__.py
    ├── test_request_validation.py
    ├── test_forbidden_fields.py
    ├── test_deny_by_default.py
    ├── test_executor_response_validation.py
    └── test_no_browser_imports.py
```

---

## 5. FUNCTION SIGNATURES

```python
def validate_execution_request(request: dict) -> ContractValidationResult:
    """Validate request before send."""

def validate_execution_response(
    response: dict,
    expected_request_id: str
) -> ContractValidationResult:
    """Validate response from executor."""

def verify_success_has_evidence(response: dict) -> bool:
    """Verify SUCCESS has evidence_hash."""
```

---

## 6. INVARIANTS

1. **Executor is untrusted:** All claims are verified
2. **Deny-by-default:** Unknown → DENIED
3. **Immutability:** All dataclasses frozen
4. **No implicit behavior:** Explicit tables only
5. **No execution:** Interface contract only

---

**END OF DESIGN**
