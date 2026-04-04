# Phase-01 Core Module

**Status:** REIMPLEMENTED-2026  
**Phase:** 01 — Core Constants, Identities, and Invariants  

---

## Overview

Phase-01 establishes the **immutable foundation** of the kali-mcp-toolkit-rebuilt system.

This module defines:
- **Constants** — Immutable system-wide values
- **Invariants** — Non-disableable rules that ALL phases MUST obey
- **Identities** — HUMAN and SYSTEM actor definitions
- **Errors** — Explicit error types for constraint violations

---

## Core Principles

1. **Human authority is absolute**
2. **No autonomous execution**
3. **No background actions**
4. **No scoring or ranking**
5. **No mutation without human confirmation**
6. **Everything is auditable**
7. **Everything is explicit**

---

## Module Structure

```
phase01_core/
├── __init__.py       # Public API exports
├── constants.py      # Immutable system constants
├── invariants.py     # Non-disableable invariants
├── identities.py     # HUMAN/SYSTEM identity model
├── errors.py         # Explicit error types
├── README.md         # This file
└── tests/
    ├── __init__.py
    ├── test_constants.py
    ├── test_invariants.py
    ├── test_identities.py
    └── test_no_forbidden_behavior.py
```

---

## Usage

```python
from python.phase01_core import (
    HUMAN,
    SYSTEM,
    HUMAN_AUTHORITY_ABSOLUTE,
    check_all_invariants,
)

# Verify all invariants hold
assert check_all_invariants() is True

# Check identity permissions
assert HUMAN.is_authoritative is True
assert SYSTEM.is_authoritative is False
```

---

## Constraints

- This phase is **REIMPLEMENTED-2026**
- This phase defines **system invariants**
- This phase contains **no execution logic**
- This phase is **frozen after completion**

---

**END OF README**
