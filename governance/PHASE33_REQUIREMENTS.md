# PHASE-33 REQUIREMENTS

**Phase:** Phase-33 — Human Decision → Execution Intent Binding  
**Type:** DESIGN-ONLY (NO CODE)  
**Version:** 1.0  
**Date:** 2026-01-26  
**Authority:** Human-Only  

---

## EXECUTIVE SUMMARY

Phase-33 defines the **intent binding layer** that translates a human decision (from Phase-32) into an immutable execution intent. Intent is DATA, not action. The system binds human decisions to structured intent objects that can be audited, validated, and revoked before execution.

---

## FUNCTIONAL REQUIREMENTS

### REQ-01: ExecutionIntent Structure

The ExecutionIntent dataclass SHALL be frozen and contain:

| Field | Type | Required | Mutable |
|-------|------|----------|---------|
| intent_id | str | ✅ | ❌ |
| decision_id | str | ✅ | ❌ |
| decision_type | HumanDecision | ✅ | ❌ |
| evidence_chain_hash | str | ✅ | ❌ |
| session_id | str | ✅ | ❌ |
| execution_state | str | ✅ | ❌ |
| created_at | str | ✅ | ❌ |
| created_by | str | ✅ | ❌ |
| intent_hash | str | ✅ | ❌ |

---

### REQ-02: Intent Binding Function

```
bind_decision_to_intent(
    decision_record: DecisionRecord,
    evidence_chain_hash: str,
    session_id: str,
    execution_state: str,
    timestamp: str
) -> ExecutionIntent
```

**Rules:**
- MUST be a pure function (no I/O)
- MUST validate decision_record is not None
- MUST validate all required fields are non-empty
- MUST compute intent_hash from all fields
- MUST return immutable ExecutionIntent
- MUST fail on any invalid input (deny-by-default)

---

### REQ-03: Intent Revocation

Intent MAY be revoked BEFORE execution. Revocation requires:

| Requirement | Description |
|-------------|-------------|
| Revocation ID | Unique identifier |
| Intent ID | Reference to revoked intent |
| Revoked By | Human identifier |
| Revocation Reason | Mandatory reason |
| Revocation Timestamp | When revoked |

**Revocation is PERMANENT** — revoked intent cannot be un-revoked.

---

### REQ-04: Intent Validation

```
validate_intent(
    intent: ExecutionIntent,
    original_decision: DecisionRecord
) -> bool
```

**Validation Checks:**
| Check | Condition |
|-------|-----------|
| Decision Match | intent.decision_id == original_decision.decision_id |
| Type Match | intent.decision_type == original_decision.decision |
| Hash Valid | Recomputed hash matches intent_hash |
| Not Revoked | Intent is not revoked |
| Timestamp Valid | Created after decision timestamp |

---

### REQ-05: Intent Audit Trail

| Field | Type | Purpose |
|-------|------|---------|
| audit_id | str | Unique audit identifier |
| records | Tuple[IntentRecord, ...] | Append-only |
| session_id | str | Session reference |
| head_hash | str | Hash chain head |
| length | int | Record count |

**Audit is APPEND-ONLY and IMMUTABLE.**

---

### REQ-06: Decision Type Mapping

Each HumanDecision maps to a specific intent behavior:

| Decision | Intent Action |
|----------|---------------|
| CONTINUE | Intent to proceed to next step |
| RETRY | Intent to re-attempt current step |
| ABORT | Intent to terminate execution |
| ESCALATE | Intent to defer to higher authority |

**No other decisions are valid.**

---

### REQ-07: Binding Preconditions

Intent binding MUST verify:

| Precondition | Validation |
|--------------|------------|
| Decision exists | DecisionRecord is not None |
| Decision valid | Decision type in allowed set |
| Evidence exists | Hash is non-empty |
| Session valid | Session ID is non-empty |
| State valid | Execution state is recognized |
| Not halted | Execution state is not HALTED (for CONTINUE) |

---

### REQ-08: Intent Uniqueness

- Each intent MUST have a unique intent_id
- Intent ID format: `INTENT-{uuid_hex[:8]}`
- No duplicate intents for same decision

---

### REQ-09: Revocability Window

| State | Revocable |
|-------|-----------|
| Before execution | ✅ YES |
| During execution | ❌ NO |
| After execution | ❌ NO |

---

### REQ-10: Default Behavior

| Scenario | Default |
|----------|---------|
| Unknown decision type | REJECT binding |
| Missing evidence hash | REJECT binding |
| Invalid session | REJECT binding |
| Any ambiguity | REJECT binding |

**Deny-by-default applies to all binding operations.**

---

## NON-FUNCTIONAL REQUIREMENTS

### REQ-NF01: Performance

- Intent binding MUST complete in < 10ms
- Hash computation MUST be deterministic
- Validation MUST be O(1) complexity

### REQ-NF02: Determinism

- Same inputs MUST produce same intent_hash
- Pure functions only (no randomness except UUID generation)

### REQ-NF03: Testability

- All functions MUST be testable without mocks of authority
- 100% statement coverage required
- 100% branch coverage required

---

## ACCEPTANCE CRITERIA

| Criterion | Verification |
|-----------|--------------|
| All decision types bindable | Unit test per type |
| Intent immutability | Mutation test |
| Hash chain integrity | Integration test |
| Revocation works | Unit test |
| Validation catches invalid | Unit tests |
| No I/O in module | Code review |
| 100% coverage | Coverage report |

---

**END OF REQUIREMENTS**
