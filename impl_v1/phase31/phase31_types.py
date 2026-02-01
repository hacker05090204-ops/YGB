"""
impl_v1 Phase-31 Observation Types.

NON-AUTHORITATIVE MIRROR of governance Phase-31.
Contains CLOSED enums only.

THIS MODULE HAS NO EXECUTION AUTHORITY.
THIS MODULE DOES NOT CAPTURE EVIDENCE.
THIS MODULE DOES NOT MODIFY EXECUTION.

CLOSED ENUMS:
- ObservationPoint: 5 members (PRE_DISPATCH, POST_DISPATCH, PRE_EVALUATE, POST_EVALUATE, HALT_ENTRY)
- EvidenceType: 5 members (STATE_TRANSITION, EXECUTOR_OUTPUT, TIMESTAMP_EVENT, RESOURCE_SNAPSHOT, STOP_CONDITION)
- StopCondition: 10 members

PASSIVE OBSERVATION ONLY.
EXECUTION WAITS.
"""
from enum import Enum, auto


class ObservationPoint(Enum):
    """Observation points in execution loop.
    
    CLOSED ENUM - Exactly 5 members. No additions permitted.
    
    Points:
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
    
    CLOSED ENUM - Exactly 5 members. No additions permitted.
    
    Types:
    - STATE_TRANSITION: Execution state change
    - EXECUTOR_OUTPUT: Raw executor response
    - TIMESTAMP_EVENT: Timed observation
    - RESOURCE_SNAPSHOT: Resource metrics
    - STOP_CONDITION: HALT trigger
    """
    STATE_TRANSITION = auto()
    EXECUTOR_OUTPUT = auto()
    TIMESTAMP_EVENT = auto()
    RESOURCE_SNAPSHOT = auto()
    STOP_CONDITION = auto()


class StopCondition(Enum):
    """Conditions that trigger immediate HALT.
    
    CLOSED ENUM - Exactly 10 members. No additions permitted.
    
    Conditions:
    - MISSING_AUTHORIZATION: No valid authorization found
    - EXECUTOR_NOT_REGISTERED: Executor is not registered
    - ENVELOPE_HASH_MISMATCH: Instruction hash mismatch
    - CONTEXT_UNINITIALIZED: Context not properly initialized
    - EVIDENCE_CHAIN_BROKEN: Evidence chain integrity failed
    - RESOURCE_LIMIT_EXCEEDED: Resource limits exceeded
    - TIMESTAMP_INVALID: Timestamp validation failed
    - PRIOR_EXECUTION_PENDING: Previous execution not completed
    - AMBIGUOUS_INTENT: Intent is ambiguous
    - HUMAN_ABORT: Human requested abort
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
