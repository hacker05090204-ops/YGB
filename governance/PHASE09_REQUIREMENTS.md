# PHASE-09 REQUIREMENTS

**Document Type:** Requirements Specification  
**Phase:** 09 — Bug Bounty Policy, Scope & Eligibility Logic  
**Date:** 2026-01-24  
**Status:** APPROVED  
**Authority:** Human-Only  

---

## 1. Scope Rules

### 1.1 In-Scope Assets

The following asset types are IN-SCOPE for bounty eligibility:

| Asset Type | Scope Status | Notes |
|------------|--------------|-------|
| `WEB_APP` | ✅ IN_SCOPE | Web applications |
| `API` | ✅ IN_SCOPE | REST/GraphQL APIs |
| `MOBILE` | ✅ IN_SCOPE | iOS/Android apps |

### 1.2 Out-of-Scope Assets

The following asset types are OUT-OF-SCOPE:

| Asset Type | Scope Status | Notes |
|------------|--------------|-------|
| `INFRASTRUCTURE` | ❌ OUT_OF_SCOPE | Internal infrastructure |
| `OUT_OF_PROGRAM` | ❌ OUT_OF_SCOPE | Explicitly excluded |
| `UNKNOWN` | ❌ OUT_OF_SCOPE | Deny-by-default |

### 1.3 Deny-by-Default Rule

> **REQUIREMENT R-SCOPE-001:** Any asset type not explicitly listed as IN_SCOPE
> MUST be treated as OUT_OF_SCOPE. This is the deny-by-default rule.

---

## 2. Duplicate Report Rules

### 2.1 Duplicate Detection

A report is considered DUPLICATE if:
1. The same vulnerability type exists
2. On the same asset
3. A prior report was already submitted

### 2.2 Duplicate Handling

| Condition | Decision |
|-----------|----------|
| First report of vulnerability | NOT duplicate |
| Same vuln, same asset, prior exists | DUPLICATE |
| Same vuln, different asset | NOT duplicate |
| Different vuln, same asset | NOT duplicate |

> **REQUIREMENT R-DUP-001:** Duplicate reports MUST return `BountyDecision.DUPLICATE`.
> 
> **REQUIREMENT R-DUP-002:** The `is_duplicate` flag in `BountyContext` is the sole
> source of truth for duplicate status.

---

## 3. Bounty Eligibility Logic

### 3.1 Eligibility Conditions

A report is ELIGIBLE for bounty if ALL conditions are met:

1. ✅ Asset is IN_SCOPE
2. ✅ Report is NOT duplicate
3. ✅ Reporter is in the program
4. ✅ No policy violations

### 3.2 Non-Eligibility Conditions

A report is NOT_ELIGIBLE if ANY condition is met:

1. ❌ Asset is OUT_OF_SCOPE
2. ❌ Reporter is not in program
3. ❌ Policy violation detected

### 3.3 Decision Table

| Scope | Duplicate | In Program | Decision |
|-------|-----------|------------|----------|
| IN_SCOPE | No | Yes | ELIGIBLE |
| IN_SCOPE | Yes | Yes | DUPLICATE |
| IN_SCOPE | No | No | NOT_ELIGIBLE |
| OUT_OF_SCOPE | Any | Any | NOT_ELIGIBLE |

> **REQUIREMENT R-ELIG-001:** The decision table above is EXHAUSTIVE.
> No decisions may be made outside this table.

---

## 4. Human Review Requirements

### 4.1 NEEDS_REVIEW Cases

The following cases MUST return `NEEDS_REVIEW`:

1. Ambiguous scope determination
2. Edge cases not in decision table
3. Policy exceptions requested
4. Disputed duplicate status

### 4.2 Human Authority

> **REQUIREMENT R-HUMAN-001:** Any decision returning `NEEDS_REVIEW`
> MUST be escalated to human authority.
>
> **REQUIREMENT R-HUMAN-002:** AI systems CANNOT resolve `NEEDS_REVIEW`
> autonomously. Human intervention is MANDATORY.

---

## 5. Program Policy Abstraction

### 5.1 Generic Design

Phase-09 implements GENERIC policy logic, not platform-specific:

- No HackerOne-specific logic
- No Bugcrowd-specific logic
- No Intigriti-specific logic
- No platform API integrations

### 5.2 Policy Configuration

Policy rules are defined through:
- Enum values (closed, explicit)
- Dataclass fields (immutable)
- Pure functions (deterministic)

---

## 6. Deny-by-Default Everywhere

> **REQUIREMENT R-DENY-001:** The system MUST deny by default.
>
> - Unknown asset → OUT_OF_SCOPE
> - Unknown program → NOT_ELIGIBLE
> - Unknown status → NEEDS_REVIEW
>
> Implicit allow is FORBIDDEN.

---

## Requirements Traceability

| Req ID | Description | Test File |
|--------|-------------|-----------|
| R-SCOPE-001 | Deny-by-default for scope | test_scope_rules.py |
| R-DUP-001 | Duplicate returns DUPLICATE | test_duplicate_detection.py |
| R-DUP-002 | is_duplicate is source of truth | test_duplicate_detection.py |
| R-ELIG-001 | Exhaustive decision table | test_bounty_decision.py |
| R-HUMAN-001 | NEEDS_REVIEW requires human | test_human_override_required.py |
| R-HUMAN-002 | AI cannot resolve NEEDS_REVIEW | test_human_override_required.py |
| R-DENY-001 | Deny-by-default everywhere | test_scope_rules.py |

---

**END OF REQUIREMENTS**
