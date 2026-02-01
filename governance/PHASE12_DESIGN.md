# PHASE-12 DESIGN

**Phase:** Phase-12 - Evidence Consistency, Replay & Confidence Governance  
**Status:** DESIGN COMPLETE  
**Date:** 2026-01-25T04:00:00-05:00  

---

## 1. ENUMS

### 1.1 EvidenceState Enum

```python
from enum import Enum, auto

class EvidenceState(Enum):
    """State of evidence after consistency evaluation.
    
    CLOSED ENUM - No new members may be added.
    """
    RAW = auto()           # Single source, unevaluated
    CONSISTENT = auto()    # Multi-source, all matching
    INCONSISTENT = auto()  # Multi-source, conflicts exist
    REPLAYABLE = auto()    # Consistent + replay verified
    UNVERIFIED = auto()    # No sources or unknown
```

### 1.2 ConfidenceLevel Enum

```python
from enum import Enum, auto

class ConfidenceLevel(Enum):
    """Confidence level for evidence.
    
    CLOSED ENUM - No new members may be added.
    NOTE: There is NO "CERTAIN" or "100%" level.
    """
    LOW = auto()      # Uncertain, needs more evidence
    MEDIUM = auto()   # Consistent but not replayable
    HIGH = auto()     # Consistent and replayable
```

---

## 2. DATACLASSES

### 2.1 EvidenceSource (frozen=True)

```python
@dataclass(frozen=True)
class EvidenceSource:
    """Immutable evidence source record.
    
    Attributes:
        source_id: Unique source identifier
        finding_hash: Hash of the finding data
        target_id: Target this evidence relates to
        evidence_type: Category of evidence
        timestamp: When evidence was collected
    """
    source_id: str
    finding_hash: str
    target_id: str
    evidence_type: str
    timestamp: str
```

### 2.2 EvidenceBundle (frozen=True)

```python
@dataclass(frozen=True)
class EvidenceBundle:
    """Immutable bundle of evidence sources.
    
    Attributes:
        bundle_id: Unique bundle identifier
        target_id: Target this bundle relates to
        sources: Frozen set of evidence sources
        replay_steps: Optional tuple of replay steps
    """
    bundle_id: str
    target_id: str
    sources: frozenset[EvidenceSource]
    replay_steps: tuple[str, ...] | None
```

### 2.3 ConsistencyResult (frozen=True)

```python
@dataclass(frozen=True)
class ConsistencyResult:
    """Immutable consistency check result.
    
    Attributes:
        bundle_id: Bundle that was checked
        state: Resulting evidence state
        source_count: Number of sources evaluated
        matching_count: Number of matching sources
        conflict_detected: Whether conflict exists
        reason_code: Machine-readable reason
        reason_description: Human-readable reason
    """
    bundle_id: str
    state: EvidenceState
    source_count: int
    matching_count: int
    conflict_detected: bool
    reason_code: str
    reason_description: str
```

### 2.4 ReplayReadiness (frozen=True)

```python
@dataclass(frozen=True)
class ReplayReadiness:
    """Immutable replay readiness assessment.
    
    Attributes:
        bundle_id: Bundle that was checked
        is_replayable: Whether replay is possible
        steps_complete: Whether all steps present
        all_deterministic: Whether all steps deterministic
        has_external_deps: Whether external deps exist
        reason_code: Machine-readable reason
        reason_description: Human-readable reason
    """
    bundle_id: str
    is_replayable: bool
    steps_complete: bool
    all_deterministic: bool
    has_external_deps: bool
    reason_code: str
    reason_description: str
```

### 2.5 ConfidenceAssignment (frozen=True)

```python
@dataclass(frozen=True)
class ConfidenceAssignment:
    """Immutable confidence level assignment.
    
    Attributes:
        bundle_id: Bundle that was evaluated
        level: Assigned confidence level
        consistency_state: State from consistency check
        is_replayable: From replay check
        reason_code: Machine-readable reason
        reason_description: Human-readable reason
        requires_human_review: Whether human must review
    """
    bundle_id: str
    level: ConfidenceLevel
    consistency_state: EvidenceState
    is_replayable: bool
    reason_code: str
    reason_description: str
    requires_human_review: bool
```

