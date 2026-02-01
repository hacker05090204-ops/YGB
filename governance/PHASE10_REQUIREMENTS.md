# PHASE-10 REQUIREMENTS

**Phase:** Phase-10 - Target Coordination & De-Duplication Authority  
**Status:** REQUIREMENTS DEFINED  
**Date:** 2026-01-24T10:25:00-05:00  
**Authority:** Human-Authorized Governance Process

---

## 1. OVERVIEW

Phase-10 defines the coordination logic for bug bounty work distribution and de-duplication. This is a **pure backend** module with no execution, no browser logic, and no network access.

---

## 2. TARGET IDENTITY ABSTRACTION

### 2.1 TargetID Definition

A target is uniquely identified by:

| Attribute | Type | Description |
|-----------|------|-------------|
| `program_id` | str | Bounty program identifier |
| `asset_id` | str | Target asset (domain, endpoint, etc.) |
| `vulnerability_class` | str | Type of vulnerability being tested |
| `target_hash` | str | SHA-256 hash of above attributes |

### 2.2 Target Identity Rules

| Rule | Description |
|------|-------------|
| **Immutability** | TargetID cannot be modified after creation |
| **Uniqueness** | target_hash is globally unique |
| **Determinism** | Same inputs always produce same hash |

---

## 3. BUG-WORK OWNERSHIP RULES

### 3.1 Claim States

| State | Description |
|-------|-------------|
| `UNCLAIMED` | No active claim on this target |
| `CLAIMED` | Active claim by a researcher |
| `RELEASED` | Claim voluntarily released |
| `EXPIRED` | Claim expired due to timeout |
| `COMPLETED` | Work completed, finding submitted |

### 3.2 Ownership Rules

| Rule ID | Rule | Enforcement |
|---------|------|-------------|
| `OWN-001` | One claim per target at a time | DENY if already claimed |
| `OWN-002` | Claim owner has exclusive access | DENY others during claim |
| `OWN-003` | Owner can release claim | ALLOW voluntary release |
| `OWN-004` | Claim expires after timeout | Auto-transition to EXPIRED |
| `OWN-005` | Human can override any claim | HUMAN authority supreme |

---

## 4. DUPLICATE PREVENTION ACROSS USERS

### 4.1 Duplicate Scenarios

| Scenario | Result |
|----------|--------|
| Same target, same user, already claimed | DENIED (self-duplicate) |
| Same target, different user, claimed | DENIED (already claimed) |
| Same target, no active claim | ALLOWED (grant claim) |
| Same target, expired claim | ALLOWED (reclaimable) |

### 4.2 Prevention Logic

```
IF target already has active claim:
    IF claimer == existing_owner:
        RETURN DENIED (already yours)
    ELSE:
        RETURN DENIED (claimed by another)
ELSE:
    GRANT CLAIM
```

---

## 5. TIME-BASED LOCK EXPIRY

### 5.1 Expiry Rules

| Rule | Description |
|------|-------------|
| Claim duration | Defined in policy (e.g., 24 hours) |
| Expiry check | Deterministic based on timestamps |
| Grace period | None (strict expiry) |
| Renewal | Must release and reclaim |

### 5.2 Expiry Decision Table

| Current Time | Claim Time | Duration | → Status |
|--------------|------------|----------|----------|
| T | T-1h | 24h | ACTIVE (not expired) |
| T | T-25h | 24h | EXPIRED |
| T | T-24h | 24h | EXPIRED (boundary) |

---

## 6. DENY-BY-DEFAULT ARBITRATION

### 6.1 Principle

> **INVARIANT:** In the absence of explicit permission, the default decision is DENY.

### 6.2 Arbitration Table

| Condition | Result |
|-----------|--------|
| Unknown target | DENY |
| Invalid claim context | DENY |
| Expired policy | DENY |
| Missing researcher ID | DENY |
| Duplicate claim attempt | DENY |
| All conditions met | ALLOW |

---

## 7. HUMAN OVERRIDE PATH

### 7.1 Override Conditions

| Condition | Override Authority |
|-----------|-------------------|
| Claim dispute | OPERATOR or higher |
| Policy exception | ADMINISTRATOR |
| Emergency release | ADMINISTRATOR |
| Audit requirement | AUDITOR |

### 7.2 Override Result

Human override produces:
- Decision marked as `HUMAN_OVERRIDE`
- Original decision preserved for audit
- Audit trail of override reason

---

## 8. DATA TYPES REQUIRED

| Type | Kind | Frozen |
|------|------|--------|
| `WorkClaimStatus` | Enum | N/A (enum) |
| `ClaimAction` | Enum | N/A (enum) |
| `TargetID` | Dataclass | ✅ `frozen=True` |
| `WorkClaimContext` | Dataclass | ✅ `frozen=True` |
| `WorkClaimResult` | Dataclass | ✅ `frozen=True` |
| `CoordinationPolicy` | Dataclass | ✅ `frozen=True` |

---

## 9. FUNCTIONAL REQUIREMENTS

### 9.1 Required Functions

| Function | Input | Output |
|----------|-------|--------|
| `create_target_id()` | program, asset, vuln | `TargetID` |
| `claim_target()` | context | `WorkClaimResult` |
| `release_claim()` | context | `WorkClaimResult` |
| `check_claim_status()` | target_id, claims | `WorkClaimStatus` |
| `is_claim_expired()` | claim, current_time | `bool` |

### 9.2 Function Constraints

All functions MUST be:
- Pure (no side effects)
- Deterministic (same input → same output)
- Total (handle all possible inputs)
- Immutable (no internal state mutation)

---

## 10. SECURITY REQUIREMENTS

| Requirement | Enforcement |
|-------------|-------------|
| No execution logic | No `exec()`, `eval()`, `subprocess` |
| No network access | No `socket`, `http`, `requests` |
| No filesystem write | No `open(..., 'w')` |
| No async/threading | No `asyncio`, `threading` |

---

## 11. TEST REQUIREMENTS

| Category | Minimum Tests |
|----------|---------------|
| Target ID creation | 10+ |
| Claim operations | 15+ |
| Duplicate prevention | 10+ |
| Expiry logic | 10+ |
| Deny-by-default | 5+ |
| Forbidden behavior | 5+ |

---

**END OF REQUIREMENTS**
