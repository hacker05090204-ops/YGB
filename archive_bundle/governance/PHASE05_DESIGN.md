# PHASE-05 DESIGN

**Phase:** 05 — Workflow State Model  
**Status:** DESIGN COMPLETE  
**Date:** 2026-01-22  

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                    WORKFLOW STATE MACHINE                           │
└─────────────────────────────────────────────────────────────────────┘

                    ┌──────────┐
                    │   INIT   │
                    └────┬─────┘
                         │ VALIDATE
                         ▼
                    ┌──────────┐
            ┌───────│ VALIDATED│───────┐
            │       └────┬─────┘       │
            │            │             │
            │ COMPLETE   │ ESCALATE    │ (HUMAN only)
            │ (HUMAN)    ▼             │
            │       ┌──────────┐       │
            │       │ ESCALATED│       │
            │       └────┬─────┘       │
            │      ┌─────┴─────┐       │
            │      │           │       │
            │   APPROVE     REJECT     │
            │   (HUMAN)    (HUMAN)     │
            │      ▼           ▼       │
            │ ┌────────┐ ┌────────┐    │
            │ │APPROVED│ │REJECTED│    │
            │ └───┬────┘ └────────┘    │
            │     │                    │
            │  COMPLETE                │
            │     │                    │
            ▼     ▼                    │
       ┌───────────────┐               │
       │   COMPLETED   │◄──────────────┘
       └───────────────┘

       ┌───────────────┐
       │   ABORTED     │◄── Any state (HUMAN only)
       └───────────────┘
```

---

## WorkflowState Enum

```python
class WorkflowState(Enum):
    INIT = "init"
    VALIDATED = "validated"
    ESCALATED = "escalated"
    APPROVED = "approved"
    REJECTED = "rejected"
    COMPLETED = "completed"
    ABORTED = "aborted"
```

---

## StateTransition Enum

```python
class StateTransition(Enum):
    VALIDATE = "validate"
    ESCALATE = "escalate"
    APPROVE = "approve"
    REJECT = "reject"
    COMPLETE = "complete"
    ABORT = "abort"
```

---

## Transition Request Dataclass

```python
@dataclass(frozen=True)
class TransitionRequest:
    current_state: WorkflowState
    transition: StateTransition
    actor_type: ActorType
```

---

## Transition Response Dataclass

```python
@dataclass(frozen=True)
class TransitionResponse:
    request: TransitionRequest
    allowed: bool
    new_state: Optional[WorkflowState]
    reason: str
```

---

## Transition Logic

```python
def attempt_transition(request: TransitionRequest) -> TransitionResponse:
    # Pure function - no side effects
    # Returns whether transition is allowed and new state
```

**Rules:**
1. HUMAN can perform any valid transition
2. SYSTEM can only: VALIDATE, ESCALATE, COMPLETE (from APPROVED)
3. Unknown transitions → DENY
4. Invalid from-state → DENY
5. Default → DENY

---

## Valid Transitions Matrix

| From | VALIDATE | ESCALATE | APPROVE | REJECT | COMPLETE | ABORT |
|------|----------|----------|---------|--------|----------|-------|
| INIT | VALIDATED | ❌ | ❌ | ❌ | ❌ | ABORTED* |
| VALIDATED | ❌ | ESCALATED | ❌ | ❌ | COMPLETED* | ABORTED* |
| ESCALATED | ❌ | ❌ | APPROVED* | REJECTED* | ❌ | ABORTED* |
| APPROVED | ❌ | ❌ | ❌ | ❌ | COMPLETED | ABORTED* |
| REJECTED | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| COMPLETED | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| ABORTED | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |

`*` = HUMAN only

---

## Design Constraints

1. **Pure functions only** — No side effects
2. **Frozen dataclasses** — All data immutable
3. **Closed enums** — No dynamic states/transitions
4. **No IO** — No file, network, or database access
5. **No threading** — Synchronous only

---

**END OF DESIGN**
