# PHASE-09 DESIGN

**Phase:** Phase-09 - Bug Bounty Policy, Scope & Eligibility Logic  
**Status:** DESIGN COMPLETE  
**Date:** 2026-01-24T08:15:00-05:00  
**Authority:** Human-Authorized Governance Process

---

## 1. ENUMS

### 1.1 ScopeResult Enum

```python
from enum import Enum, auto

class ScopeResult(Enum):
    """Classification of target scope status.
    
    CLOSED ENUM - No new members may be added.
    """
    IN_SCOPE = auto()
    OUT_OF_SCOPE = auto()
```

| Member | Description | Use Case |
|--------|-------------|----------|
| `IN_SCOPE` | Target is within bounty program scope | Proceed to eligibility check |
| `OUT_OF_SCOPE` | Target is NOT within scope | Decision is NOT_ELIGIBLE |

### 1.2 BountyDecision Enum

```python
from enum import Enum, auto

class BountyDecision(Enum):
    """Final eligibility decision for a bounty submission.
    
    CLOSED ENUM - No new members may be added.
    """
    ELIGIBLE = auto()
    NOT_ELIGIBLE = auto()
    DUPLICATE = auto()
    NEEDS_REVIEW = auto()
```

| Member | Description | Human Action |
|--------|-------------|--------------|
| `ELIGIBLE` | Report qualifies for bounty | Proceed to payout |
| `NOT_ELIGIBLE` | Report does NOT qualify | Close with reason |
| `DUPLICATE` | Report duplicates existing | Close as duplicate |
| `NEEDS_REVIEW` | Requires human decision | Escalate to OPERATOR |

---

## 2. DATACLASSES

### 2.1 BountyPolicy (frozen=True)

```python
from dataclasses import dataclass

@dataclass(frozen=True)
class BountyPolicy:
    """Immutable bounty program policy definition.
    
    Defines what is in-scope and out-of-scope for a bounty program.
    """
    policy_id: str
    policy_name: str
    in_scope_assets: frozenset[str]
    excluded_assets: frozenset[str]
    accepted_vuln_types: frozenset[str]
    excluded_vuln_types: frozenset[str]
    active: bool
    require_proof_of_concept: bool
```

### 2.2 BountyContext (frozen=True)

```python
from dataclasses import dataclass
from typing import Optional

@dataclass(frozen=True)
class BountyContext:
    """Immutable context for evaluating a bounty submission.
    
    Contains all information needed to make an eligibility decision.
    """
    submission_id: str
    target_asset: str
    vulnerability_type: str
    affected_parameter: Optional[str]
    root_cause_hash: str
    researcher_id: str
    submission_timestamp: str
    has_proof_of_concept: bool
    policy: BountyPolicy
    prior_submission_hashes: frozenset[str]
```

### 2.3 BountyDecisionResult (frozen=True)

```python
from dataclasses import dataclass
from typing import Optional

@dataclass(frozen=True)
class BountyDecisionResult:
    """Immutable result of a bounty eligibility decision.
    
    Contains the decision and reasoning chain.
    """
    submission_id: str
    scope_result: ScopeResult
    is_duplicate: bool
    decision: BountyDecision
    reason_code: str
    reason_description: str
    requires_human_review: bool
    review_reason: Optional[str]
```

### 2.4 DuplicateCheckResult (frozen=True)

```python
from dataclasses import dataclass
from typing import Optional

@dataclass(frozen=True)
class DuplicateCheckResult:
    """Immutable result of duplicate detection.
    
    Contains duplicate status and matching submission if any.
    """
    is_duplicate: bool
    matching_submission_hash: Optional[str]
    match_reason: Optional[str]
```

---

## 3. EXPLICIT DECISION TABLE

### 3.1 Scope Evaluation Table

| Asset Valid | Vuln Type Valid | Not Excluded | Format Valid | → Result |
|-------------|-----------------|--------------|--------------|----------|
| ✅ | ✅ | ✅ | ✅ | **IN_SCOPE** |
| ❌ | any | any | any | OUT_OF_SCOPE |
| any | ❌ | any | any | OUT_OF_SCOPE |
| any | any | ❌ | any | OUT_OF_SCOPE |
| any | any | any | ❌ | OUT_OF_SCOPE |

### 3.2 Eligibility Decision Table

| Scope | Duplicate | POC Required | Has POC | → Decision |
|-------|-----------|--------------|---------|------------|
| IN_SCOPE | NO | NO | any | **ELIGIBLE** |
| IN_SCOPE | NO | YES | YES | **ELIGIBLE** |
| IN_SCOPE | NO | YES | NO | **NOT_ELIGIBLE** |
| IN_SCOPE | YES | any | any | **DUPLICATE** |
| OUT_OF_SCOPE | any | any | any | **NOT_ELIGIBLE** |

### 3.3 NEEDS_REVIEW Trigger Table

| Condition ID | Condition | → Action |
|--------------|-----------|----------|
| NR-001 | Asset partially matches | NEEDS_REVIEW |
| NR-002 | Unknown vulnerability type | NEEDS_REVIEW |
| NR-003 | Partial duplicate overlap | NEEDS_REVIEW |
| NR-004 | Researcher disputed prior decision | NEEDS_REVIEW |
| NR-005 | Policy unclear for this case | NEEDS_REVIEW |
| NR-006 | High severity claim | NEEDS_REVIEW |
| NR-007 | Multiple vulns in one report | NEEDS_REVIEW |
| NR-008 | Any other uncertainty | NEEDS_REVIEW |

