# PHASE-32 DESIGN

**Phase:** Phase-32 — Human-Mediated Execution Decision & Continuation Governance  
**Type:** DESIGN-ONLY (NO CODE)  
**Version:** 1.0  
**Date:** 2026-01-25  
**Authority:** Human-Only  

---

## OVERVIEW

Phase-32 defines the **human decision subsystem** that receives evidence from Phase-31 and presents it to humans for explicit decision commands. The system never interprets evidence or makes decisions autonomously.

---

## ARCHITECTURAL PRINCIPLES

| Principle | Description |
|-----------|-------------|
| **Human Authority** | Only humans issue decisions |
| **Explicit Commands** | No implicit or inferred actions |
| **Curated Presentation** | Evidence is filtered for safety |
| **Immutable Audit** | Every decision is logged permanently |
| **Default ABORT** | Ambiguity or timeout → ABORT |

---

## COMPONENT ARCHITECTURE

```
┌───────────────────────────────────────────────────────────────────────┐
│                        PHASE-32 DECISION LAYER                         │
├───────────────────────────────────────────────────────────────────────┤
│                                                                        │
│   ┌─────────────────────┐       ┌─────────────────────┐              │
│   │   decision_types    │       │   decision_context  │              │
│   │   ─────────────────  │       │   ─────────────────  │              │
│   │   HumanDecision     │       │   DecisionRequest   │              │
│   │   DecisionOutcome   │       │   DecisionRecord    │              │
│   │   EvidenceVisibility│       │   DecisionAudit     │              │
│   └─────────────────────┘       └─────────────────────┘              │
│              │                           │                            │
│              └───────────┬───────────────┘                            │
│                          ▼                                            │
│              ┌─────────────────────┐                                  │
│              │   decision_engine   │                                  │
│              │   ─────────────────  │                                  │
│              │   create_request()  │                                  │
│              │   present_evidence()│                                  │
│              │   accept_decision() │                                  │
│              │   record_decision() │                                  │
│              │   apply_decision()  │                                  │
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
│  Phase-30: ResponseDecision                                           │
│  Phase-31: ObservationPoint, EvidenceType, EvidenceChain              │
└───────────────────────────────────────────────────────────────────────┘
```

---

## DATA STRUCTURES

### Enums (CLOSED)

```python
class HumanDecision(Enum):
    """Human decision types.
    
    CLOSED ENUM - No new members may be added.
    """
    CONTINUE = auto()    # Proceed to next step
    RETRY = auto()       # Re-attempt same step
    ABORT = auto()       # Terminate execution
    ESCALATE = auto()    # Defer to higher authority


class DecisionOutcome(Enum):
    """Outcome of attempting to apply a decision.
    
    CLOSED ENUM - No new members may be added.
    """
    APPLIED = auto()     # Decision was applied successfully
    REJECTED = auto()    # Decision could not be applied
    PENDING = auto()     # Decision awaiting precondition
    TIMEOUT = auto()     # Decision timed out (→ ABORT)


class EvidenceVisibility(Enum):
    """Evidence visibility levels.
    
    CLOSED ENUM - No new members may be added.
    """
    VISIBLE = auto()           # Human may see
    HIDDEN = auto()            # Human must not see (default)
    OVERRIDE_REQUIRED = auto() # Requires higher authority
```

---

### Dataclasses (frozen=True)

```python
@dataclass(frozen=True)
class EvidenceSummary:
    """Curated evidence summary for human presentation.
    
    Contains ONLY safe-to-display information.
    """
    observation_point: str      # Point name, not enum
    evidence_type: str          # Type name, not enum
    timestamp: str              # ISO-8601
    chain_length: int           # Number of records
    execution_state: str        # Current loop state name
    confidence_score: float     # From Phase-30 (0.0-1.0)
    # RAW DATA IS NEVER INCLUDED


@dataclass(frozen=True)
class DecisionRequest:
    """Request for human decision.
    
    Immutable once created.
    """
    request_id: str
    session_id: str             # From Phase-31 ObservationContext
    evidence_summary: EvidenceSummary
    allowed_decisions: Tuple[HumanDecision, ...]
    created_at: str             # When request was created
    timeout_at: str             # When request will timeout
    timeout_decision: HumanDecision  # Always ABORT


@dataclass(frozen=True)
class DecisionRecord:
    """Record of a human decision.
    
    Immutable audit entry.
    """
    decision_id: str
    request_id: str             # Link to DecisionRequest
    human_id: str               # Who made the decision
    decision: HumanDecision
    reason: Optional[str]       # Required for RETRY, ESCALATE
    escalation_target: Optional[str]  # Required for ESCALATE
    timestamp: str              # When decision was made
    evidence_chain_hash: str    # Hash of evidence at decision time


@dataclass(frozen=True)
class DecisionAudit:
    """Append-only audit trail of decisions.
    
    Immutable chain.
    """
    audit_id: str
    records: Tuple[DecisionRecord, ...]
    session_id: str
    head_hash: str              # Hash of most recent record
    length: int
```

---

## ENGINE FUNCTIONS

### create_request()

