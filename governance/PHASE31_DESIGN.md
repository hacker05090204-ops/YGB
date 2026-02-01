# PHASE-31 DESIGN

**Phase:** Phase-31 — Runtime Observation & Controlled Execution Evidence Capture  
**Type:** DESIGN-ONLY (NO CODE)  
**Version:** 1.0  
**Date:** 2026-01-25  
**Authority:** Human-Only  

---

## OVERVIEW

Phase-31 defines the **observation subsystem** that captures evidence from real execution without granting any control or authority. This document specifies the technical architecture, data structures, and integration points.

---

## ARCHITECTURAL PRINCIPLES

| Principle | Description |
|-----------|-------------|
| **Passive Observation** | Observation layer NEVER modifies execution |
| **Immutable Evidence** | All captured data is frozen at capture time |
| **Hash Chaining** | Evidence entries are cryptographically linked |
| **Deny-By-Default** | Unknown conditions → HALT |
| **Human Authority** | All interpretation requires human action |

---

## COMPONENT ARCHITECTURE

```
┌───────────────────────────────────────────────────────────────────────┐
│                        PHASE-31 OBSERVATION LAYER                      │
├───────────────────────────────────────────────────────────────────────┤
│                                                                        │
│   ┌─────────────────────┐       ┌─────────────────────┐              │
│   │  observation_types  │       │  observation_context │              │
│   │  ─────────────────  │       │  ─────────────────── │              │
│   │  ObservationPoint   │       │  EvidenceRecord      │              │
│   │  EvidenceType       │       │  ObservationContext  │              │
│   │  StopCondition      │       │  EvidenceChain       │              │
│   └─────────────────────┘       └─────────────────────┘              │
│              │                           │                            │
│              └───────────┬───────────────┘                            │
│                          ▼                                            │
│              ┌─────────────────────┐                                  │
│              │  observation_engine │                                  │
│              │  ─────────────────  │                                  │
│              │  capture_evidence() │                                  │
│              │  check_stop()       │                                  │
│              │  validate_chain()   │                                  │
│              │  attach_observer()  │                                  │
│              └─────────────────────┘                                  │
│                                                                        │
└───────────────────────────────────────────────────────────────────────┘
                                    │
                                    │ Integrates with
                                    ▼
┌───────────────────────────────────────────────────────────────────────┐
│                         FROZEN PHASES (01-30)                          │
├───────────────────────────────────────────────────────────────────────┤
│  Phase-29: ExecutionLoopState, ExecutionLoopContext                   │
│  Phase-30: ExecutorRawResponse, NormalizedExecutionResult             │
│  Phase-28: HandshakeContext, HandshakeDecision                        │
│  Phase-01: Actor, Role, constants                                     │
└───────────────────────────────────────────────────────────────────────┘
```

---

## DATA STRUCTURES

### Enums (CLOSED)

```python
class ObservationPoint(Enum):
    """Observation points in execution loop.
    
    CLOSED ENUM - No new members may be added.
    """
    PRE_DISPATCH = auto()        # Before INIT → DISPATCHED
    POST_DISPATCH = auto()       # After DISPATCHED → AWAITING_RESPONSE
    PRE_EVALUATE = auto()        # Before AWAITING_RESPONSE → EVALUATED
    POST_EVALUATE = auto()       # After EVALUATED → (loop or halt)
    HALT_ENTRY = auto()          # Any state → HALTED


class EvidenceType(Enum):
    """Types of evidence that can be captured.
    
    CLOSED ENUM - No new members may be added.
    """
    STATE_TRANSITION = auto()    # Execution state change
    EXECUTOR_OUTPUT = auto()     # Raw executor response
    TIMESTAMP_EVENT = auto()     # Timed observation
    RESOURCE_SNAPSHOT = auto()   # Resource metrics
    STOP_CONDITION = auto()      # HALT trigger


class StopCondition(Enum):
    """Conditions that trigger immediate HALT.
    
    CLOSED ENUM - No new members may be added.
    """
    MISSING_AUTHORIZATION = auto()
    EXECUTOR_NOT_REGISTERED = auto()
    ENVELOPE_HASH_MISMATCH = auto()
    CONTEXT_UNINITIALIZED = auto()
    EVIDENCE_CHAIN_BROKEN = auto()
    RESOURCE_LIMIT_EXCEEDED = auto()
    TIMESTAMP_INVALID = auto()
    PRIOR_EXECUTION_PENDING = auto()
    AMBIGUOUS_INTENT = auto()
    HUMAN_ABORT = auto()
```

---

### Dataclasses (frozen=True)

```python
@dataclass(frozen=True)
class EvidenceRecord:
    """Single immutable evidence entry.
    
    All fields captured at observation time.
    HashChain links to prior evidence.
    """
    record_id: str              # Unique identifier
    observation_point: ObservationPoint
    evidence_type: EvidenceType
    timestamp: str              # ISO-8601 format
    raw_data: bytes             # Never parsed
    prior_hash: str             # Link to previous record
    self_hash: str              # SHA-256 of this record


@dataclass(frozen=True)
class ObservationContext:
    """Context for a single observation session.
    
    Immutable once created.
    """
    session_id: str
    loop_id: str                # From Phase-29 ExecutionLoopContext
    executor_id: str
    envelope_hash: str          # Expected instruction hash
    created_at: str             # Session start time


@dataclass(frozen=True)
class EvidenceChain:
    """Append-only chain of evidence records.
    
    Immutable structure - new records create new chain.
    """
    chain_id: str
    records: tuple[EvidenceRecord, ...]  # Immutable tuple
    head_hash: str              # Hash of most recent record
    length: int                 # Number of records
```

