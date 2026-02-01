# PHASE-15 DESIGN

**Phase:** Phase-15 - Frontend ↔ Backend Contract Authority  
**Status:** DESIGN COMPLETE  
**Date:** 2026-01-25T05:58:00-05:00  

---

## 1. ENUMS

### 1.1 FrontendRequestField Enum

```python
class FrontendRequestField(Enum):
    """Allowed frontend request fields.
    
    CLOSED ENUM - No new members may be added.
    """
    # Required fields
    REQUEST_ID = "request_id"
    BUG_ID = "bug_id"
    TARGET_ID = "target_id"
    REQUEST_TYPE = "request_type"
    TIMESTAMP = "timestamp"
    # Optional fields
    SESSION_ID = "session_id"
    USER_CONTEXT = "user_context"
    NOTES = "notes"
```

### 1.2 RequestType Enum

```python
class RequestType(Enum):
    """Allowed request types.
    
    CLOSED ENUM - No new members may be added.
    """
    STATUS_CHECK = "STATUS_CHECK"
    READINESS_CHECK = "READINESS_CHECK"
    FULL_EVALUATION = "FULL_EVALUATION"
```

### 1.3 ValidationStatus Enum

```python
class ValidationStatus(Enum):
    """Validation result status.
    
    CLOSED ENUM - No new members may be added.
    """
    VALID = auto()
    DENIED = auto()
```

---

## 2. DATACLASSES

### 2.1 FrontendRequest (frozen=True)

```python
@dataclass(frozen=True)
class FrontendRequest:
    """Validated frontend request.
    
    Attributes:
        request_id: Unique request identifier
        bug_id: Bug being queried
        target_id: Target identifier
        request_type: Type of request
        timestamp: ISO timestamp
        session_id: Optional session ID
        user_context: Optional user context
        notes: Optional notes
    """
    request_id: str
    bug_id: str
    target_id: str
    request_type: RequestType
    timestamp: str
    session_id: Optional[str] = None
    user_context: Optional[str] = None
    notes: Optional[str] = None
```

### 2.2 ContractValidationResult (frozen=True)

```python
@dataclass(frozen=True)
class ContractValidationResult:
    """Immutable validation result.
    
    Attributes:
        status: VALID or DENIED
        is_valid: True if valid
        reason_code: Machine-readable reason
        reason_description: Human-readable reason
        request: Validated request if valid
        denied_fields: Fields that caused denial
    """
    status: ValidationStatus
    is_valid: bool
    reason_code: str
    reason_description: str
    request: Optional[FrontendRequest] = None
    denied_fields: tuple[str, ...] = ()
```

---

## 3. VALIDATION DECISION TABLE

### 3.1 Required Field Validation

| Field | Present | Empty | → Result |
|-------|---------|-------|----------|
| request_id | YES | NO | CONTINUE |
| request_id | YES | YES | DENIED |
| request_id | NO | - | DENIED |
| bug_id | YES | NO | CONTINUE |
| bug_id | YES | YES | DENIED |
| bug_id | NO | - | DENIED |
| target_id | YES | NO | CONTINUE |
| target_id | NO | - | DENIED |
| request_type | YES | NO | CONTINUE |
| request_type | NO | - | DENIED |
| timestamp | YES | NO | CONTINUE |
| timestamp | NO | - | DENIED |

### 3.2 Forbidden Field Detection

| Field in Payload | → Result | Code |
|------------------|----------|------|
| confidence | DENIED | FB-001 |
| confidence_level | DENIED | FB-002 |
| severity | DENIED | FB-003 |
| bug_severity | DENIED | FB-004 |
| readiness | DENIED | FB-005 |
| readiness_state | DENIED | FB-006 |
| human_presence | DENIED | FB-007 |
| can_proceed | DENIED | FB-008 |
| is_blocked | DENIED | FB-009 |
| evidence_state | DENIED | FB-010 |
| trust_level | DENIED | FB-011 |
| authority | DENIED | FB-012 |

### 3.3 Request Type Validation

| request_type Value | → Result |
|--------------------|----------|
| STATUS_CHECK | VALID |
| READINESS_CHECK | VALID |
| FULL_EVALUATION | VALID |
| (any other) | DENIED |

---

## 4. DENY-BY-DEFAULT TABLE

| Condition | → Result | Code |
|-----------|----------|------|
| Unknown field present | DENIED | DD-001 |
| Empty required field | DENIED | DD-002 |
| Invalid enum value | DENIED | DD-003 |
| Forbidden field present | DENIED | DD-004 |
| Null payload | DENIED | DD-005 |

---

## 5. FUNCTION SIGNATURES

```python
def validate_required_fields(payload: dict) -> ContractValidationResult:
    """Validate all required fields are present and non-empty."""

def validate_forbidden_fields(payload: dict) -> ContractValidationResult:
    """Check for any forbidden fields in payload."""

def validate_request_type(payload: dict) -> ContractValidationResult:
    """Validate request_type is in allowed list."""

def validate_unexpected_fields(payload: dict) -> ContractValidationResult:
    """Check for any unexpected fields (not in allowed list)."""

def validate_contract(payload: dict) -> ContractValidationResult:
    """Full contract validation. Deny-by-default."""
```

---

## 6. MODULE STRUCTURE

```
python/phase15_contract/
├── __init__.py
├── contract_types.py     # Enums
├── contract_context.py   # Dataclasses
├── validation_engine.py  # Validation logic
└── tests/
    ├── __init__.py
    ├── test_required_fields.py
    ├── test_forbidden_fields.py
    ├── test_enum_validation.py
    ├── test_deny_by_default.py
    └── test_tampered_payloads.py
```

---

## 7. INVARIANTS

1. **Deny-by-default:** Unknown → DENIED
2. **Backend authority:** Frontend cannot set critical fields
3. **Immutability:** All dataclasses are frozen
4. **Determinism:** Same input → same output

---

**END OF DESIGN**