```python
def create_request(
    session_id: str,
    evidence_chain: EvidenceChain,
    execution_state: ExecutionLoopState,
    confidence_score: float,
    timeout_seconds: int,
    timestamp: str
) -> DecisionRequest:
    """Create a decision request from evidence.
    
    Args:
        session_id: Observation session ID
        evidence_chain: Phase-31 evidence chain
        execution_state: Current Phase-29 state
        confidence_score: From Phase-30
        timeout_seconds: Seconds until timeout
        timestamp: Current time
        
    Returns:
        DecisionRequest for human presentation
        
    Rules:
        - Raw evidence is NEVER included
        - Only curated summary presented
        - Timeout decision is ALWAYS ABORT
    """
```

### present_evidence()

```python
def present_evidence(
    request: DecisionRequest
) -> EvidenceSummary:
    """Extract curated evidence summary for display.
    
    Args:
        request: Decision request
        
    Returns:
        EvidenceSummary safe for human viewing
        
    Rules:
        - Raw bytes NEVER exposed
        - Executor claims shown as "CLAIMED" only
        - Timestamps validated before display
    """
```

### accept_decision()

```python
def accept_decision(
    request: DecisionRequest,
    decision: HumanDecision,
    human_id: str,
    reason: Optional[str],
    escalation_target: Optional[str],
    timestamp: str
) -> DecisionRecord:
    """Accept a human decision.
    
    Args:
        request: The decision request being answered
        decision: Human's decision
        human_id: Identifier of deciding human
        reason: Required for RETRY and ESCALATE
        escalation_target: Required for ESCALATE
        timestamp: When decision was made
        
    Returns:
        DecisionRecord (or raises if invalid)
        
    Rules:
        - RETRY requires reason
        - ESCALATE requires reason AND target
        - Decision must be in allowed_decisions
    """
```

### record_decision()

```python
def record_decision(
    audit: DecisionAudit,
    record: DecisionRecord
) -> DecisionAudit:
    """Record decision in audit trail.
    
    Args:
        audit: Current audit trail
        record: Decision to record
        
    Returns:
        NEW DecisionAudit with appended record
        
    Rules:
        - Audit is append-only
        - New record hash computed
        - Returns new structure (immutable)
    """
```

### apply_decision()

```python
def apply_decision(
    record: DecisionRecord,
    current_state: ExecutionLoopState
) -> DecisionOutcome:
    """Determine if decision can be applied.
    
    Args:
        record: Decision to apply
        current_state: Current execution state
        
    Returns:
        DecisionOutcome indicating result
        
    Rules:
        - This is a PURE function
        - It does NOT execute anything
        - It only validates applicability
    """
```

---

## EVIDENCE VISIBILITY RULES

| Evidence Field | Visibility | Presentation |
|----------------|------------|--------------|
| observation_point | VISIBLE | ObservationPoint.name |
| evidence_type | VISIBLE | EvidenceType.name |
| timestamp | VISIBLE | As-is (ISO-8601) |
| chain_length | VISIBLE | Integer count |
| execution_state | VISIBLE | ExecutionLoopState.name |
| confidence_score | VISIBLE | Float 0.0-1.0 |
| raw_data | HIDDEN | NEVER displayed |
| self_hash | VISIBLE | Hex string (for verification) |
| prior_hash | VISIBLE | Hex string (for verification) |

---

## DECISION VALIDATION

| Decision | Required Fields | Allowed When |
|----------|-----------------|--------------|
| CONTINUE | human_id | State allows continuation |
| RETRY | human_id, reason | Retry count < max |
| ABORT | human_id | Always allowed |
| ESCALATE | human_id, reason, escalation_target | Escalation path exists |

---

## FORBIDDEN PATTERNS

| Pattern | Why Forbidden |
|---------|---------------|
| Auto-continue | Bypasses human authority |
| AI decision selection | Removes human agency |
| Evidence interpretation | System cannot judge |
| Silent timeout | Must ABORT explicitly |
| Retry without reason | Must justify retry |
| Modifying prior phases | Frozen by governance |

---

## TIMEOUT BEHAVIOR

```
┌────────────────────────────────────────────────────┐
│                 TIMEOUT HANDLING                    │
│                                                     │
│   Request Created                                   │
│         │                                           │
│         ▼                                           │
│   ┌─────────────┐                                   │
│   │  WAITING    │                                   │
│   │  FOR INPUT  │                                   │
│   └──────┬──────┘                                   │
│          │                                          │
│    80% timeout                                      │
│          │                                          │
│          ▼                                          │
│   ┌─────────────┐                                   │
│   │   WARNING   │ ───▶ Present warning to human    │
│   └──────┬──────┘                                   │
│          │                                          │
│   100% timeout                                      │
│          │                                          │
│          ▼                                          │
│   ┌─────────────┐                                   │
│   │    ABORT    │ ───▶ Decision = ABORT            │
│   │  (DEFAULT)  │      Reason = "TIMEOUT"          │
│   └─────────────┘                                   │
│                                                     │
│   NO SILENT CONTINUATION                            │
│   NO AUTO-RETRY                                     │
│                                                     │
└────────────────────────────────────────────────────┘
```

---

## TEST DESIGN

### Unit Tests Required

| Test Category | Count |
|---------------|-------|
| Decision types | 4 tests (one per type) |
| Decision validation | 8 tests (valid + invalid per type) |
| Evidence visibility | 6 tests |
| Timeout handling | 3 tests |
| Audit trail | 4 tests |
| Forbidden patterns | 6 tests |
| **Total** | **31+ tests minimum** |

---

**END OF DESIGN**
