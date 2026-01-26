"""
Phase-31 Observation Types.

This module defines enums for runtime observation and evidence capture.

CLOSED ENUMS - No new members may be added.

THIS IS AN OBSERVATION LAYER ONLY.
IT DOES NOT EXECUTE ANYTHING.
IT DOES NOT INTERPRET ANYTHING.

CORE RULES:
- Observation is PASSIVE only
- Evidence is RAW only (never parsed)
- Any ambiguity → HALT
"""
from enum import Enum, auto


class ObservationPoint(Enum):
    """Observation points in execution loop.
    
    CLOSED ENUM - No new members may be added.
    
    Each point captures evidence at a specific state transition:
    - PRE_DISPATCH: Before INIT → DISPATCHED
    - POST_DISPATCH: After DISPATCHED → AWAITING_RESPONSE
    - PRE_EVALUATE: Before AWAITING_RESPONSE → EVALUATED
    - POST_EVALUATE: After EVALUATED → (loop or halt)
    - HALT_ENTRY: Any state → HALTED
    """
    PRE_DISPATCH = auto()
    POST_DISPATCH = auto()
    PRE_EVALUATE = auto()
    POST_EVALUATE = auto()
    HALT_ENTRY = auto()


class EvidenceType(Enum):
    """Types of evidence that can be captured.
    
    CLOSED ENUM - No new members may be added.
    
    Evidence types:
    - STATE_TRANSITION: Execution state change
    - EXECUTOR_OUTPUT: Raw executor response (untrusted)
    - TIMESTAMP_EVENT: Timed observation
    - RESOURCE_SNAPSHOT: Resource metrics (untrusted)
    - STOP_CONDITION: HALT trigger
    """
    STATE_TRANSITION = auto()
    EXECUTOR_OUTPUT = auto()
    TIMESTAMP_EVENT = auto()
    RESOURCE_SNAPSHOT = auto()
    STOP_CONDITION = auto()


class StopCondition(Enum):
    """Conditions that trigger immediate HALT.
    
    CLOSED ENUM - No new members may be added.
    
    Default behavior: If ANY condition is unknown or ambiguous → HALT
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
