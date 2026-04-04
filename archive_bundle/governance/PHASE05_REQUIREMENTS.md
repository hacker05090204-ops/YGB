# PHASE-05 REQUIREMENTS

**Phase:** 05 — Workflow State Model  
**Status:** REQUIREMENTS DEFINED  
**Date:** 2026-01-22  

---

## Overview

Phase-05 defines a pure workflow state machine for controlling action lifecycle.

---

## WorkflowState Enum (CLOSED)

| State | Description |
|-------|-------------|
| `INIT` | Initial state, action not yet validated |
| `VALIDATED` | Action passed Phase-04 validation |
| `ESCALATED` | Action requires human approval |
| `APPROVED` | Human approved the action |
| `REJECTED` | Human rejected the action |
| `COMPLETED` | Action workflow finished successfully |
| `ABORTED` | Action workflow aborted |

---

## StateTransition Enum (CLOSED)

| Transition | Description |
|------------|-------------|
| `VALIDATE` | Move from INIT to VALIDATED |
| `ESCALATE` | Move to ESCALATED (requires human) |
| `APPROVE` | Human approves (HUMAN only) |
| `REJECT` | Human rejects (HUMAN only) |
| `COMPLETE` | Finalize workflow |
| `ABORT` | Abort workflow |

---

## Transition Rules

| From State | Transition | To State | Allowed By |
|------------|------------|----------|------------|
| INIT | VALIDATE | VALIDATED | SYSTEM, HUMAN |
| VALIDATED | ESCALATE | ESCALATED | SYSTEM, HUMAN |
| VALIDATED | COMPLETE | COMPLETED | HUMAN only |
| ESCALATED | APPROVE | APPROVED | HUMAN only |
| ESCALATED | REJECT | REJECTED | HUMAN only |
| APPROVED | COMPLETE | COMPLETED | SYSTEM, HUMAN |
| ANY | ABORT | ABORTED | HUMAN only |

---

## Forbidden Behavior

| Behavior | Status |
|----------|--------|
| Auto-progression without human | ❌ FORBIDDEN |
| SYSTEM approving actions | ❌ FORBIDDEN |
| SYSTEM rejecting actions | ❌ FORBIDDEN |
| Skipping escalation | ❌ FORBIDDEN |
| Unknown transitions | ❌ DENIED |
| Background state changes | ❌ FORBIDDEN |

---

## Security Invariants

```
WORKFLOW_INVARIANT_01: Human Override
  - Human can override any state transition

WORKFLOW_INVARIANT_02: Deny by Default
  - Unknown transitions are DENIED

WORKFLOW_INVARIANT_03: No Auto Progression
  - SYSTEM cannot advance to APPROVED/REJECTED/COMPLETED

WORKFLOW_INVARIANT_04: Explicit States
  - All states are explicit, no implicit states

WORKFLOW_INVARIANT_05: Immutable History
  - State transitions cannot be undone (forward only)
```

---

## Binding Constraint

> Phase-05 MUST NOT weaken any invariant from Phase-01 through Phase-04.

---

**END OF REQUIREMENTS**
