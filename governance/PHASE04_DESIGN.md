# PHASE-04 DESIGN

**Status:** GOVERNANCE-ONLY  
**Phase:** 04 — Action Validation  
**Date:** 2026-01-21  

---

## Overview

This document defines the high-level design for Phase-04: Action Validation.

Phase-04 establishes the validation model that determines whether actions
may proceed, built upon Phase-01 invariants, Phase-02 actors, and Phase-03 trust.

---

## High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    ACTION REQUEST                               │
│           (Actor + ActionType + Target + TrustZone)             │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                    VALIDATION PIPELINE                          │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────────┐  │
│  │ Actor Check │→ │ Trust Check │→ │ Action Permission Check │  │
│  │  (Phase-02) │  │  (Phase-03) │  │       (Phase-04)        │  │
│  └─────────────┘  └─────────────┘  └─────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                    VALIDATION RESULT                            │
│              ALLOW │ DENY │ ESCALATE_TO_HUMAN                   │
└─────────────────────────────────────────────────────────────────┘
```

---

## Action Type Enumeration (Design)

```python
# Future implementation in action_types.py
from enum import Enum

class ActionType(Enum):
    """Types of actions that can be validated."""
    
    READ = "read"
    """Read-only access - lowest risk."""
    
    WRITE = "write"
    """State modification - requires validation."""
    
    DELETE = "delete"
    """Data removal - critical, requires escalation."""
    
    EXECUTE = "execute"
    """Command execution - critical, requires escalation."""
    
    CONFIGURE = "configure"
    """Settings change - requires validation."""
```

---

## Validation Result Enumeration (Design)

```python
# Future implementation in validation_results.py
from enum import Enum

class ValidationResult(Enum):
    """Possible outcomes of action validation."""
    
    ALLOW = "allow"
    """Action may proceed."""
    
    DENY = "deny"
    """Action is not permitted."""
    
    ESCALATE = "escalate"
    """Action requires human approval."""
```

---

## Action Request Dataclass (Design)

```python
# Future implementation
from dataclasses import dataclass

@dataclass(frozen=True)
class ActionRequest:
    """Represents a request to perform an action."""
    
    actor_type: ActorType
    """Who is requesting the action."""
    
    action_type: ActionType
    """What action is being requested."""
    
    trust_zone: TrustZone
    """What trust level applies."""
    
    target: str
    """What is being acted upon."""
```

---

## Validation Response Dataclass (Design)

```python
# Future implementation
@dataclass(frozen=True)
class ValidationResponse:
    """Result of validating an action request."""
    
    request: ActionRequest
    """The original request."""
    
    result: ValidationResult
    """ALLOW, DENY, or ESCALATE."""
    
    reason: str
    """Human-readable explanation."""
    
    requires_human: bool
    """Whether human approval is needed."""
```

---

## Validation Logic (Design)

```
VALIDATION RULES:

1. IF actor_type == HUMAN:
   → ALLOW (human has absolute authority)

2. IF trust_zone == HUMAN:
   → ALLOW (trusted request)

3. IF action_type == READ and trust_zone >= SYSTEM:
   → ALLOW (low-risk read)

4. IF action_type in [DELETE, EXECUTE]:
   → ESCALATE (always require human for critical actions)

5. IF action_type == WRITE and trust_zone == EXTERNAL:
   → DENY (untrusted write)

6. IF action_type == WRITE and trust_zone == SYSTEM:
   → ESCALATE (system writes need human approval)

7. DEFAULT:
   → DENY (deny by default)
```

---

## Data Flow

```
┌──────────────┐
│    Caller    │
│ (any system) │
└──────┬───────┘
       │
       │ ActionRequest
       ▼
┌──────────────┐
│  validate()  │ ← Pure function, no side effects
└──────┬───────┘
       │
       │ ValidationResponse
       ▼
┌──────────────┐
│    Caller    │ → If ALLOW: may proceed
│  (decision)  │ → If DENY: must stop
│              │ → If ESCALATE: request human
└──────────────┘
```

---

## Failure Modes

| Failure | Cause | Response |
|---------|-------|----------|
| Unknown actor type | Invalid input | DENY |
| Unknown action type | Invalid input | DENY |
| Unknown trust zone | Invalid input | DENY |
| Validation function error | Bug | DENY (fail safe) |
| Missing audit log | System error | DENY (audit required) |

---

## Security Assumptions

1. **Actor type is verified** — Caller correctly identifies actor
2. **Trust zone is verified** — Caller correctly identifies trust level
3. **Caller respects result** — Caller honors DENY/ESCALATE
4. **Human is available** — Escalation can reach human
5. **Audit is working** — Validation results are logged

---

## Human Override Flow

```
┌───────────────────────────────────────────────────────────────┐
│                    HUMAN OVERRIDE                             │
│                                                               │
│   Any validation result can be overridden by human:          │
│                                                               │
│   ALLOW → Human may DENY (block something validated)         │
│   DENY  → Human may ALLOW (permit something blocked)         │
│   ESCALATE → Human decides ALLOW or DENY                     │
│                                                               │
│   Human authority is absolute. Validation is advisory.        │
└───────────────────────────────────────────────────────────────┘
```

---

## Audit Record (Design)

```python
# Future implementation
@dataclass(frozen=True)
class ValidationAuditRecord:
    """Audit record for a validation event."""
    
    timestamp: str
    """When validation occurred."""
    
    request: ActionRequest
    """What was requested."""
    
    response: ValidationResponse
    """What was decided."""
    
    human_override: bool
    """Whether human overrode the result."""
```

---

## Design Constraints

Phase-04 design is constrained by:

1. **Phase-01 Invariants** — Human authority, no autonomous execution
2. **Phase-02 Actor Model** — Actor types and permissions
3. **Phase-03 Trust Boundaries** — Trust zones and escalation
4. **No Execution Authority** — Validation only, no action execution
5. **No IO** — Pure functions with no side effects

---

## Future Implementation Notes

When Phase-04 implementation is authorized:

1. Create `python/phase04_validation/` module directory
2. Implement action types as closed enum
3. Implement validation results as closed enum
4. Implement request/response as frozen dataclass
5. Implement validate_action as pure function
6. Write tests BEFORE implementation
7. Ensure 100% test coverage
8. No mutation methods, no IO

---

**END OF DESIGN**
