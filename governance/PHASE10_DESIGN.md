# PHASE-10 DESIGN

**Phase:** Phase-10 - Target Coordination & De-Duplication Authority  
**Status:** DESIGN COMPLETE  
**Date:** 2026-01-24T10:25:00-05:00  

---

## 1. ENUMS

### 1.1 WorkClaimStatus Enum

```python
from enum import Enum, auto

class WorkClaimStatus(Enum):
    """Status of a work claim on a target.
    
    CLOSED ENUM - No new members may be added.
    """
    UNCLAIMED = auto()
    CLAIMED = auto()
    RELEASED = auto()
    EXPIRED = auto()
    COMPLETED = auto()
    DENIED = auto()
```

### 1.2 ClaimAction Enum

```python
from enum import Enum, auto

class ClaimAction(Enum):
    """Actions that can be performed on claims.
    
    CLOSED ENUM - No new members may be added.
    """
    CLAIM = auto()
    RELEASE = auto()
    COMPLETE = auto()
    CHECK = auto()
```

---

## 2. DATACLASSES

### 2.1 TargetID (frozen=True)

```python
from dataclasses import dataclass

@dataclass(frozen=True)
class TargetID:
    """Immutable target identifier.
    
    Uniquely identifies a bug bounty target.
    """
    program_id: str
    asset_id: str
    vulnerability_class: str
    target_hash: str
```

### 2.2 CoordinationPolicy (frozen=True)

```python
@dataclass(frozen=True)
class CoordinationPolicy:
    """Immutable coordination policy definition.
    
    Defines claim duration and rules.
    """
    policy_id: str
    claim_duration_seconds: int
    allow_reclaim_after_expiry: bool
    active: bool
```

### 2.3 WorkClaimContext (frozen=True)

```python
@dataclass(frozen=True)
class WorkClaimContext:
    """Immutable context for coordination operations.
    
    Contains all information for claim decisions.
    """
    request_id: str
    target: TargetID
    researcher_id: str
    action: ClaimAction
    request_timestamp: str
    policy: CoordinationPolicy
    existing_claims: frozenset[str]  # claim_hashes
    claim_timestamps: dict[str, str]  # researcher_id -> timestamp
```

### 2.4 WorkClaimResult (frozen=True)

```python
@dataclass(frozen=True)
class WorkClaimResult:
    """Immutable result of a coordination operation.
    
    Contains decision and reasoning.
    """
    request_id: str
    target_hash: str
    status: WorkClaimStatus
    granted: bool
    reason_code: str
    reason_description: str
    claim_expiry: Optional[str]
    owner_id: Optional[str]
```

---

## 3. EXPLICIT ARBITRATION TABLES

### 3.1 Claim Request Table

| Target Claimed | Owner == Requester | Expired | → Result |
|----------------|-------------------|---------|----------|
| NO | N/A | N/A | **GRANTED** |
| YES | YES | NO | **DENIED** (already yours) |
| YES | YES | YES | **GRANTED** (reclaim) |
| YES | NO | NO | **DENIED** (owned by another) |
| YES | NO | YES | **GRANTED** (expired, reclaimable) |

### 3.2 Release Request Table

| Target Claimed | Owner == Requester | → Result |
|----------------|-------------------|----------|
| NO | N/A | **DENIED** (nothing to release) |
| YES | YES | **RELEASED** |
| YES | NO | **DENIED** (not your claim) |

### 3.3 Expiry Decision Table

| Current Time | Claim Time | Duration | → Status |
|--------------|------------|----------|----------|
| T | T - (D-1) | D | ACTIVE |
| T | T - D | D | EXPIRED |
| T | T - (D+1) | D | EXPIRED |

---

## 4. FUNCTION SIGNATURES

### 4.1 Target ID Creation

```python
def create_target_id(
    program_id: str,
    asset_id: str,
    vulnerability_class: str
) -> TargetID:
    """Create a unique target identifier.
    
    Args:
        program_id: Bounty program identifier
        asset_id: Target asset identifier
        vulnerability_class: Type of vulnerability
        
    Returns:
        TargetID with computed hash
    """
```

### 4.2 Claim Operations

```python
def claim_target(context: WorkClaimContext) -> WorkClaimResult:
    """Attempt to claim a target for work.
    
    Decision precedence:
    1. Validate context
    2. Check if already claimed
    3. Check expiry
    4. Grant or deny
    """

def release_claim(context: WorkClaimContext) -> WorkClaimResult:
    """Release a claim on a target.
    
    Only the owner can release.
    """

def check_claim_status(
    target_hash: str,
    existing_claims: frozenset[str],
    claim_timestamps: dict[str, str],
    current_time: str,
    policy: CoordinationPolicy
) -> WorkClaimStatus:
    """Check current claim status of a target."""
```

### 4.3 Expiry Check

```python
def is_claim_expired(
    claim_timestamp: str,
    current_time: str,
    duration_seconds: int
) -> bool:
    """Check if a claim has expired.
    
    Pure deterministic comparison.
    """
```

---

## 5. MODULE STRUCTURE

```
python/phase10_coordination/
├── __init__.py
├── coordination_types.py    # Enums: WorkClaimStatus, ClaimAction
├── coordination_context.py  # Dataclasses: TargetID, WorkClaimContext, etc.
├── coordination_engine.py   # Functions: claim_target(), release_claim(), etc.
└── tests/
    ├── __init__.py
    ├── test_coordination_types.py
    ├── test_coordination_context.py
    └── test_coordination_engine.py
```

---

## 6. REASON CODES

| Code | Description |
|------|-------------|
| `CL-001` | Claim granted successfully |
| `CL-002` | Claim granted (reclaim after expiry) |
| `DN-001` | Denied - target already claimed by you |
| `DN-002` | Denied - target claimed by another |
| `DN-003` | Denied - invalid context |
| `DN-004` | Denied - policy inactive |
| `DN-005` | Denied - nothing to release |
| `DN-006` | Denied - not your claim |
| `RL-001` | Claim released successfully |
| `EX-001` | Claim expired |

---

## 7. INVARIANTS

| Invariant | Enforcement |
|-----------|-------------|
| Same input → same output | Pure functions only |
| Expired claims reclaimable | Arbitration table |
| Owner exclusive access | Ownership check |
| Deny-by-default | Default DENIED result |

---

**END OF DESIGN**
