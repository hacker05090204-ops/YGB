# PHASE-09 DESIGN

**Document Type:** Technical Design Specification  
**Phase:** 09 — Bug Bounty Policy, Scope & Eligibility Logic  
**Date:** 2026-01-24  
**Status:** APPROVED  
**Authority:** Human-Only  

---

## 1. Enums

### 1.1 BountyDecision

```python
class BountyDecision(Enum):
    """Final bounty eligibility decision."""
    ELIGIBLE = "eligible"
    NOT_ELIGIBLE = "not_eligible"
    DUPLICATE = "duplicate"
    NEEDS_REVIEW = "needs_review"
```

| Value | Description |
|-------|-------------|
| `ELIGIBLE` | Report qualifies for bounty |
| `NOT_ELIGIBLE` | Report does not qualify |
| `DUPLICATE` | Report duplicates existing |
| `NEEDS_REVIEW` | Human review required |

### 1.2 ScopeResult

```python
class ScopeResult(Enum):
    """Result of scope check."""
    IN_SCOPE = "in_scope"
    OUT_OF_SCOPE = "out_of_scope"
```

### 1.3 AssetType

```python
class AssetType(Enum):
    """Type of asset being reported."""
    WEB_APP = "web_app"
    API = "api"
    MOBILE = "mobile"
    INFRASTRUCTURE = "infrastructure"
    OUT_OF_PROGRAM = "out_of_program"
    UNKNOWN = "unknown"
```

---

## 2. Dataclasses

### 2.1 BountyContext

```python
@dataclass(frozen=True)
class BountyContext:
    """Immutable context for bounty evaluation."""
    report_id: str
    asset_type: AssetType
    vulnerability_type: str
    is_duplicate: bool
    is_in_program: bool
```

| Field | Type | Description |
|-------|------|-------------|
| `report_id` | str | Unique report identifier |
| `asset_type` | AssetType | Type of asset |
| `vulnerability_type` | str | Vulnerability classification |
| `is_duplicate` | bool | Whether this is a duplicate |
| `is_in_program` | bool | Whether reporter is in program |

### 2.2 BountyDecisionResult

```python
@dataclass(frozen=True)
class BountyDecisionResult:
    """Immutable result of bounty evaluation."""
    context: BountyContext
    scope_result: ScopeResult
    decision: BountyDecision
    requires_human_review: bool
    reason: str
```

| Field | Type | Description |
|-------|------|-------------|
| `context` | BountyContext | Original evaluation context |
| `scope_result` | ScopeResult | Scope determination |
| `decision` | BountyDecision | Final decision |
| `requires_human_review` | bool | True if human needed |
| `reason` | str | Human-readable reason |

---

## 3. Functions

### 3.1 check_scope

```python
def check_scope(asset_type: AssetType) -> ScopeResult:
    """Check if asset type is in scope."""
```

**Decision Table:**

| Input | Output |
|-------|--------|
| `WEB_APP` | `IN_SCOPE` |
| `API` | `IN_SCOPE` |
| `MOBILE` | `IN_SCOPE` |
| `INFRASTRUCTURE` | `OUT_OF_SCOPE` |
| `OUT_OF_PROGRAM` | `OUT_OF_SCOPE` |
| `UNKNOWN` | `OUT_OF_SCOPE` |

### 3.2 evaluate_bounty

```python
def evaluate_bounty(context: BountyContext) -> BountyDecisionResult:
    """Evaluate bounty eligibility."""
```

**Decision Logic:**

```
1. scope = check_scope(context.asset_type)
2. IF scope == OUT_OF_SCOPE:
      RETURN NOT_ELIGIBLE, reason="Asset out of scope"
3. IF context.is_duplicate:
      RETURN DUPLICATE, reason="Duplicate report"
4. IF NOT context.is_in_program:
      RETURN NOT_ELIGIBLE, reason="Reporter not in program"
5. RETURN ELIGIBLE, reason="All conditions met"
```

---

## 4. Explicit Decision Table

This is the COMPLETE decision table. No implicit logic allowed.

| # | Asset Scope | Is Duplicate | In Program | Decision | Reason |
|---|-------------|--------------|------------|----------|--------|
| 1 | OUT_OF_SCOPE | Any | Any | NOT_ELIGIBLE | Asset out of scope |
| 2 | IN_SCOPE | True | Any | DUPLICATE | Duplicate report |
| 3 | IN_SCOPE | False | False | NOT_ELIGIBLE | Reporter not in program |
| 4 | IN_SCOPE | False | True | ELIGIBLE | All conditions met |

---

## 5. Module Structure

```
python/phase09_bounty/
├── __init__.py           # Public exports
├── bounty_types.py       # Enums (BountyDecision, ScopeResult, AssetType)
├── bounty_context.py     # Dataclasses (BountyContext, BountyDecisionResult)
├── scope_rules.py        # check_scope function
├── bounty_engine.py      # evaluate_bounty function
└── tests/
    ├── __init__.py
    ├── test_scope_rules.py
    ├── test_bounty_decision.py
    ├── test_duplicate_detection.py
    └── test_human_override_required.py
```

---

## 6. Immutability Constraints

1. **All dataclasses MUST use `frozen=True`**
2. **All enums are CLOSED** — no dynamic members
3. **All functions are PURE** — no side effects
4. **No mutable state** — anywhere in the module

---

## 7. Deny-by-Default Implementation

```python
# In scope_rules.py
IN_SCOPE_ASSETS: frozenset = frozenset({
    AssetType.WEB_APP,
    AssetType.API,
    AssetType.MOBILE,
})

def check_scope(asset_type: AssetType) -> ScopeResult:
    if asset_type in IN_SCOPE_ASSETS:
        return ScopeResult.IN_SCOPE
    return ScopeResult.OUT_OF_SCOPE  # Deny-by-default
```

---

**END OF DESIGN**
