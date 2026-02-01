# PHASE-24 DESIGN

**Phase:** Phase-24 - Execution Orchestration & Deterministic Action Planning  
**Status:** DESIGN COMPLETE  
**Date:** 2026-01-25T17:11:00-05:00  

---

## 1. ENUMS

### 1.1 PlannedActionType Enum

```python
class PlannedActionType(Enum):
    """Planned action types. CLOSED."""
    CLICK = auto()
    TYPE = auto()
    NAVIGATE = auto()
    WAIT = auto()
    SCREENSHOT = auto()
    SCROLL = auto()
    UPLOAD = auto()
```

### 1.2 PlanRiskLevel Enum

```python
class PlanRiskLevel(Enum):
    """Plan risk levels. CLOSED."""
    LOW = auto()
    MEDIUM = auto()
    HIGH = auto()
    CRITICAL = auto()
```

### 1.3 PlanValidationDecision Enum

```python
class PlanValidationDecision(Enum):
    """Plan validation decisions. CLOSED."""
    ACCEPT = auto()
    REJECT = auto()
    REQUIRES_HUMAN = auto()
```

---

## 2. DATACLASSES

### 2.1 ActionPlanStep (frozen=True)

```python
@dataclass(frozen=True)
class ActionPlanStep:
    step_id: str
    step_index: int
    action_type: PlannedActionType
    target_selector: str
    action_value: str
    timeout_ms: int
    risk_level: PlanRiskLevel
```

### 2.2 ExecutionPlan (frozen=True)

```python
@dataclass(frozen=True)
class ExecutionPlan:
    plan_id: str
    execution_id: str
    steps: tuple[ActionPlanStep, ...]
    max_risk_level: PlanRiskLevel
    timestamp: str
    plan_hash: str
```

### 2.3 PlanValidationContext (frozen=True)

```python
@dataclass(frozen=True)
class PlanValidationContext:
    plan: ExecutionPlan
    allowed_actions: frozenset[PlannedActionType]
    max_allowed_risk: PlanRiskLevel
    timestamp: str
```

### 2.4 PlanValidationResult (frozen=True)

```python
@dataclass(frozen=True)
class PlanValidationResult:
    decision: PlanValidationDecision
    risk_level: PlanRiskLevel
    reason_code: str
    reason_description: str
```

---

## 3. VALIDATION RULES

| Structure | Capabilities | Risk ≤ Max | Decision |
|-----------|--------------|------------|----------|
| ✅ | ✅ | ✅ LOW/MED | ACCEPT |
| ✅ | ✅ | HIGH/CRIT | REQUIRES_HUMAN |
| ❌ | Any | Any | REJECT |
| ✅ | ❌ | Any | REJECT |

---

## 4. MODULE STRUCTURE

```
HUMANOID_HUNTER/
├── planning/
│   ├── __init__.py
│   ├── planning_types.py
│   ├── planning_context.py
│   ├── planning_engine.py
│   └── tests/
│       ├── __init__.py
│       ├── test_plan_structure.py
│       ├── test_plan_capabilities.py
│       ├── test_plan_risk.py
│       ├── test_deny_by_default.py
│       └── test_no_browser_imports.py
```

---

## 5. INVARIANTS

1. **Plans are immutable**
2. **Planning ≠ execution**
3. **Governance owns truth**
4. **Deny-by-default always**
5. **If plan cannot be proven safe, it must never exist**

---

**END OF DESIGN**
