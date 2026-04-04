# PHASE-11 DESIGN

**Phase:** Phase-11 - Work Scheduling, Fair Distribution & Delegation Governance  
**Status:** DESIGN COMPLETE  
**Date:** 2026-01-24T13:25:00-05:00  

---

## 1. ENUMS

### 1.1 WorkSlotStatus Enum

```python
from enum import Enum, auto

class WorkSlotStatus(Enum):
    """Status of a work assignment slot.
    
    CLOSED ENUM - No new members may be added.
    """
    AVAILABLE = auto()
    ASSIGNED = auto()
    QUEUED = auto()
    COMPLETED = auto()
    EXPIRED = auto()
    DENIED = auto()
```

### 1.2 DelegationDecision Enum

```python
from enum import Enum, auto

class DelegationDecision(Enum):
    """Result of a delegation request.
    
    CLOSED ENUM - No new members may be added.
    """
    ALLOWED = auto()
    DENIED_NO_CONSENT = auto()
    DENIED_NOT_OWNER = auto()
    DENIED_SYSTEM_DELEGATION = auto()
    DENIED_INVALID_TARGET = auto()
```

### 1.3 WorkerLoadLevel Enum

```python
from enum import Enum, auto

class WorkerLoadLevel(Enum):
    """Classification of worker current load.
    
    CLOSED ENUM - No new members may be added.
    """
    LIGHT = auto()      # 0-2 assignments
    MEDIUM = auto()     # 3-5 assignments
    HEAVY = auto()      # 6+ assignments
```

---

## 2. DATACLASSES

### 2.1 WorkerProfile (frozen=True)

```python
@dataclass(frozen=True)
class WorkerProfile:
    """Immutable worker profile for scheduling.
    
    Attributes:
        worker_id: Unique worker identifier
        worker_type: standard, premium, etc.
        max_parallel: Maximum parallel assignments
        has_gpu: GPU capability flag
        gpu_memory_gb: GPU memory (if applicable)
        active: Whether worker is active
    """
    worker_id: str
    worker_type: str
    max_parallel: int
    has_gpu: bool
    gpu_memory_gb: int
    active: bool
```

### 2.2 SchedulingPolicy (frozen=True)

```python
@dataclass(frozen=True)
class SchedulingPolicy:
    """Immutable scheduling policy definition.
    
    Attributes:
        policy_id: Unique policy identifier
        light_load_threshold: Max assignments for "light" load
        medium_load_threshold: Max assignments for "medium" load
        allow_gpu_override: Allow GPU tasks to bypass load limits
        active: Whether policy is active
    """
    policy_id: str
    light_load_threshold: int
    medium_load_threshold: int
    allow_gpu_override: bool
    active: bool
```

### 2.3 WorkTarget (frozen=True)

```python
@dataclass(frozen=True)
class WorkTarget:
    """Immutable work target description.
    
    Attributes:
        target_id: Unique target identifier
        difficulty: low, medium, high
        requires_gpu: Whether target requires GPU
        min_gpu_memory_gb: Minimum GPU memory required
    """
    target_id: str
    difficulty: str
    requires_gpu: bool
    min_gpu_memory_gb: int
```

### 2.4 WorkAssignmentContext (frozen=True)

```python
@dataclass(frozen=True)
class WorkAssignmentContext:
    """Immutable context for assignment decisions.
    
    Attributes:
        request_id: Unique request identifier
        worker: Worker requesting assignment
        target: Target to be assigned
        policy: Scheduling policy to apply
        current_assignments: Worker's current assignment hashes
        team_assignments: All team assignment target hashes
    """
    request_id: str
    worker: WorkerProfile
    target: WorkTarget
    policy: SchedulingPolicy
    current_assignments: frozenset[str]
    team_assignments: frozenset[str]
```

### 2.5 AssignmentResult (frozen=True)

