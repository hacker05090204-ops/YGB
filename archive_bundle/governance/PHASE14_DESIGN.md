# PHASE-14 DESIGN

**Phase:** Phase-14 - Backend Connector & Integration Verification Layer  
**Status:** DESIGN COMPLETE  
**Date:** 2026-01-25T04:50:00-05:00  

---

## 1. ENUMS

### 1.1 ConnectorRequestType Enum

```python
from enum import Enum, auto

class ConnectorRequestType(Enum):
    """Type of connector request.
    
    CLOSED ENUM - No new members may be added.
    """
    STATUS_CHECK = auto()      # Check current status
    READINESS_CHECK = auto()   # Check browser readiness
    FULL_EVALUATION = auto()   # Full pipeline evaluation
```

---

## 2. DATACLASSES

### 2.1 ConnectorInput (frozen=True)

```python
@dataclass(frozen=True)
class ConnectorInput:
    """Immutable input for connector.
    
    Attributes:
        bug_id: Unique bug identifier
        target_id: Target being evaluated
        request_type: Type of request
        timestamp: ISO timestamp of request
        handoff_decision: From Phase-13 (optional)
    """
    bug_id: str
    target_id: str
    request_type: ConnectorRequestType
    timestamp: str
    handoff_decision: Optional[HandoffDecision] = None
```

### 2.2 ConnectorOutput (frozen=True)

```python
@dataclass(frozen=True)
class ConnectorOutput:
    """Immutable output from connector.
    
    All fields are READ-ONLY pass-through from backend phases.
    
    Attributes:
        bug_id: Bug identifier (pass-through)
        target_id: Target identifier (pass-through)
        confidence: From Phase-12 (read-only)
        evidence_state: From Phase-12 (read-only)
        readiness: From Phase-13 (read-only)
        human_presence: From Phase-13 (read-only)
        can_proceed: From Phase-13 (pass-through)
        is_blocked: From Phase-13 (pass-through)
        blockers: Active blockers list
        reason_code: Machine-readable reason
        reason_description: Human-readable reason
    """
    bug_id: str
    target_id: str
    confidence: ConfidenceLevel
    evidence_state: EvidenceState
    readiness: ReadinessState
    human_presence: HumanPresence
    can_proceed: bool
    is_blocked: bool
    blockers: tuple[str, ...]
    reason_code: str
    reason_description: str
```

### 2.3 ConnectorResult (frozen=True)

```python
@dataclass(frozen=True)
class ConnectorResult:
    """Immutable result container.
    
    Attributes:
        input: Original input (read-only)
        output: Connector output (read-only)
        success: Whether pipeline succeeded
        error_code: Error code if failed
        error_description: Error description if failed
    """
    input: ConnectorInput
    output: ConnectorOutput
    success: bool
    error_code: Optional[str] = None
    error_description: Optional[str] = None
```

---

## 3. MAPPING TABLE

| Input Field | Source Phase | Output Field | Transformation |
|-------------|--------------|--------------|----------------|
| bug_id | Pass-through | bug_id | NONE |
| target_id | Pass-through | target_id | NONE |
| - | Phase-12 | confidence | READ-ONLY |
| - | Phase-12 | evidence_state | READ-ONLY |
| - | Phase-13 | readiness | READ-ONLY |
| - | Phase-13 | human_presence | READ-ONLY |
| - | Phase-13 | can_proceed | PASS-THROUGH |
| - | Phase-13 | is_blocked | PASS-THROUGH |
| - | Phase-13 | blockers | PASS-THROUGH |
| - | Phase-13 | reason_code | PASS-THROUGH |

**CRITICAL:** Transformation is ALWAYS NONE or READ-ONLY.
Phase-14 has NO authority to modify values.

---

## 4. FUNCTION SIGNATURES

```python
def validate_input(input: ConnectorInput) -> bool:
    """Validate input contract. No authority."""

def map_handoff_to_output(
    input: ConnectorInput,
    decision: HandoffDecision
) -> ConnectorOutput:
    """Map Phase-13 decision to output. READ-ONLY."""

def propagate_blocking(decision: HandoffDecision) -> bool:
    """Check if blocking propagates. Pass-through only."""

def create_result(
    input: ConnectorInput,
    output: ConnectorOutput,
    success: bool
) -> ConnectorResult:
    """Create result container. No modification."""
```

---

## 5. BLOCKING PROPAGATION TABLE

| HandoffDecision.is_blocked | ConnectorOutput.is_blocked |
|---------------------------|---------------------------|
| True | True |
| False | False |

| HandoffDecision.can_proceed | ConnectorOutput.can_proceed |
|----------------------------|----------------------------|
| True | True |
| False | False |

**Rule:** Phase-14 CANNOT change False to True. EVER.

---

## 6. MODULE STRUCTURE

```
python/phase14_connector/
├── __init__.py
├── connector_types.py     # Enum + dataclasses
├── connector_context.py   # Input/output containers
├── connector_engine.py    # Mapping logic (no decisions)
└── tests/
    ├── __init__.py
    ├── test_input_contracts.py
    ├── test_phase_chain_execution.py
    ├── test_blocking_propagation.py
    ├── test_no_authority.py
    └── test_deny_by_default.py
```

---

## 7. ZERO-AUTHORITY INVARIANTS

1. **No value modification:** Output values equal input values
2. **No approval authority:** Cannot set can_proceed = True if input is False
3. **No blocker removal:** Cannot remove items from blockers list
4. **No confidence upgrade:** Cannot change LOW to HIGH
5. **No readiness upgrade:** Cannot change NOT_READY to READY

---

**END OF DESIGN**
