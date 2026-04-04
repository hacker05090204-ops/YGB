# PHASE-18 DESIGN

**Phase:** Phase-18 - Execution State & Provenance Ledger  
**Status:** DESIGN COMPLETE  
**Date:** 2026-01-25T08:35:00-05:00  

---

## 1. ENUMS

### 1.1 ExecutionState Enum

```python
class ExecutionState(Enum):
    """Execution lifecycle states. CLOSED.
    """
    REQUESTED = auto()
    ALLOWED = auto()
    ATTEMPTED = auto()
    FAILED = auto()
    COMPLETED = auto()
    ESCALATED = auto()
```

### 1.2 EvidenceStatus Enum

```python
class EvidenceStatus(Enum):
    """Evidence validation status. CLOSED.
    """
    MISSING = auto()
    LINKED = auto()
    INVALID = auto()
    VERIFIED = auto()
```

### 1.3 RetryDecision Enum

```python
class RetryDecision(Enum):
    """Retry decision values. CLOSED.
    """
    ALLOWED = auto()
    DENIED = auto()
    HUMAN_REQUIRED = auto()
```

---

## 2. DATACLASSES

### 2.1 ExecutionRecord (frozen=True)

```python
@dataclass(frozen=True)
class ExecutionRecord:
    """Immutable execution record."""
    execution_id: str
    request_id: str
    bug_id: str
    target_id: str
    created_at: str
    current_state: ExecutionState
    attempt_count: int = 0
    max_attempts: int = 3
    finalized: bool = False
```

### 2.2 EvidenceRecord (frozen=True)

```python
@dataclass(frozen=True)
class EvidenceRecord:
    """Immutable evidence record."""
    evidence_id: str
    execution_id: str
    evidence_hash: str
    evidence_status: EvidenceStatus
    linked_at: str
```

### 2.3 ExecutionLedgerEntry (frozen=True)

```python
@dataclass(frozen=True)
class ExecutionLedgerEntry:
    """Immutable ledger entry."""
    entry_id: str
    execution_id: str
    timestamp: str
    from_state: ExecutionState
    to_state: ExecutionState
    reason: str
```

### 2.4 LedgerValidationResult (frozen=True)

```python
@dataclass(frozen=True)
class LedgerValidationResult:
    """Ledger validation result."""
    is_valid: bool
    reason_code: str
    reason_description: str
```

---

## 3. STATE TRANSITION TABLE

| Current State | Target State | Condition | Decision |
|---------------|--------------|-----------|----------|
| REQUESTED | ALLOWED | Phase-16 approves | ✅ |
| REQUESTED | ESCALATED | Human required | ✅ |
| ALLOWED | ATTEMPTED | Sent to executor | ✅ |
| ATTEMPTED | FAILED | Error/timeout response | ✅ |
| ATTEMPTED | COMPLETED | Valid evidence | ✅ |
| ATTEMPTED | ESCALATED | Human required | ✅ |
| FAILED | ATTEMPTED | Retry allowed | ✅ |
| FAILED | ESCALATED | Max retries | ✅ |
| Any → COMPLETED | Any | N/A | ❌ DENIED |
| Any → REQUESTED | Any | N/A | ❌ DENIED |
| Unknown | Any | N/A | ❌ DENIED |

---

## 4. REPLAY PREVENTION TABLE

| Evidence Hash | Status | Decision |
|---------------|--------|----------|
| Never seen | LINKED | ✅ |
| Already linked to this execution | INVALID | ❌ |
| Already linked to other execution | DENIED (replay) | ❌ |

---

## 5. MODULE STRUCTURE

```
python/phase18_ledger/
├── __init__.py
├── ledger_types.py     # Enums
├── ledger_context.py   # Dataclasses
├── ledger_engine.py    # Core functions
└── tests/
    ├── __init__.py
    ├── test_execution_record.py
    ├── test_evidence_record.py
    ├── test_ledger_entry.py
    ├── test_deny_by_default.py
    ├── test_replay_attacks.py
    ├── test_state_transitions.py
    └── test_no_browser_imports.py
```

---

## 6. FUNCTION SIGNATURES

```python
def create_execution_record(
    request_id: str,
    bug_id: str,
    target_id: str,
    timestamp: str
) -> ExecutionRecord:
    """Create new execution record."""

def record_attempt(
    record: ExecutionRecord
) -> ExecutionRecord:
    """Record execution attempt."""

def transition_state(
    record: ExecutionRecord,
    to_state: ExecutionState,
    timestamp: str
) -> ExecutionLedgerEntry:
    """Transition execution state."""

def attach_evidence(
    execution_id: str,
    evidence_hash: str,
    timestamp: str,
    used_hashes: frozenset
) -> Tuple[EvidenceRecord, LedgerValidationResult]:
    """Attach evidence to execution."""

def validate_evidence_linkage(
    evidence: EvidenceRecord
) -> LedgerValidationResult:
    """Validate evidence is properly linked."""

def decide_retry(
    record: ExecutionRecord
) -> RetryDecision:
    """Decide if retry is allowed."""
```

---

## 7. INVARIANTS

1. **Unique IDs:** All IDs are unique
2. **Immutable records:** frozen=True
3. **No replay:** Evidence hash used once
4. **Deny-by-default:** Unknown → DENIED
5. **Deterministic:** Same input → same output

---

**END OF DESIGN**
