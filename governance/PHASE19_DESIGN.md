# PHASE-19 DESIGN

**Phase:** Phase-19 - Browser Capability Governance & Action Authorization  
**Status:** DESIGN COMPLETE  
**Date:** 2026-01-25T15:05:00-05:00  

---

## 1. ENUMS

### 1.1 BrowserActionType Enum

```python
class BrowserActionType(Enum):
    """Browser action types. CLOSED."""
    NAVIGATE = auto()
    CLICK = auto()
    READ = auto()
    SCROLL = auto()
    EXTRACT_TEXT = auto()
    SCREENSHOT = auto()
    FILL_INPUT = auto()
    SUBMIT_FORM = auto()
    FILE_UPLOAD = auto()
    SCRIPT_EXECUTE = auto()
```

### 1.2 ActionRiskLevel Enum

```python
class ActionRiskLevel(Enum):
    """Action risk levels. CLOSED."""
    LOW = auto()
    MEDIUM = auto()
    HIGH = auto()
    FORBIDDEN = auto()
```

### 1.3 CapabilityDecision Enum

```python
class CapabilityDecision(Enum):
    """Capability decision. CLOSED."""
    ALLOWED = auto()
    DENIED = auto()
    HUMAN_REQUIRED = auto()
```

---

## 2. DATACLASSES

### 2.1 BrowserCapabilityPolicy (frozen=True)

```python
@dataclass(frozen=True)
class BrowserCapabilityPolicy:
    policy_id: str
    allowed_actions: frozenset  # BrowserActionType values
    risk_overrides: tuple = ()
    require_evidence: bool = True
    max_actions_per_execution: int = 100
```

### 2.2 ActionRequestContext (frozen=True)

```python
@dataclass(frozen=True)
class ActionRequestContext:
    execution_id: str
    action_type: BrowserActionType
    request_timestamp: str
    execution_state: str  # From Phase-18
    action_count: int = 0
```

### 2.3 CapabilityDecisionResult (frozen=True)

```python
@dataclass(frozen=True)
class CapabilityDecisionResult:
    decision: CapabilityDecision
    reason_code: str
    reason_description: str
    action_type: BrowserActionType
    risk_level: ActionRiskLevel
```

---

## 3. RISK CLASSIFICATION TABLE

| Action | Default Risk |
|--------|--------------|
| NAVIGATE | MEDIUM |
| CLICK | LOW |
| READ | LOW |
| SCROLL | LOW |
| EXTRACT_TEXT | LOW |
| SCREENSHOT | LOW |
| FILL_INPUT | MEDIUM |
| SUBMIT_FORM | HIGH |
| FILE_UPLOAD | FORBIDDEN |
| SCRIPT_EXECUTE | FORBIDDEN |

---

## 4. CAPABILITY DECISION TABLE

| Risk | State | Decision |
|------|-------|----------|
| FORBIDDEN | Any | DENIED |
| Any | COMPLETED | DENIED |
| Any | ESCALATED | HUMAN_REQUIRED |
| HIGH | ATTEMPTED | HUMAN_REQUIRED |
| MEDIUM | ATTEMPTED | ALLOWED |
| LOW | ATTEMPTED | ALLOWED |
| Unknown | Any | DENIED |

---

## 5. MODULE STRUCTURE

```
python/phase19_capability/
├── __init__.py
├── capability_types.py   # Enums
├── capability_context.py # Dataclasses
├── capability_engine.py  # Engine functions
└── tests/
    ├── __init__.py
    ├── test_action_classification.py
    ├── test_capability_decision.py
    ├── test_policy_validation.py
    ├── test_deny_by_default.py
    ├── test_forbidden_actions.py
    └── test_no_browser_imports.py
```

---

## 6. INVARIANTS

1. **Default deny:** Unknown → DENIED
2. **Immutable:** frozen=True
3. **Deterministic:** Same input → same output
4. **No execution:** Policy only

---

**END OF DESIGN**
