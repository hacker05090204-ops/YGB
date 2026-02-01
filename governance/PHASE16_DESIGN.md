# PHASE-16 DESIGN

**Phase:** Phase-16 - Execution Boundary & Browser Invocation Authority  
**Status:** DESIGN COMPLETE  
**Date:** 2026-01-25T06:15:00-05:00  

---

## 1. ENUMS

### 1.1 ExecutionPermission Enum

```python
class ExecutionPermission(Enum):
    """Execution permission decision.
    
    CLOSED ENUM - No new members may be added.
    """
    ALLOWED = auto()
    DENIED = auto()
```

---

## 2. DATACLASSES

### 2.1 ExecutionContext (frozen=True)

```python
@dataclass(frozen=True)
class ExecutionContext:
    """Context for execution permission decision.
    
    Attributes:
        bug_id: Bug identifier
        target_id: Target identifier
        handoff_readiness: From Phase-13 (ReadinessState)
        handoff_can_proceed: From Phase-13 (bool)
        handoff_is_blocked: From Phase-13 (bool)
        handoff_human_presence: From Phase-13 (HumanPresence)
        contract_is_valid: From Phase-15 (bool)
        human_present: Whether human is present
        decision_timestamp: ISO timestamp of decision
        human_override: Whether human override requested
    """
    bug_id: str
    target_id: str
    handoff_readiness: str  # ReadinessState value
    handoff_can_proceed: bool
    handoff_is_blocked: bool
    handoff_human_presence: str  # HumanPresence value
    contract_is_valid: bool
    human_present: bool
    decision_timestamp: str
    human_override: bool = False
```

### 2.2 ExecutionDecision (frozen=True)

```python
@dataclass(frozen=True)
class ExecutionDecision:
    """Immutable execution decision.
    
    Attributes:
        permission: ALLOWED or DENIED
        is_allowed: True if allowed
        reason_code: Machine-readable reason
        reason_description: Human-readable reason
        context: Original context
    """
    permission: ExecutionPermission
    is_allowed: bool
    reason_code: str
    reason_description: str
    context: ExecutionContext
```

---

## 3. EXPLICIT DECISION TABLE

### 3.1 Allow Conditions (ALL must be True)

| Condition | Required Value |
|-----------|----------------|
| handoff_readiness | "READY_FOR_BROWSER" |
| handoff_can_proceed | True |
| handoff_is_blocked | False |
| handoff_human_presence | "OPTIONAL" or (human_present = True) |
| contract_is_valid | True |
| decision not stale | True (< 300 seconds) |

### 3.2 Deny Conditions (ANY triggers DENIED)

| Condition | Result | Code |
|-----------|--------|------|
| context is None | DENIED | EX-000 |
| handoff_readiness = NOT_READY | DENIED | EX-001 |
| handoff_readiness = REVIEW_REQUIRED (no override) | DENIED | EX-002 |
| handoff_can_proceed = False | DENIED | EX-003 |
| handoff_is_blocked = True | DENIED | EX-004 |
| human_presence = REQUIRED, not present | DENIED | EX-005 |
| human_presence = BLOCKING | DENIED | EX-006 |
| contract_is_valid = False | DENIED | EX-007 |
| decision stale | DENIED | EX-008 |
| unknown readiness value | DENIED | EX-009 |

### 3.3 Human Override Table

| handoff_readiness | human_override | Result |
|-------------------|----------------|--------|
| READY_FOR_BROWSER | any | Check other conditions |
| REVIEW_REQUIRED | True | ALLOWED (if other conditions pass) |
| REVIEW_REQUIRED | False | DENIED |
| NOT_READY | any | DENIED (no override) |

---

## 4. MODULE STRUCTURE

```
python/phase16_execution/
├── __init__.py
├── execution_types.py     # Enum
├── execution_context.py   # Dataclasses
├── execution_engine.py    # Decision logic
└── tests/
    ├── __init__.py
    ├── test_execution_allowed.py
    ├── test_execution_denied.py
    ├── test_handoff_dependency.py
    ├── test_contract_dependency.py
    ├── test_deny_by_default.py
    └── test_no_browser_imports.py
```

---

## 5. FUNCTION SIGNATURES

```python
def check_handoff_signals(context: ExecutionContext) -> bool:
    """Check Phase-13 signals. Returns True if all pass."""

def check_contract_signals(context: ExecutionContext) -> bool:
    """Check Phase-15 signals. Returns True if valid."""

def check_human_present(context: ExecutionContext) -> bool:
    """Check human presence requirements."""

def decide_execution(context: ExecutionContext) -> ExecutionDecision:
    """Make final execution decision. Deny-by-default."""
```

---

## 6. INVARIANTS

1. **Deny-by-default:** Unknown → DENIED
2. **All conditions required:** Missing ANY condition → DENIED
3. **No execution here:** This is permission only
4. **Immutability:** All dataclasses frozen
5. **Determinism:** Same input → same output

---

**END OF DESIGN**