---

## 3. EXPLICIT DECISION TABLES

### 3.1 Consistency Decision Table

| Sources | All Match | Conflict | → State | Reason Code |
|---------|-----------|----------|---------|-------------|
| 0 | N/A | N/A | UNVERIFIED | CS-001 |
| 1 | N/A | N/A | RAW | CS-002 |
| 2+ | YES | NO | CONSISTENT | CS-003 |
| 2+ | NO | YES | INCONSISTENT | CS-004 |

### 3.2 Replay Readiness Decision Table

| Steps Present | All Deterministic | External Deps | → Replayable | Code |
|---------------|-------------------|---------------|--------------|------|
| NO | Any | Any | NO | RP-001 |
| YES | NO | Any | NO | RP-002 |
| YES | YES | YES | NO | RP-003 |
| YES | YES | NO | YES | RP-004 |

### 3.3 Confidence Assignment Decision Table

| Consistency State | Replayable | → Confidence | Code | Human Review |
|-------------------|------------|--------------|------|--------------|
| UNVERIFIED | Any | LOW | CF-001 | YES |
| RAW | NO | LOW | CF-002 | NO |
| RAW | YES | MEDIUM | CF-003 | NO |
| INCONSISTENT | Any | LOW | CF-004 | YES |
| CONSISTENT | NO | MEDIUM | CF-005 | NO |
| CONSISTENT | YES | HIGH | CF-006 | YES |
| REPLAYABLE | YES | HIGH | CF-007 | YES |

---

## 4. FUNCTION SIGNATURES

```python
def check_consistency(bundle: EvidenceBundle) -> ConsistencyResult:
    """Check consistency of evidence bundle."""

def check_replay_readiness(bundle: EvidenceBundle) -> ReplayReadiness:
    """Check if evidence bundle is replayable."""

def assign_confidence(
    consistency: ConsistencyResult,
    replay: ReplayReadiness
) -> ConfidenceAssignment:
    """Assign confidence level based on consistency and replay."""

def evaluate_evidence(bundle: EvidenceBundle) -> ConfidenceAssignment:
    """Full evaluation: consistency + replay + confidence."""

def sources_match(sources: frozenset[EvidenceSource]) -> bool:
    """Check if all sources have matching finding hashes."""
```

---

## 5. MODULE STRUCTURE

```
python/phase12_evidence/
├── __init__.py
├── evidence_types.py      # Enums
├── evidence_context.py    # Dataclasses
├── consistency_engine.py  # Consistency logic
├── confidence_engine.py   # Confidence assignment
└── tests/
    ├── __init__.py
    ├── test_evidence_state_enum.py
    ├── test_consistency_rules.py
    ├── test_replay_readiness.py
    ├── test_confidence_assignment.py
    └── test_deny_by_default.py
```

---

## 6. REASON CODES

| Code | Description |
|------|-------------|
| `CS-001` | No sources - unverified |
| `CS-002` | Single source - raw |
| `CS-003` | Multi-source consistent |
| `CS-004` | Multi-source inconsistent |
| `RP-001` | No replay steps present |
| `RP-002` | Non-deterministic steps |
| `RP-003` | External dependencies |
| `RP-004` | Replay ready |
| `CF-001` | Low confidence - unverified |
| `CF-002` | Low confidence - raw |
| `CF-003` | Medium confidence - replayable raw |
| `CF-004` | Low confidence - inconsistent |
| `CF-005` | Medium confidence - consistent |
| `CF-006` | High confidence - replayable |
| `CF-007` | High confidence - fully verified |

---

## 7. INVARIANTS

1. **No 100% confidence:** The system NEVER claims certainty
2. **Deny-by-default:** Unknown → UNVERIFIED, unknown → LOW
3. **Human review for HIGH:** All HIGH confidence requires human validation
4. **No inference:** Conflicting data → INCONSISTENT, never averaged
5. **Immutability:** All dataclasses are frozen

---

**END OF DESIGN**
