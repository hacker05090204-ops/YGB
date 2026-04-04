# PHASE-09 REQUIREMENTS

**Phase:** Phase-09 - Bug Bounty Policy, Scope & Eligibility Logic  
**Status:** REQUIREMENTS DEFINED  
**Date:** 2026-01-24T08:05:00-05:00  
**Authority:** Human-Authorized Governance Process

---

## 1. OVERVIEW

Phase-09 defines the policy logic for bug bounty eligibility decisions. This is a **pure backend** module with no execution, no browser logic, and no network access.

---

## 2. IN-SCOPE VS OUT-OF-SCOPE RULES

### 2.1 In-Scope Definition

A vulnerability report is classified as **IN_SCOPE** if and only if ALL of the following conditions are TRUE:

| Condition | Description |
|-----------|-------------|
| `domain_valid` | Target domain/asset is in the defined asset list |
| `vulnerability_type_valid` | Vulnerability type is in the accepted types list |
| `submission_format_valid` | Report meets minimum required fields |
| `not_excluded` | Target is not in the exclusion list |

### 2.2 Out-of-Scope Explicit Rules

A vulnerability report is classified as **OUT_OF_SCOPE** if ANY of the following conditions are TRUE:

| Rule ID | Condition | Result |
|---------|-----------|--------|
| `OOS-001` | Domain not in asset list | OUT_OF_SCOPE |
| `OOS-002` | Vulnerability type explicitly excluded | OUT_OF_SCOPE |
| `OOS-003` | Report missing required fields | OUT_OF_SCOPE |
| `OOS-004` | Target in exclusion list | OUT_OF_SCOPE |
| `OOS-005` | Self-attack / researcher-owned asset | OUT_OF_SCOPE |
| `OOS-006` | Already public disclosure | OUT_OF_SCOPE |

### 2.3 Default Behavior

> **DENY-BY-DEFAULT:** If a report cannot be explicitly classified as IN_SCOPE,
> it SHALL be classified as OUT_OF_SCOPE.

---

## 3. DUPLICATE REPORT CLASSIFICATION

### 3.1 Duplicate Detection Rules

A report is classified as **DUPLICATE** if ALL of the following match a previous report:

| Attribute | Match Requirement |
|-----------|-------------------|
| `target_asset` | Exact match |
| `vulnerability_type` | Exact match |
| `affected_parameter` | Exact match (if applicable) |
| `root_cause_signature` | Hash match within threshold |

### 3.2 Non-Duplicate Conditions

A report is NOT a duplicate if ANY of the following are true:

| Condition | Reason |
|-----------|--------|
| Different root cause | Different underlying issue |
| Different attack vector | Novel exploitation path |
| Prior report was REJECTED | Previous rejection does not block new submission |
| Prior report was OUT_OF_SCOPE | Scope change may apply |

### 3.3 Duplicate Precedence

| Scenario | Result |
|----------|--------|
| First submission | NOT a duplicate |
| Same issue, same researcher | DUPLICATE (self-duplicate) |
| Same issue, different researcher | DUPLICATE (external duplicate) |
| Similar but distinct issue | NOT a duplicate → NEEDS_REVIEW |

---

## 4. ELIGIBLE VS NOT-ELIGIBLE LOGIC

### 4.1 Eligibility Decision Table

| Scope Result | Duplicate Status | Eligibility |
|--------------|------------------|-------------|
| IN_SCOPE | NOT_DUPLICATE | **ELIGIBLE** |
| IN_SCOPE | DUPLICATE | **DUPLICATE** |
| OUT_OF_SCOPE | NOT_DUPLICATE | **NOT_ELIGIBLE** |
| OUT_OF_SCOPE | DUPLICATE | **NOT_ELIGIBLE** |

### 4.2 Eligibility Preconditions

A report can only be **ELIGIBLE** if:

| Precondition | Requirement |
|--------------|-------------|
| Scope | IN_SCOPE |
| Duplicate | NOT a duplicate |
| Format | Valid submission format |
| Policy | Matches current bounty policy |

### 4.3 Not-Eligible Conditions

A report is **NOT_ELIGIBLE** if ANY of the following are true:

| Condition | Reason |
|-----------|--------|
| OUT_OF_SCOPE | Target not covered |
| Missing required fields | Incomplete submission |
| Policy violation | Violates program terms |
| Expired program | Bounty program no longer active |

---

