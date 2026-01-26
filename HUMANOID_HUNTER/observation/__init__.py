"""
HUMANOID_HUNTER Observation — Runtime Observation & Evidence Capture

Phase-31 implementation.

THIS IS AN OBSERVATION LAYER ONLY.
IT DOES NOT EXECUTE ANYTHING.
IT DOES NOT INTERPRET ANYTHING.

CORE RULES:
- Observation is PASSIVE only
- Evidence is RAW only (never parsed)
- Any ambiguity → HALT
- Humans remain final authority
"""
from .observation_types import (
    ObservationPoint,
    EvidenceType,
    StopCondition
)
from .observation_context import (
    EvidenceRecord,
    ObservationContext,
    EvidenceChain
)
from .observation_engine import (
    capture_evidence,
    check_stop,
    validate_chain,
    attach_observer,
    create_empty_chain
)

__all__ = [
    # Enums
    "ObservationPoint",
    "EvidenceType",
    "StopCondition",
    # Dataclasses
    "EvidenceRecord",
    "ObservationContext",
    "EvidenceChain",
    # Functions
    "capture_evidence",
    "check_stop",
    "validate_chain",
    "attach_observer",
    "create_empty_chain",
]