---

## 4. FUNCTION SIGNATURES

### 4.1 Scope Evaluation

```python
def evaluate_scope(context: BountyContext) -> ScopeResult:
    """Evaluate whether submission target is in-scope.
    
    Args:
        context: Immutable submission context
        
    Returns:
        ScopeResult.IN_SCOPE if all conditions met
        ScopeResult.OUT_OF_SCOPE otherwise (deny-by-default)
    """
```

### 4.2 Duplicate Check

```python
def check_duplicate(context: BountyContext) -> DuplicateCheckResult:
    """Check if submission is a duplicate of prior submissions.
    
    Args:
        context: Immutable submission context
        
    Returns:
        DuplicateCheckResult with duplicate status and match info
    """
```

### 4.3 Requires Review Check

```python
def requires_review(context: BountyContext) -> tuple[bool, Optional[str]]:
    """Determine if submission requires human review.
    
    Args:
        context: Immutable submission context
        
    Returns:
        (True, reason) if human review required
        (False, None) if auto-decision allowed
    """
```

### 4.4 Make Decision

```python
def make_decision(context: BountyContext) -> BountyDecisionResult:
    """Make final eligibility decision for submission.
    
    Decision precedence:
    1. Check NEEDS_REVIEW triggers first
    2. Check scope (OUT_OF_SCOPE → NOT_ELIGIBLE)
    3. Check duplicate (is_duplicate → DUPLICATE)
    4. Check POC requirement
    5. Default deny
    
    Args:
        context: Immutable submission context
        
    Returns:
        BountyDecisionResult with decision and reasoning
    """
```

---

## 5. MODULE STRUCTURE

```
python/phase09_bounty/
├── __init__.py           # Exports all public types and functions
├── bounty_types.py       # ScopeResult, BountyDecision enums
├── scope_rules.py        # evaluate_scope() logic
├── bounty_context.py     # BountyContext, BountyPolicy dataclasses
├── bounty_engine.py      # BountyDecisionResult, make_decision(), check_duplicate()
└── tests/
    ├── __init__.py
    ├── test_scope_rules.py
    ├── test_bounty_decision.py
    ├── test_duplicate_detection.py
    └── test_human_review_required.py
```

---

## 6. REASON CODES

### 6.1 Eligibility Reason Codes

| Code | Description |
|------|-------------|
| `EL-001` | All conditions met, eligible for bounty |
| `NE-001` | Target asset not in scope |
| `NE-002` | Vulnerability type not accepted |
| `NE-003` | Target in exclusion list |
| `NE-004` | Missing proof of concept |
| `NE-005` | Invalid submission format |
| `NE-006` | Policy inactive |
| `DU-001` | Exact duplicate found |
| `DU-002` | Self-duplicate by same researcher |
| `RV-001` | Scope ambiguity requires review |
| `RV-002` | Novel vulnerability type |
| `RV-003` | Partial duplicate overlap |
| `RV-004` | Researcher dispute |
| `RV-005` | Policy edge case |
| `RV-006` | High severity claim |
| `RV-007` | Multiple vulnerabilities |
| `RV-008` | Unclassifiable condition |

---

## 7. INVARIANTS

### 7.1 Decision Invariants

| Invariant | Enforcement |
|-----------|-------------|
| Same input → same output | Pure functions only |
| OUT_OF_SCOPE → NOT_ELIGIBLE | Decision table enforced |
| Duplicate → DUPLICATE | Decision table enforced |
| Unknown → NEEDS_REVIEW or NOT_ELIGIBLE | Deny-by-default |
| Policy inactive → NOT_ELIGIBLE | Status check before decision |

### 7.2 Type Invariants

| Invariant | Enforcement |
|-----------|-------------|
| Enums are closed | No dynamic member addition |
| Dataclasses are frozen | `frozen=True` |
| frozenset for collections | Immutable collection types |

---

## 8. INTEGRATION POINTS

### 8.1 Prior Phase Dependencies

| Phase | Import | Use |
|-------|--------|-----|
| Phase-01 | `ActorType`, `RoleType` | For researcher/operator classification |
| Phase-02 | `Permission` | For human authority verification |

### 8.2 Forward Phase Isolation

> **ISOLATION:** Phase-09 SHALL NOT be modified by or depend on Phase-10+.
> Phase-09 is a FROZEN policy layer that future phases consume.

---

## 9. SECURITY DESIGN

### 9.1 Attack Surface

| Vector | Mitigation |
|--------|------------|
| Malformed input | Explicit validation in context creation |
| Injection | No string interpolation, no exec/eval |
| State mutation | All dataclasses frozen |
| Side effects | Pure functions only |

### 9.2 Denied Functionality

| Denied | Reason |
|--------|--------|
| Network calls | Backend-only constraint |
| File operations | No I/O in policy logic |
| Dynamic code | No exec/eval |
| Threading | Synchronous only |

---

**END OF DESIGN**
