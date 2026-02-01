# PHASE-07 DESIGN

**Phase:** Phase-07 - Bug Intelligence & Knowledge Resolution Layer  
**Status:** 📋 **APPROVED**  
**Creation Date:** 2026-01-23T15:03:00-05:00  

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                       Bug Type Input                            │
│                      (string or enum)                           │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
                    ┌─────────────────┐
                    │ resolve_bug_info│
                    │ (pure function) │
                    └─────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                      BugExplanation                             │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐ │
│  │ bug_type        │  │ title_en/hi     │  │ description     │ │
│  │ (BugType)       │  │ (str)           │  │ (en/hi)         │ │
│  └─────────────────┘  └─────────────────┘  └─────────────────┘ │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐ │
│  │ impact_en/hi    │  │ steps_en/hi     │  │ cwe_id / source │ │
│  └─────────────────┘  └─────────────────┘  └─────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
```

---

## Type Definitions

### BugType Enum

```python
class BugType(Enum):
    """Closed enum for bug types."""
    XSS = "xss"
    SQLI = "sqli"
    IDOR = "idor"
    SSRF = "ssrf"
    CSRF = "csrf"
    XXE = "xxe"
    PATH_TRAVERSAL = "path_traversal"
    OPEN_REDIRECT = "open_redirect"
    RCE = "rce"
    LFI = "lfi"
    UNKNOWN = "unknown"
```

### KnowledgeSource Enum

```python
class KnowledgeSource(Enum):
    """Closed enum for knowledge sources."""
    CVE = "cve"
    CWE = "cwe"
    MANUAL = "manual"
    UNKNOWN = "unknown"
```

### BugExplanation Dataclass

```python
@dataclass(frozen=True)
class BugExplanation:
    """Frozen dataclass for bug explanations."""
    bug_type: BugType
    title_en: str
    title_hi: str
    description_en: str
    description_hi: str
    impact_en: str
    impact_hi: str
    steps_en: Tuple[str, ...]
    steps_hi: Tuple[str, ...]
    cwe_id: Optional[str]
    source: KnowledgeSource
```

---

## Knowledge Registry

Predefined explanations stored in `_KNOWLEDGE_REGISTRY`:

```python
_KNOWLEDGE_REGISTRY: Dict[BugType, BugExplanation] = {
    BugType.XSS: BugExplanation(...),
    BugType.SQLI: BugExplanation(...),
    # ... other known types
}
```

---

## Pure Function Signature

```python
def resolve_bug_info(bug_type: BugType) -> BugExplanation:
    """
    Resolve bug information from the knowledge registry.
    
    If bug_type is UNKNOWN or not in registry, returns
    a default UNKNOWN explanation.
    
    This function is PURE:
    - No side effects
    - No guessing
    - Deterministic
    """
```

### String Lookup Function

```python
def lookup_bug_type(bug_name: str) -> BugType:
    """
    Convert a string bug name to BugType enum.
    
    Returns BugType.UNKNOWN if not recognized.
    NEVER guesses - explicit mapping only.
    """
```

---

## File Structure

```
python/phase07_knowledge/
├── __init__.py           # Module exports
├── bug_types.py          # BugType enum
├── knowledge_sources.py  # KnowledgeSource enum
├── explanations.py       # BugExplanation dataclass + registry
├── resolver.py           # resolve_bug_info() function
└── tests/
    ├── __init__.py
    ├── test_bug_types.py
    ├── test_knowledge_sources.py
    ├── test_explanations.py
    └── test_resolver.py
```

---

## No Guessing Implementation

```python
def lookup_bug_type(bug_name: str) -> BugType:
    """NEVER guesses - explicit mapping only."""
    _NAME_TO_TYPE = {
        "xss": BugType.XSS,
        "sqli": BugType.SQLI,
        # ... explicit mappings only
    }
    return _NAME_TO_TYPE.get(bug_name.lower(), BugType.UNKNOWN)
```

---

## Dependencies

### Allowed Imports

- `enum.Enum`
- `dataclasses.dataclass`
- `typing.Optional, Tuple, Dict`

### Forbidden Imports

- `import os`
- `import subprocess`
- `import socket`
- `import requests`
- `import selenium`
- `import phase08` or later

---

**END OF DESIGN**