---

## INTEGRATION POINTS

### Attachment to Phase-29 (Execution Loop)

| Phase-29 Transition | Phase-31 Observation |
|---------------------|----------------------|
| `initialize_execution_loop()` | `capture_pre_dispatch()` |
| `transition_execution_state(DISPATCHED)` | `capture_post_dispatch()` |
| `transition_execution_state(AWAITING)` | None (internal) |
| `transition_execution_state(EVALUATED)` | `capture_pre_evaluate()` |
| Loop continuation | `capture_post_evaluate()` |
| `transition_execution_state(HALTED)` | `capture_halt_entry()` |

### Attachment to Phase-30 (Response Governance)

| Phase-30 Function | Phase-31 Evidence |
|-------------------|-------------------|
| `normalize_executor_response()` | Capture raw before normalization |
| Result decision | Capture decision (ACCEPT/REJECT/ESCALATE) |

---

## ENGINE FUNCTIONS

### capture_evidence()

```python
def capture_evidence(
    context: ObservationContext,
    observation_point: ObservationPoint,
    raw_data: bytes,
    prior_chain: EvidenceChain
) -> EvidenceChain:
    """Capture evidence at observation point.
    
    Args:
        context: Observation session context
        observation_point: Where in execution loop
        raw_data: Opaque bytes (never parsed)
        prior_chain: Existing evidence chain
        
    Returns:
        NEW EvidenceChain with appended record
        
    Rules:
        - Data is never interpreted
        - Timestamp captured at function entry
        - Hash computed over all fields
        - Chain link verified before append
    """
```

### check_stop()

```python
def check_stop(
    context: ObservationContext,
    condition: StopCondition
) -> bool:
    """Check if stop condition is triggered.
    
    Args:
        context: Current observation context
        condition: Condition to check
        
    Returns:
        True if HALT should be triggered
        
    Rules:
        - Unknown condition → HALT (True)
        - Missing context → HALT (True)
        - Default is HALT
    """
```

### validate_chain()

```python
def validate_chain(
    chain: EvidenceChain
) -> bool:
    """Validate evidence chain integrity.
    
    Args:
        chain: Evidence chain to validate
        
    Returns:
        True if chain is valid, False otherwise
        
    Rules:
        - Empty chain is valid
        - Each record's prior_hash must match previous self_hash
        - Missing links → Invalid
    """
```

### attach_observer()

```python
def attach_observer(
    loop_context: ExecutionLoopContext,
    observation_context: ObservationContext
) -> ObservationContext:
    """Attach observer to execution loop.
    
    Args:
        loop_context: Phase-29 execution loop context
        observation_context: Observation session context
        
    Returns:
        Updated observation context (or HALTED if invalid)
        
    Rules:
        - Loop must be in INIT state
        - Executor IDs must match
        - Envelope hashes must match
        - Any mismatch → Return context with HALTED flag
    """
```

---

## FORBIDDEN PATTERNS

The following patterns are ABSOLUTELY FORBIDDEN in Phase-31:

| Pattern | Why Forbidden |
|---------|---------------|
| `import os` | System access |
| `import subprocess` | Process execution |
| `import socket` | Network access |
| `import asyncio` | Async control flow |
| `import playwright` | Browser control |
| `import selenium` | Browser control |
| `async def` | Async control |
| `await` | Async control |
| `exec()` | Dynamic execution |
| `eval()` | Dynamic execution |
| `import phase32` | Future phase |

---

## EVIDENCE HASH COMPUTATION

Evidence hashes are computed as follows:

```
self_hash = SHA256(
    record_id + 
    observation_point.name + 
    evidence_type.name + 
    timestamp + 
    raw_data + 
    prior_hash
)
```

All fields concatenated with null separators. Hash is hex-encoded.

---

## STOP CONDITION ENFORCEMENT

When any STOP condition is detected:

1. Capture `STOP_CONDITION` evidence with condition details
2. Force state → `HALTED`
3. Seal evidence chain
4. Return control to human

**No automatic recovery. No retries. HALT is final until human decides.**

---

## TEST DESIGN

### Unit Tests Required

| Test Category | Count |
|---------------|-------|
| Observation point capture | 5 tests (one per point) |
| Stop condition detection | 10 tests (one per condition) |
| Evidence chain validation | 4 tests |
| Hash computation | 3 tests |
| Forbidden imports | 17 tests |
| Immutability | 5 tests |
| **Total** | **44 tests minimum** |

### Mock Strategy

| Component | Mock Strategy |
|-----------|---------------|
| ExecutionLoopContext | Use real from Phase-29 |
| ExecutorRawResponse | Mock with test data |
| Timestamps | Inject deterministic values |
| Evidence storage | In-memory tuple |

---

**END OF DESIGN**
