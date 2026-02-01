"""
Phase-12 Evidence Types.

This module defines enums for evidence state and confidence level.

Enums:
- EvidenceState: State of evidence after evaluation
- ConfidenceLevel: Confidence level (LOW/MEDIUM/HIGH only)

CLOSED ENUMS - No new members may be added.
"""
from enum import Enum, auto


class EvidenceState(Enum):
    """State of evidence after consistency evaluation.
    
    CLOSED ENUM - No new members may be added.
    
    Members:
        RAW: Single source, unevaluated
        CONSISTENT: Multi-source, all matching
        INCONSISTENT: Multi-source, conflicts exist
        REPLAYABLE: Consistent + replay verified
        UNVERIFIED: No sources or unknown
    """
    RAW = auto()
    CONSISTENT = auto()
    INCONSISTENT = auto()
    REPLAYABLE = auto()
    UNVERIFIED = auto()


class ConfidenceLevel(Enum):
    """Confidence level for evidence.
    
    CLOSED ENUM - No new members may be added.
    
    NOTE: There is NO "CERTAIN" or "100%" level.
    HIGH is the maximum, and it requires human review.
    
    Members:
        LOW: Uncertain, needs more evidence
        MEDIUM: Consistent but not replayable
        HIGH: Consistent and replayable
    """
    LOW = auto()
    MEDIUM = auto()
    HIGH = auto()
