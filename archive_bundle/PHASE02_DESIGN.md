# PHASE-02 DESIGN DOCUMENT

**Status:** REIMPLEMENTED-2026  
**Phase:** 02 — Actor & Role Model  
**Date:** 2026-01-21  

---

## 1. Actor Taxonomy

### Actor Types

| Actor Type | Description | Authority Level |
|------------|-------------|-----------------|
| HUMAN | The human operator | 100 (Maximum) |
| SYSTEM | The automated system | 0 (None) |

### Actor Properties

Each actor has:
- `actor_id` — Unique identifier
- `actor_type` — HUMAN or SYSTEM
- `name` — Human-readable name
- `permissions` — Set of allowed actions
- `trust_level` — Numeric trust value

---

## 2. Trust Boundaries

### Trust Matrix

| Trustor | Trustee | Trust Level | Notes |
|---------|---------|-------------|-------|
| HUMAN | HUMAN | FULL | Humans trust other humans |
| HUMAN | SYSTEM | NONE | Humans do not trust system for decisions |
| SYSTEM | HUMAN | FULL | System must defer to human |
| SYSTEM | SYSTEM | NONE | System cannot trust itself for decisions |

### Trust Rules

1. SYSTEM MUST NOT make decisions for HUMAN
2. SYSTEM MUST defer all authoritative actions to HUMAN
3. HUMAN MAY override any SYSTEM action
4. SYSTEM CANNOT override HUMAN

---

## 3. Role Definitions

### Role: OPERATOR (HUMAN)

```
Permissions:
  - INITIATE: Can start any action
  - CONFIRM: Can confirm any mutation
  - OVERRIDE: Can override system actions
  - AUDIT: Can view all audit logs
  - ADMIN: Full administrative access
```

### Role: EXECUTOR (SYSTEM)

```
Permissions:
  - EXECUTE: Can execute ONLY when HUMAN initiates
  
Forbidden:
  - Cannot INITIATE
  - Cannot CONFIRM
  - Cannot OVERRIDE
  - Cannot DECIDE
  - Cannot SCORE
  - Cannot RANK
```

---

## 4. Permission Model

### Permission Enum

```python
class Permission(Enum):
    INITIATE = "initiate"      # Start actions
    CONFIRM = "confirm"        # Confirm mutations
    OVERRIDE = "override"      # Override other actors
    EXECUTE = "execute"        # Execute approved actions
    AUDIT = "audit"            # View audit logs
    ADMIN = "admin"            # Administrative access
```

### Permission Validation

All permission checks MUST:
1. Verify actor identity
2. Check actor's role
3. Validate permission against role
4. Raise `UnauthorizedActorError` on failure

---

## 5. Failure Modes

### FM-01: Unauthorized Action Attempt
- **Trigger:** SYSTEM attempts HUMAN-only action
- **Response:** Raise `UnauthorizedActorError`
- **Recovery:** None — violation is logged and blocked

### FM-02: Invalid Actor
- **Trigger:** Unknown actor type
- **Response:** Raise `InvalidActorError`
- **Recovery:** None — must use defined actors

### FM-03: Permission Denied
- **Trigger:** Actor lacks required permission
- **Response:** Raise `PermissionDeniedError`
- **Recovery:** Request HUMAN authorization

---

## 6. Security Assumptions

### SA-01: Actor Immutability
- Actors are frozen after creation
- Actor properties cannot be modified

### SA-02: Permission Immutability
- Permissions are defined at compile time
- Runtime permission changes are FORBIDDEN

### SA-03: No Privilege Escalation
- SYSTEM cannot elevate to HUMAN permissions
- Role changes require code modification

### SA-04: Audit Trail
- All permission checks are auditable
- All failures are logged

---

## 7. Module Structure

```
python/
└── phase02_actors/
    ├── __init__.py       # Public API exports
    ├── actors.py         # Actor definitions
    ├── roles.py          # Role definitions
    ├── permissions.py    # Permission model
    ├── README.md         # Module documentation
    └── tests/
        ├── __init__.py
        ├── test_actors.py
        ├── test_roles.py
        ├── test_permissions.py
        └── test_phase02_no_forbidden_behavior.py
```

---

## Constraints

- This phase is **REIMPLEMENTED-2026**
- This phase defines **actor and role model**
- This phase contains **no execution**
- This phase is **frozen after completion**

---

**END OF DESIGN DOCUMENT**
