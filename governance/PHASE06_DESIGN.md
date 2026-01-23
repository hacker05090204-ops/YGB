# PHASE-06 DESIGN

**Phase:** Phase-06 - Decision Aggregation & Authority Resolution  
**Status:** 📋 **APPROVED**  
**Creation Date:** 2026-01-23T14:46:00-05:00  

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                      DecisionContext                            │
│  ┌─────────────────┐  ┌─────────────────┐                       │
│  │ ValidationResponse│  │TransitionResponse│                     │
│  │ (Phase-04)       │  │ (Phase-05)       │                     │
│  └─────────────────┘  └─────────────────┘                       │
│  ┌─────────────────┐  ┌─────────────────┐                       │
│  │ ActorType       │  │ TrustZone       │                       │
│  │ (Phase-02)      │  │ (Phase-03)      │                       │
│  └─────────────────┘  └─────────────────┘                       │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
                    ┌─────────────────┐
                    │ resolve_decision│
                    │ (pure function) │
                    └─────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                      DecisionResult                             │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐ │
│  │ context         │  │ decision        │  │ reason          │ │
│  │ (DecisionContext)│  │ (FinalDecision) │  │ (str)           │ │
│  └─────────────────┘  └─────────────────┘  └─────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
```

---

## Type Definitions

### FinalDecision Enum

```python
class FinalDecision(Enum):
    """
    Closed enum for final decision outcomes.
    No other values permitted.
    """
    ALLOW = "allow"
    DENY = "deny"
    ESCALATE = "escalate"
```

### DecisionContext Dataclass

```python
@dataclass(frozen=True)
class DecisionContext:
    """
    Immutable context for decision resolution.
    Aggregates inputs from Phase-02, 03, 04, 05.
    """
    validation_response: ValidationResponse  # Phase-04
    transition_response: TransitionResponse  # Phase-05
    actor_type: ActorType                    # Phase-02
    trust_zone: TrustZone                    # Phase-03
```

### DecisionResult Dataclass

```python
@dataclass(frozen=True)
class DecisionResult:
    """
    Immutable result of decision resolution.
    Always includes explicit reason.
    """
    context: DecisionContext
    decision: FinalDecision
    reason: str  # Never empty
```

---

## Decision Table

| Priority | Condition | Decision | Reason |
|----------|-----------|----------|--------|
| 1 | actor_type == HUMAN AND validation.result == ALLOW | ALLOW | HUMAN authority override |
| 2 | workflow state is TERMINAL | DENY | Terminal workflow state |
| 3 | transition.allowed == False | DENY | Workflow transition denied |
| 4 | validation.result == ESCALATE | ESCALATE | Validation requires escalation |
| 5 | validation.result == DENY | DENY | Validation denied |
| 6 | trust_zone == UNTRUSTED | ESCALATE | Untrusted source requires review |
| 7 | actor_type == SYSTEM AND action is critical | ESCALATE | SYSTEM cannot ALLOW critical |
| 8 | validation.result == ALLOW AND transition.allowed == True | ALLOW | All checks passed |
| 9 | DEFAULT | DENY | Deny by default |

---

## Pure Function Signature

```python
def resolve_decision(context: DecisionContext) -> DecisionResult:
    """
    Resolve a final decision based on aggregated context.
    
    This function is PURE:
    - No side effects
    - No IO
    - No network
    - No state mutation
    - Deterministic output for same input
    
    Args:
        context: Aggregated decision context
        
    Returns:
        DecisionResult with decision and reason
    """
```

---

## File Structure

```
python/phase06_decision/
├── __init__.py           # Module exports
├── decision_types.py     # FinalDecision enum
├── decision_context.py   # DecisionContext dataclass
├── decision_result.py    # DecisionResult dataclass
├── decision_engine.py    # resolve_decision() function
└── tests/
    ├── __init__.py
    ├── test_decision_types.py
    ├── test_decision_context.py
    ├── test_decision_result.py
    └── test_decision_engine.py
```

---

## Dependencies

### Required Imports

```python
from python.phase02_actors.actors import ActorType
from python.phase03_trust.trust_zones import TrustZone
from python.phase04_validation.validator import ValidationResponse
from python.phase04_validation.validation_results import ValidationResult
from python.phase05_workflow.state_machine import TransitionResponse
from python.phase05_workflow.states import WorkflowState, is_terminal_state
```

### Forbidden Imports

- `import os`
- `import subprocess`
- `import socket`
- `import asyncio`
- `import threading`
- `import phase07` or later

---

## Invariants Enforced

| Invariant | Implementation |
|-----------|----------------|
| HUMAN_OVERRIDE_ALWAYS_WINS | Priority 1 in decision table |
| DENY_BY_DEFAULT | Priority 9 (final default) |
| NO_IMPLICIT_DECISIONS | Explicit decision table |
| TERMINAL_BLOCKS_ALL | Priority 2 in decision table |
| IMMUTABLE_DECISIONS | `frozen=True` on all dataclasses |

---

**END OF DESIGN**
