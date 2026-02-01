# PHASE-01 REQUIREMENTS

**Status:** REIMPLEMENTED-2026  
**Phase:** 01 — Core Constants, Identities, and Invariants  
**Date:** 2026-01-20  

---

## Purpose

Define the immutable system-wide constants, identities, and invariants that every future phase MUST obey.

---

## Functional Requirements

### FR-01: System Constants
- Define immutable system-wide constants
- Constants MUST NOT be modifiable at runtime
- Constants MUST be explicitly named and documented

### FR-02: Identity Model
- Define HUMAN as the sole authoritative actor
- Define SYSTEM as a non-authoritative executor
- SYSTEM MUST NOT act without HUMAN initiation

### FR-03: Invariants
- Define invariants that CANNOT be disabled
- Invariants MUST be enforced across all phases
- Violation of invariants MUST raise explicit errors

### FR-04: Error Definitions
- Define explicit error types for invariant violations
- Errors MUST be auditable and traceable

---

## Non-Functional Requirements

### NFR-01: No Execution Logic
- Phase-01 contains NO business logic
- Phase-01 contains NO execution logic
- Phase-01 is pure foundation

### NFR-02: No Forbidden Patterns
The following are FORBIDDEN in Phase-01:
- `auto_*` prefixes
- `score`, `rank`, `severity`
- `background`, `daemon`
- `thread`, `async`, `schedule`
- Network operations
- Subprocess operations

### NFR-03: Auditability
- All definitions MUST be explicit
- No hidden behavior
- No implicit defaults

---

## Constraints

- This phase is **REIMPLEMENTED-2026**
- This phase defines **system invariants**
- This phase contains **no execution**
- This phase is **frozen after completion**

---

**END OF REQUIREMENTS**
