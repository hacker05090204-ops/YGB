# PHASE-23 DESIGN

**Phase:** Phase-23 - Native Evidence Integrity & Verification Governance  
**Status:** DESIGN COMPLETE  
**Date:** 2026-01-25T16:38:00-05:00  

---

## 1. ENUMS

### 1.1 EvidenceFormat Enum

```python
class EvidenceFormat(Enum):
    """Evidence formats. CLOSED."""
    JSON = auto()
    BINARY = auto()
    SCREENSHOT = auto()
```

### 1.2 EvidenceIntegrityStatus Enum

```python
class EvidenceIntegrityStatus(Enum):
    """Evidence integrity status. CLOSED."""
    VALID = auto()
    INVALID = auto()
    TAMPERED = auto()
    REPLAY = auto()
```

### 1.3 VerificationDecision Enum

```python
class VerificationDecision(Enum):
    """Verification decisions. CLOSED."""
    ACCEPT = auto()
    REJECT = auto()
    QUARANTINE = auto()
```

---

## 2. DATACLASSES

### 2.1 EvidenceEnvelope (frozen=True)

```python
@dataclass(frozen=True)
class EvidenceEnvelope:
    evidence_id: str
    execution_id: str
    evidence_format: EvidenceFormat
    content_hash: str
    timestamp: str
    schema_version: str
    required_fields: tuple[str, ...]
```

### 2.2 EvidenceVerificationContext (frozen=True)

```python
@dataclass(frozen=True)
class EvidenceVerificationContext:
    envelope: EvidenceEnvelope
    expected_execution_id: str
    expected_format: EvidenceFormat
    known_hashes: frozenset[str]
    timestamp: str
```

### 2.3 EvidenceVerificationResult (frozen=True)

```python
@dataclass(frozen=True)
class EvidenceVerificationResult:
    decision: VerificationDecision
    integrity_status: EvidenceIntegrityStatus
    reason_code: str
    reason_description: str
```

---

## 3. VERIFICATION RULES

| Schema | Hash | Replay | ID Match | Decision |
|--------|------|--------|----------|----------|
| ✅ | ✅ | ❌ | ✅ | ACCEPT |
| ❌ | Any | Any | Any | REJECT |
| ✅ | ❌ | Any | Any | REJECT |
| ✅ | ✅ | ✅ | Any | REJECT |
| ✅ | ✅ | ❌ | ❌ | REJECT |

---

## 4. MODULE STRUCTURE

```
HUMANOID_HUNTER/
├── evidence/
│   ├── __init__.py
│   ├── evidence_types.py
│   ├── evidence_context.py
│   ├── evidence_engine.py
│   └── tests/
│       ├── __init__.py
│       ├── test_evidence_schema.py
│       ├── test_evidence_hash.py
│       ├── test_evidence_replay.py
│       ├── test_deny_by_default.py
│       └── test_no_browser_imports.py
```

---

## 5. INVARIANTS

1. **Evidence presence ≠ validity**
2. **Native reports claims, not truth**
3. **Hash mismatch → REJECT**
4. **Replay → REJECT**
5. **Unknown format → REJECT**

---

**END OF DESIGN**
