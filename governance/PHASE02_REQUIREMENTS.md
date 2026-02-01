# PHASE-02 REQUIREMENTS

**Status:** REIMPLEMENTED-2026  
**Phase:** 02 — Actor & Role Model  
**Date:** 2026-01-21  

---

## Purpose

Define the Actor & Role Model that governs WHO can do WHAT in the system.

---

## Functional Requirements

### FR-01: Actor Registry
- Define a registry of all actor types
- Each actor MUST have a unique identifier
- Actors MUST be immutable after creation

### FR-02: Role Definitions
- Define HUMAN role with full authority
- Define SYSTEM role with no autonomous authority
- Roles MUST be explicit and documented

### FR-03: Trust Boundaries
- HUMAN trusts HUMAN
- HUMAN does NOT trust SYSTEM for decisions
- SYSTEM MUST defer to HUMAN for all actions

### FR-04: Permission Model
- HUMAN can: initiate, confirm, override, audit
- SYSTEM can: execute (only when HUMAN initiates)
- SYSTEM cannot: decide, score, rank, schedule

### FR-05: Actor Validation
- Provide validation functions for actor permissions
- Validation MUST raise errors on unauthorized actions

---

## Non-Functional Requirements

### NFR-01: No Execution Logic
- Phase-02 contains NO business execution logic
- Phase-02 only defines the actor model

### NFR-02: No Forbidden Patterns
The following are FORBIDDEN in Phase-02:
- `auto_*` prefixes
- `score`, `rank`, `severity`
- `background`, `daemon`
- `thread`, `async`, `schedule`
- Network operations
- Subprocess operations

### NFR-03: Phase-01 Compliance
- All Phase-02 code MUST obey Phase-01 invariants
- Phase-02 MUST import from Phase-01

---

## Constraints

- This phase is **REIMPLEMENTED-2026**
- This phase defines **actor and role model**
- This phase contains **no execution**
- This phase is **frozen after completion**

---

## Phase-1 Binding Constraint

> **CRITICAL:** Phase-2 MAY NOT weaken, override, or circumvent
> any Phase-1 constraints. Phase-1 invariants remain binding.

---

**END OF REQUIREMENTS**
