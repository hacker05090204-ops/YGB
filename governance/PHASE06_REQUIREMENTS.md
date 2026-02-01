# PHASE-06 REQUIREMENTS

**Phase:** Phase-06 - Decision Aggregation & Authority Resolution  
**Status:** 📋 **APPROVED**  
**Creation Date:** 2026-01-23T14:46:00-05:00  

---

## PURPOSE

Phase-06 aggregates validation results, workflow transitions, actor types, and trust zones into a single `FinalDecision` with an explicit reason.

---

## INPUTS

Phase-06 accepts the following inputs:

| Input | Source | Type |
|-------|--------|------|
| `validation_response` | Phase-04 | `ValidationResponse` |
| `transition_response` | Phase-05 | `TransitionResponse` |
| `actor_type` | Phase-02 | `ActorType` |
| `trust_zone` | Phase-03 | `TrustZone` |

---

## OUTPUTS

Phase-06 produces:

| Output | Type | Values |
|--------|------|--------|
| `decision` | `FinalDecision` | ALLOW, DENY, ESCALATE |
| `reason` | `str` | Non-empty explanation |

---

## DECISION PRIORITY ORDER

Decisions are resolved in the following explicit priority order:

```
1. HUMAN OVERRIDE
   - If actor_type == HUMAN AND validation_response.result == ALLOW:
     → ALLOW (HUMAN authority is supreme)

2. TERMINAL WORKFLOW BLOCK
   - If workflow state is TERMINAL (COMPLETED, ABORTED, REJECTED):
     → DENY (terminal states block all decisions)

3. WORKFLOW TRANSITION DENIED
   - If transition_response.allowed == False:
     → DENY (workflow transition not permitted)

4. VALIDATION RESULT ESCALATE
   - If validation_response.result == ESCALATE:
     → ESCALATE (requires human review)

5. VALIDATION RESULT DENY
   - If validation_response.result == DENY:
     → DENY (validation failed)

6. UNTRUSTED ZONE
   - If trust_zone == UNTRUSTED:
     → ESCALATE (untrusted sources require review)

7. SYSTEM CRITICAL ACTION
   - If actor_type == SYSTEM AND action is CRITICAL:
     → ESCALATE (SYSTEM cannot ALLOW critical actions)

8. ALL CHECKS PASS
   - If validation_response.result == ALLOW AND transition_response.allowed == True:
     → ALLOW (all conditions met)

9. DEFAULT DENY
   - All other cases:
     → DENY (deny-by-default)
```

---

## ALLOWED BEHAVIORS

| Behavior | Status |
|----------|--------|
| Aggregate inputs from Phase-02, 03, 04, 05 | ✅ ALLOWED |
| Return ALLOW / DENY / ESCALATE | ✅ ALLOWED |
| Return non-empty reason string | ✅ ALLOWED |
| Pure function with no side effects | ✅ ALLOWED |
| Frozen dataclasses | ✅ ALLOWED |
| Closed enums | ✅ ALLOWED |

---

## FORBIDDEN BEHAVIORS

| Behavior | Status |
|----------|--------|
| Execute actions | ❌ FORBIDDEN |
| Modify inputs | ❌ FORBIDDEN |
| Access file system | ❌ FORBIDDEN |
| Access network | ❌ FORBIDDEN |
| Spawn threads/processes | ❌ FORBIDDEN |
| Use async/await | ❌ FORBIDDEN |
| Import phase07+ | ❌ FORBIDDEN |
| Auto-execute decisions | ❌ FORBIDDEN |
| Implicit decision paths | ❌ FORBIDDEN |
| Reduce HUMAN authority | ❌ FORBIDDEN |

---

## SECURITY INVARIANTS

| Invariant ID | Name | Description |
|--------------|------|-------------|
| DECISION_INV_01 | HUMAN_OVERRIDE_ALWAYS_WINS | HUMAN actor's ALLOW is never overridden |
| DECISION_INV_02 | DENY_BY_DEFAULT | Unknown combinations result in DENY |
| DECISION_INV_03 | NO_IMPLICIT_DECISIONS | All decision paths are explicit |
| DECISION_INV_04 | NO_AUTONOMOUS_EXECUTION | No action execution occurs |
| DECISION_INV_05 | NO_FORWARD_IMPORTS | No imports from phase07+ |
| DECISION_INV_06 | IMMUTABLE_DECISIONS | All dataclasses are frozen |
| DECISION_INV_07 | TERMINAL_BLOCKS_ALL | Terminal workflow states deny all |
| DECISION_INV_08 | EXPLICIT_REASONS | Every decision has a non-empty reason |

---

## TEST REQUIREMENTS

Tests MUST verify:

1. HUMAN override always wins
2. Terminal workflow states block all decisions
3. DENY by default for unknown combinations
4. ESCALATE propagates from validation
5. SYSTEM cannot ALLOW critical actions
6. Reasons are non-empty
7. No forbidden imports
8. No phase07+ imports
9. All dataclasses are frozen
10. All enums are closed

Coverage requirement: **100%**

---

## IMPLEMENTATION CONSTRAINTS

- Python only
- Pure functions only
- Frozen dataclasses only
- Closed enums only
- No IO
- No network
- No async
- No threading
- No subprocess
- No exec/eval

---

**END OF REQUIREMENTS**
