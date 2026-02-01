# Phase-02 Actors Module

**Status:** REIMPLEMENTED-2026  
**Phase:** 02 — Actor & Role Model  

---

## Overview

Phase-02 defines the **Actor & Role Model** for the kali-mcp-toolkit-rebuilt system.

This module defines:
- **Actors** — Entities that can perform actions (HUMAN, SYSTEM)
- **Roles** — Permission sets assigned to actor types (OPERATOR, EXECUTOR)
- **Permissions** — Specific actions that can be performed

---

## Core Principles

1. **HUMAN has full authority** (OPERATOR role)
2. **SYSTEM has no autonomous authority** (EXECUTOR role)
3. **Trust flows from HUMAN only**
4. **Permissions are immutable**
5. **All checks are auditable**

---

## Actor Types

| Actor | Role | Trust Level | Permissions |
|-------|------|-------------|-------------|
| HUMAN | OPERATOR | 100 | INITIATE, CONFIRM, OVERRIDE, EXECUTE, AUDIT |
| SYSTEM | EXECUTOR | 0 | EXECUTE only |

---

## Module Structure

```
phase02_actors/
├── __init__.py       # Public API exports
├── actors.py         # Actor definitions
├── roles.py          # Role definitions
├── permissions.py    # Permission model
├── README.md         # This file
└── tests/
    ├── __init__.py
    ├── test_actors.py
    ├── test_roles.py
    └── test_permissions.py
```

---

## Usage

```python
from python.phase02_actors import (
    ActorType,
    Permission,
    check_permission,
    require_permission,
)

# Check if HUMAN can initiate
can_initiate = check_permission(ActorType.HUMAN, Permission.INITIATE)
assert can_initiate is True

# Check if SYSTEM can initiate (should be False)
can_system_initiate = check_permission(ActorType.SYSTEM, Permission.INITIATE)
assert can_system_initiate is False

# Require permission (raises error if denied)
require_permission(ActorType.HUMAN, Permission.CONFIRM)  # OK
require_permission(ActorType.SYSTEM, Permission.INITIATE)  # Raises UnauthorizedActorError
```

---

## Dependencies

Phase-02 imports from Phase-01:
- `UnauthorizedActorError` from `python.phase01_core.errors`

---

## Constraints

- This phase is **REIMPLEMENTED-2026**
- This phase defines **actor and role model**
- This phase contains **no execution logic**
- This phase is **frozen after completion**

---

**END OF README**
