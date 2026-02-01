# PHASE-04 REQUIREMENTS

**Status:** GOVERNANCE-ONLY  
**Phase:** 04 — Action Validation  
**Date:** 2026-01-21  

---

## Overview

This document defines the requirements for Phase-04: Action Validation.

All requirements MUST be compatible with Phase-01 invariants, Phase-02 actor model, and Phase-03 trust boundaries.

---

## Allowed Behavior

| Behavior | Allowed | Condition |
|----------|---------|-----------|
| Define action types | ✅ YES | Enum only |
| Define validation rules | ✅ YES | Pure functions |
| Return validation result | ✅ YES | ALLOW/DENY/ESCALATE |
| Log validation requests | ✅ YES | Audit requirement |
| Check actor permissions | ✅ YES | Uses Phase-02 |
| Check trust zone | ✅ YES | Uses Phase-03 |
| Return structured result | ✅ YES | Frozen dataclass |

---

## Forbidden Behavior

| Behavior | Forbidden | Reason |
|----------|-----------|--------|
| Execute actions | ❌ YES | Phase-01: No autonomous execution |
| Bypass human override | ❌ YES | Phase-01: Human authority absolute |
| Auto-approve mutations | ❌ YES | Phase-01: Mutation requires confirmation |
| Background validation | ❌ YES | Phase-01: No background actions |
| Implicit allow | ❌ YES | Phase-01: Everything explicit |
| Scoring actions | ❌ YES | Phase-01: No scoring/ranking |
| Network validation | ❌ YES | No network access |
| File validation | ❌ YES | No IO access |

---

## Trusted vs Untrusted Inputs

| Input Source | Trust Level | Validation Required |
|--------------|-------------|---------------------|
| HUMAN action request | ABSOLUTE | NO (human decision) |
| GOVERNANCE rule | IMMUTABLE | NO (frozen rules) |
| SYSTEM action request | CONDITIONAL | YES |
| EXTERNAL action request | ZERO | YES (strict) |

---

## Human vs System Trust Zones

| Zone | Can Request Action | Can Skip Validation | Can Override Result |
|------|-------------------|---------------------|---------------------|
| HUMAN | ✅ YES | ✅ YES | ✅ YES |
| GOVERNANCE | ❌ NO (defines rules) | N/A | ❌ NO |
| SYSTEM | ✅ YES | ❌ NO | ❌ NO |
| EXTERNAL | ✅ YES | ❌ NO | ❌ NO |

---

## Action Types (Proposed)

| Action Type | Description | Validation Level |
|-------------|-------------|------------------|
| READ | Read-only access | LOW |
| WRITE | State modification | HIGH |
| DELETE | Data removal | CRITICAL |
| EXECUTE | Command execution | CRITICAL |
| CONFIGURE | Settings change | HIGH |

---

## Validation Results

| Result | Meaning | Next Step |
|--------|---------|-----------|
| ALLOW | Action may proceed | Caller may execute |
| DENY | Action not permitted | Caller must stop |
| ESCALATE | Requires human approval | Request human decision |

---

## Security Invariants

Phase-04 establishes the following security invariants:

```
VALIDATION_INVARIANT_01: Human Override
  - Human can ALLOW or DENY any action regardless of validation result

VALIDATION_INVARIANT_02: Deny by Default
  - Unknown actions are DENIED, not allowed

VALIDATION_INVARIANT_03: Explicit Results
  - All validations return explicit ALLOW/DENY/ESCALATE result

VALIDATION_INVARIANT_04: Audit Trail
  - All validation requests and results are logged

VALIDATION_INVARIANT_05: No Execution
  - Validation NEVER executes the action itself
```

---

## Statement: Phase-04 MUST NOT Weaken Prior Phases

> **BINDING CONSTRAINT:**
> 
> Phase-04 MUST NOT weaken, bypass, or reinterpret any invariant
> from Phase-01, Phase-02, or Phase-03.
> 
> Phase-04 ONLY defines validation logic within the boundaries
> already established by prior phases.
> 
> Any Phase-04 requirement that conflicts with prior phases is INVALID.

---

**END OF REQUIREMENTS**