```python
@dataclass(frozen=True)
class AssignmentResult:
    """Immutable assignment decision result.
    
    Attributes:
        request_id: ID of the original request
        target_id: Target identifier
        status: Resulting slot status
        assigned: Whether assignment was granted
        reason_code: Machine-readable reason
        reason_description: Human-readable reason
        worker_id: Assigned worker (if any)
    """
    request_id: str
    target_id: str
    status: WorkSlotStatus
    assigned: bool
    reason_code: str
    reason_description: str
    worker_id: Optional[str]
```

### 2.6 DelegationContext (frozen=True)

```python
@dataclass(frozen=True)
class DelegationContext:
    """Immutable context for delegation decisions.
    
    Attributes:
        request_id: Unique request identifier
        delegator_role: Role of person delegating
        target_owner_id: Current owner of target
        target_id: Target being delegated
        explicit_consent: Whether consent was given
    """
    request_id: str
    delegator_role: str
    target_owner_id: str
    new_owner_id: str
    target_id: str
    explicit_consent: bool
```

---

## 3. EXPLICIT DECISION TABLES

### 3.1 Assignment Decision Table

| Worker Load | Capability Match | Target in Team | → Status |
|-------------|-----------------|----------------|----------|
| Any | NO | Any | DENIED |
| Any | YES | YES (duplicate) | DENIED |
| LIGHT | YES | NO | ASSIGNED |
| MEDIUM | YES | NO | ASSIGNED (if low/medium) |
| MEDIUM | YES | NO | QUEUED (if high difficulty) |
| HEAVY | YES | NO | QUEUED |

### 3.2 Delegation Decision Table

| Delegator Role | Is Owner | Has Consent | → Decision |
|----------------|----------|-------------|------------|
| HUMAN | Any | Any | ALLOWED |
| ADMINISTRATOR | Any | Any | ALLOWED |
| OPERATOR | YES | - | ALLOWED |
| OPERATOR | NO | YES | ALLOWED |
| OPERATOR | NO | NO | DENIED_NO_CONSENT |
| SYSTEM | Any | Any | DENIED_SYSTEM_DELEGATION |

### 3.3 GPU Eligibility Table

| Worker has_gpu | Target requires_gpu | Worker GPU Memory | Target Min GPU | → Eligible |
|----------------|---------------------|-------------------|----------------|------------|
| NO | YES | - | - | NO |
| YES | NO | - | - | YES |
| YES | YES | >= Min | Min | YES |
| YES | YES | < Min | Min | NO |

---

## 4. FUNCTION SIGNATURES

```python
def assign_work(context: WorkAssignmentContext) -> AssignmentResult:
    """Assign work to a worker based on policy."""

def can_assign(worker: WorkerProfile, target: WorkTarget) -> bool:
    """Check if worker can be assigned target."""

def get_worker_load(current_assignments: frozenset[str]) -> int:
    """Get worker's current load count."""

def classify_load(load: int, policy: SchedulingPolicy) -> WorkerLoadLevel:
    """Classify load into level based on policy."""

def is_eligible_for_target(worker: WorkerProfile, target: WorkTarget) -> bool:
    """Check if worker is eligible for target (GPU, etc)."""

def delegate_work(context: DelegationContext) -> DelegationDecision:
    """Process a delegation request."""
```

---

## 5. MODULE STRUCTURE

```
python/phase11_scheduling/
├── __init__.py
├── scheduling_types.py    # Enums
├── scheduling_context.py  # Dataclasses
├── scheduling_engine.py   # Functions
└── tests/
    ├── __init__.py
    ├── test_fair_distribution.py
    ├── test_parallel_limits.py
    ├── test_delegation_rules.py
    └── test_deny_by_default.py
```

---

## 6. REASON CODES

| Code | Description |
|------|-------------|
| `AS-001` | Assignment granted |
| `AS-002` | Assignment queued (worker busy) |
| `DN-001` | Denied - capability mismatch |
| `DN-002` | Denied - target already assigned |
| `DN-003` | Denied - worker at capacity |
| `DN-004` | Denied - policy inactive |
| `DN-005` | Denied - worker inactive |
| `DL-001` | Delegation allowed |
| `DL-002` | Delegation denied - no consent |
| `DL-003` | Delegation denied - not owner |
| `DL-004` | Delegation denied - system cannot delegate |

---

**END OF DESIGN**
