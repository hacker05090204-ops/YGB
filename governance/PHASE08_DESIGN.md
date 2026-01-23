# PHASE-08 DESIGN

**Phase:** Phase-08 - Evidence & Explanation Orchestration Layer  
**Status:** 📋 **APPROVED**  
**Creation Date:** 2026-01-23T15:18:00-05:00  

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                         Inputs                                  │
│  ┌─────────────────┐  ┌─────────────────┐                       │
│  │ DecisionResult  │  │ BugExplanation  │                       │
│  │ (Phase-06)      │  │ (Phase-07)      │                       │
│  └─────────────────┘  └─────────────────┘                       │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
                    ┌─────────────────┐
                    │ compose_narrative│
                    │ (pure function) │
                    └─────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                    EvidenceNarrative                            │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐ │
│  │ step            │  │ decision        │  │ bug_type        │ │
│  │ (EvidenceStep)  │  │ (FinalDecision) │  │ (BugType)       │ │
│  └─────────────────┘  └─────────────────┘  └─────────────────┘ │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐ │
│  │ title_en/hi     │  │ summary_en/hi   │  │ recommend_en/hi │ │
│  └─────────────────┘  └─────────────────┘  └─────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
```

---

## Type Definitions

### EvidenceStep Enum

```python
class EvidenceStep(Enum):
    """Closed enum for evidence workflow steps."""
    DISCOVERY = "discovery"
    VALIDATION = "validation"
    DECISION = "decision"
    EXPLANATION = "explanation"
    RECOMMENDATION = "recommendation"
```

### EvidenceNarrative Dataclass

```python
@dataclass(frozen=True)
class EvidenceNarrative:
    """Frozen dataclass for evidence narratives."""
    step: EvidenceStep
    decision: FinalDecision
    bug_type: BugType
    title_en: str
    title_hi: str
    summary_en: str
    summary_hi: str
    recommendation_en: str
    recommendation_hi: str
```

---

## Narrative Templates

| Decision | Template (EN) | Template (HI) |
|----------|---------------|---------------|
| ALLOW | "Allowed: {bug_title}" | "अनुमति: {bug_title}" |
| DENY | "Denied: {bug_title}" | "अस्वीकृत: {bug_title}" |
| ESCALATE | "Escalate: {bug_title}" | "समीक्षा: {bug_title}" |

---

## Pure Function Signatures

```python
def compose_narrative(
    decision_result: DecisionResult,
    bug_explanation: BugExplanation
) -> EvidenceNarrative:
    """
    Compose a narrative from decision and knowledge.
    
    This function is PURE:
    - No side effects
    - No guessing
    - Deterministic
    """

def get_recommendation(
    decision: FinalDecision,
    bug_type: BugType
) -> Tuple[str, str]:
    """
    Get recommendation text in (English, Hindi).
    Returns explicit recommendations based on decision.
    """
```

---

## File Structure

```
python/phase08_evidence/
├── __init__.py           # Module exports
├── evidence_steps.py     # EvidenceStep enum
├── narrative.py          # EvidenceNarrative dataclass
├── composer.py           # compose_narrative() function
└── tests/
    ├── __init__.py
    ├── test_evidence_steps.py
    ├── test_narrative.py
    └── test_composer.py
```

---

## Dependencies

### Required Imports

```python
from python.phase06_decision.decision_types import FinalDecision
from python.phase06_decision.decision_result import DecisionResult
from python.phase07_knowledge.bug_types import BugType
from python.phase07_knowledge.explanations import BugExplanation
```

### Forbidden Imports

- `import os`
- `import subprocess`
- `import socket`
- `import requests`
- `import asyncio`
- `import threading`
- `import phase09` or later

---

**END OF DESIGN**
