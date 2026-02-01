# PHASE-33 DESIGN

**Phase:** Phase-33 — Human Decision → Execution Intent Binding  
**Type:** DESIGN-ONLY (NO CODE)  
**Version:** 1.0  
**Date:** 2026-01-26  
**Authority:** Human-Only  

---

## OVERVIEW

Phase-33 defines the **intent binding subsystem** that receives human decisions from Phase-32 and produces immutable execution intents. Intent is DATA, not action. The system binds, never decides.

---

## ARCHITECTURAL PRINCIPLES

| Principle | Description |
|-----------|-------------|
| **Immutability** | Intent cannot be modified after creation |
| **One-to-One** | Each decision binds to exactly one intent |
| **Auditable** | Every binding is logged permanently |
| **Revocable** | Intent can be revoked before execution only |
| **Deny-by-Default** | Any invalid input rejects binding |

---

## COMPONENT ARCHITECTURE

```
┌───────────────────────────────────────────────────────────────────────┐
│                        PHASE-33 INTENT LAYER                           │
├───────────────────────────────────────────────────────────────────────┤
│                                                                        │
│   ┌─────────────────────┐       ┌─────────────────────┐              │
│   │   intent_types      │       │   intent_context    │              │
│   │   ─────────────────  │       │   ─────────────────  │              │
│   │   IntentStatus      │       │   ExecutionIntent   │              │
│   │   BindingResult     │       │   IntentRevocation  │              │
│   │                     │       │   IntentAudit       │              │
│   └─────────────────────┘       └─────────────────────┘              │
│              │                           │                            │
│              └───────────┬───────────────┘                            │
│                          ▼                                            │
│              ┌─────────────────────┐                                  │
│              │   intent_engine     │                                  │
│              │   ─────────────────  │                                  │
│              │   bind_decision()   │                                  │
│              │   validate_intent() │                                  │
│              │   revoke_intent()   │                                  │
│              │   record_intent()   │                                  │
│              │   create_audit()    │                                  │
│              └─────────────────────┘                                  │
│                                                                        │
└───────────────────────────────────────────────────────────────────────┘
                                    │
                                    │ Imports from
                                    ▼
┌───────────────────────────────────────────────────────────────────────┐
│                         FROZEN PHASES                                  │
├───────────────────────────────────────────────────────────────────────┤
│  Phase-01: Authority, Constants                                       │
│  Phase-29: ExecutionLoopState                                         │
│  Phase-31: EvidenceChain (hash reference only)                        │
│  Phase-32: DecisionRecord, HumanDecision                              │
└───────────────────────────────────────────────────────────────────────┘
```

---

## DATA STRUCTURES

### Enums (CLOSED)

```python
class IntentStatus(Enum):
    """Intent lifecycle status.
    
    CLOSED ENUM - No new members may be added.
    """
    PENDING = auto()     # Bound but not executed
    EXECUTED = auto()    # Execution completed
    REVOKED = auto()     # Revoked before execution
    EXPIRED = auto()     # Timeout without execution


class BindingResult(Enum):
    """Result of binding attempt.
    
    CLOSED ENUM - No new members may be added.
    """
    SUCCESS = auto()     # Binding successful
    INVALID_DECISION = auto()  # Decision validation failed
    MISSING_FIELD = auto()     # Required field missing
    DUPLICATE = auto()         # Intent already exists
    REJECTED = auto()          # Binding rejected
```

---

### Dataclasses (frozen=True)

```python
@dataclass(frozen=True)
class ExecutionIntent:
    """Immutable execution intent bound to a human decision.
    
    All fields are frozen after creation.
    """
    intent_id: str                # INTENT-{uuid_hex}
    decision_id: str              # Reference to DecisionRecord
    decision_type: HumanDecision  # CONTINUE/RETRY/ABORT/ESCALATE
    evidence_chain_hash: str      # Frozen evidence state
    session_id: str               # Observation session
    execution_state: str          # ExecutionLoopState at binding
    created_at: str               # ISO-8601 timestamp
    created_by: str               # Human who decided
    intent_hash: str              # SHA-256 of all fields


@dataclass(frozen=True)
class IntentRevocation:
    """Record of intent revocation.
    
    Immutable once created.
    """
    revocation_id: str
    intent_id: str                # Intent being revoked
    revoked_by: str               # Human who revoked
    revocation_reason: str        # Mandatory reason
    revoked_at: str               # ISO-8601 timestamp
    revocation_hash: str          # Hash of revocation


@dataclass(frozen=True)
class IntentRecord:
    """Record in intent audit trail.
    
    Either binding or revocation.
    """
    record_id: str
    record_type: str              # "BINDING" or "REVOCATION"
    intent_id: str
    timestamp: str
    prior_hash: str
    self_hash: str


@dataclass(frozen=True)
class IntentAudit:
    """Append-only intent audit trail.
    
    Immutable chain structure.
    """
    audit_id: str
    records: Tuple[IntentRecord, ...]
    session_id: str
    head_hash: str
    length: int
```

---

## ENGINE FUNCTIONS

### bind_decision()