## 5. NEEDS-REVIEW CONDITIONS

### 5.1 Human Review Required

A report SHALL be classified as **NEEDS_REVIEW** if ANY of the following are true:

| Condition ID | Condition | Reason |
|--------------|-----------|--------|
| `NR-001` | Scope ambiguity | Target partially matches asset list |
| `NR-002` | Novel vulnerability type | Not in known types list |
| `NR-003` | Partial duplicate overlap | Some but not all attributes match |
| `NR-004` | Researcher dispute | Prior decision contested |
| `NR-005` | Policy edge case | Current policy unclear |
| `NR-006` | High severity claim | Critical/high claims require human validation |
| `NR-007` | Multiple vulnerabilities in one report | Chained issues need decomposition |
| `NR-008` | Unknown | Any unclassifiable condition |

### 5.2 Review Escalation Path

```
NEEDS_REVIEW
    │
    ▼
HUMAN AUTHORITY (Phase-02 OPERATOR or higher)
    │
    ├──▶ Confirm ELIGIBLE
    ├──▶ Confirm NOT_ELIGIBLE
    ├──▶ Confirm DUPLICATE
    └──▶ Request more information
```

---

## 6. DENY-BY-DEFAULT EVERYWHERE

### 6.1 Principle

> **INVARIANT:** In the absence of explicit permission, the default decision is DENY.

### 6.2 Application

| Scenario | Default |
|----------|---------|
| Unknown domain | OUT_OF_SCOPE |
| Unknown vuln type | NEEDS_REVIEW |
| Unknown researcher | No special treatment |
| Missing data | NOT_ELIGIBLE |
| Ambiguous case | NEEDS_REVIEW |
| System uncertainty | NEEDS_REVIEW |

---

## 7. GENERIC POLICY ABSTRACTION

### 7.1 Platform Independence

Phase-09 SHALL NOT be specific to any platform:

| ❌ Not Allowed | ✅ Required |
|----------------|-------------|
| HackerOne API calls | Generic policy interface |
| Bugcrowd-specific logic | Platform-agnostic types |
| Synack integration | Abstract asset definitions |

### 7.2 Policy Configuration

Policy SHALL be defined as immutable data structures:

```python
@dataclass(frozen=True)
class BountyPolicy:
    policy_id: str
    in_scope_assets: frozenset[str]
    excluded_assets: frozenset[str]
    accepted_vuln_types: frozenset[str]
    excluded_vuln_types: frozenset[str]
    active: bool
```

---

## 8. FUNCTIONAL REQUIREMENTS

### 8.1 Required Functions

| Function | Input | Output |
|----------|-------|--------|
| `evaluate_scope()` | `BountyContext` | `ScopeResult` |
| `check_duplicate()` | `BountyContext`, prior reports | `bool` |
| `make_decision()` | `BountyContext` | `BountyDecisionResult` |
| `requires_review()` | `BountyContext` | `bool` |

### 8.2 Function Constraints

All functions MUST be:
- Pure (no side effects)
- Deterministic (same input → same output)
- Total (handle all possible inputs)
- Immutable (no internal state mutation)

---

## 9. DATA TYPES REQUIRED

| Type | Kind | Frozen |
|------|------|--------|
| `ScopeResult` | Enum | N/A (enum) |
| `BountyDecision` | Enum | N/A (enum) |
| `BountyContext` | Dataclass | ✅ `frozen=True` |
| `BountyDecisionResult` | Dataclass | ✅ `frozen=True` |
| `BountyPolicy` | Dataclass | ✅ `frozen=True` |
| `DuplicateCheckResult` | Dataclass | ✅ `frozen=True` |

---

## 10. SECURITY REQUIREMENTS

| Requirement | Enforcement |
|-------------|-------------|
| No execution logic | No `exec()`, `eval()`, `subprocess` |
| No network access | No `socket`, `http`, `requests` |
| No filesystem write | No `open(..., 'w')` |
| No OS interaction | No `os.system()`, `os.popen()` |
| No async/threading | No `asyncio`, `threading`, `multiprocessing` |

---

## 11. TEST REQUIREMENTS

| Category | Minimum Tests |
|----------|---------------|
| Scope rules | 15+ |
| Eligibility decisions | 20+ |
| Duplicate detection | 15+ |
| Human review triggers | 10+ |
| Edge cases | 10+ |
| Forbidden behavior | 5+ |

---

**END OF REQUIREMENTS**
