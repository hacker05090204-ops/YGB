"""
impl_v1 Phase-24 Execution Orchestration Boundary Types.

NON-AUTHORITATIVE MIRROR of governance Phase-24.
Contains CLOSED enums only.

THIS MODULE HAS NO EXECUTION AUTHORITY.
THIS MODULE NEVER SCHEDULES OR EXECUTES.

CLOSED ENUMS:
- OrchestrationState: 4 members (INITIALIZED, SEQUENCED, VALIDATED, BLOCKED)
- OrchestrationViolation: 4 members

ANY ORDERING VIOLATION → BLOCKED.
DEFAULT = BLOCKED.
"""
from enum import Enum, auto


class OrchestrationState(Enum):
    """State of orchestration.
    
    CLOSED ENUM - Exactly 4 members. No additions permitted.
    
    States:
    - INITIALIZED: Orchestration has been initialized
    - SEQUENCED: Stages have been sequenced
    - VALIDATED: Orchestration has been validated
    - BLOCKED: Orchestration is blocked
    """
    INITIALIZED = auto()
    SEQUENCED = auto()
    VALIDATED = auto()
    BLOCKED = auto()


class OrchestrationViolation(Enum):
    """Types of orchestration violations.
    
    CLOSED ENUM - Exactly 4 members. No additions permitted.
    
    Violations:
    - OUT_OF_ORDER: Stages are out of order
    - MISSING_DEPENDENCY: Required dependency is missing
    - DUPLICATE_STEP: Step is duplicated
    - UNKNOWN_STAGE: Stage is unknown
    """
    OUT_OF_ORDER = auto()
    MISSING_DEPENDENCY = auto()
    DUPLICATE_STEP = auto()
    UNKNOWN_STAGE = auto()