```python
def bind_decision(
    decision_record: DecisionRecord,
    evidence_chain_hash: str,
    session_id: str,
    execution_state: str,
    timestamp: str
) -> Tuple[BindingResult, Optional[ExecutionIntent]]:
    """Bind a human decision to an execution intent.
    
    Args:
        decision_record: Phase-32 decision
        evidence_chain_hash: Phase-31 evidence hash
        session_id: Observation session ID
        execution_state: Current execution loop state
        timestamp: Binding timestamp
        
    Returns:
        (BindingResult, ExecutionIntent or None)
        
    Rules:
        - Pure function (no I/O)
        - Validates all fields
        - Computes intent_hash
        - Returns immutable intent
        - Fails on invalid input
    """
```

### validate_intent()

```python
def validate_intent(
    intent: ExecutionIntent,
    decision_record: DecisionRecord
) -> bool:
    """Validate intent matches its source decision.
    
    Args:
        intent: Intent to validate
        decision_record: Original decision
        
    Returns:
        True if valid, False otherwise
        
    Checks:
        - Decision ID matches
        - Decision type matches
        - Hash is valid
        - Not revoked (separate check)
    """
```

### revoke_intent()

```python
def revoke_intent(
    intent: ExecutionIntent,
    revoked_by: str,
    reason: str,
    timestamp: str
) -> IntentRevocation:
    """Create revocation for an intent.
    
    Args:
        intent: Intent to revoke
        revoked_by: Human revoking
        reason: Mandatory reason
        timestamp: Revocation time
        
    Returns:
        IntentRevocation record
        
    Rules:
        - Revocation is permanent
        - Reason is required
        - Creates immutable record
    """
```

### record_intent()

```python
def record_intent(
    audit: IntentAudit,
    intent: ExecutionIntent,
    record_type: str
) -> IntentAudit:
    """Record intent event in audit trail.
    
    Args:
        audit: Current audit trail
        intent: Intent to record
        record_type: "BINDING" or "REVOCATION"
        
    Returns:
        NEW IntentAudit with appended record
        
    Rules:
        - Audit is append-only
        - Hash chain maintained
        - Returns new structure
    """
```

### create_empty_audit()

```python
def create_empty_audit(session_id: str) -> IntentAudit:
    """Create empty intent audit trail.
    
    Args:
        session_id: Session identifier
        
    Returns:
        Empty IntentAudit ready for appending
    """
```

### is_intent_revoked()

```python
def is_intent_revoked(
    intent_id: str,
    audit: IntentAudit
) -> bool:
    """Check if intent has been revoked.
    
    Args:
        intent_id: Intent to check
        audit: Audit trail to search
        
    Returns:
        True if revoked, False otherwise
    """
```

---

## INTENT BINDING FLOW

```
┌────────────────────────────────────────────────────────────────┐
│                    INTENT BINDING FLOW                          │
│                                                                  │
│   DecisionRecord (Phase-32)                                     │
│         │                                                        │
│         ▼                                                        │
│   ┌─────────────┐                                               │
│   │  VALIDATE   │ ─── Invalid ──▶ BindingResult.REJECTED       │
│   │  DECISION   │                                               │
│   └──────┬──────┘                                               │
│          │ Valid                                                 │
│          ▼                                                       │
│   ┌─────────────┐                                               │
│   │   COMPUTE   │                                               │
│   │ INTENT HASH │                                               │
│   └──────┬──────┘                                               │
│          │                                                       │
│          ▼                                                       │
│   ┌─────────────┐                                               │
│   │   CREATE    │                                               │
│   │   INTENT    │ ──▶ ExecutionIntent (frozen)                  │
│   └──────┬──────┘                                               │
│          │                                                       │
│          ▼                                                       │
│   ┌─────────────┐                                               │
│   │   RECORD    │                                               │
│   │  IN AUDIT   │ ──▶ IntentAudit (updated)                     │
│   └─────────────┘                                               │
│                                                                  │
│   INTENT IS NOW:                                                 │
│   ✅ Immutable                                                  │
│   ✅ Audited                                                    │
│   ✅ Revocable (until execution)                                │
│   ⏸️ Waiting for execution phase                                │
│                                                                  │
└────────────────────────────────────────────────────────────────┘
```

---

## HASH COMPUTATION

Intent hash is computed over ALL fields (except intent_hash itself):

```python
def compute_intent_hash(
    intent_id: str,
    decision_id: str,
    decision_type: HumanDecision,
    evidence_chain_hash: str,
    session_id: str,
    execution_state: str,
    created_at: str,
    created_by: str
) -> str:
    """Compute SHA-256 hash for intent."""
    hasher = hashlib.sha256()
    hasher.update(intent_id.encode())
    hasher.update(b'\x00')
    hasher.update(decision_id.encode())
    hasher.update(b'\x00')
    hasher.update(decision_type.name.encode())
    # ... all fields ...
    return hasher.hexdigest()
```

---

## FORBIDDEN PATTERNS

| Pattern | Why Forbidden |
|---------|---------------|
| Execution logic | This phase binds, doesn't execute |
| I/O operations | Pure functions only |
| Async/await | No async patterns |
| AI decision | System binds, never decides |
| Intent modification | Intent is immutable |
| Revocation undo | Revocation is permanent |

---

## TEST DESIGN

### Unit Tests Required

| Test Category | Count |
|---------------|-------|
| Intent creation | 4+ tests |
| Binding validation | 6+ tests |
| Revocation | 4+ tests |
| Audit trail | 5+ tests |
| Hash computation | 3+ tests |
| Forbidden imports | 8+ tests |
| Immutability | 4+ tests |
| **Total** | **34+ tests minimum** |

---

**END OF DESIGN**
