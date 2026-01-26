"""
impl_v1 Phase-31 Observation Mirror.

NON-AUTHORITATIVE MIRROR of governance Phase-31.
Contains ONLY data structures and validation logic.

THIS MODULE HAS NO EXECUTION AUTHORITY.
THIS MODULE DOES NOT CAPTURE EVIDENCE.
THIS MODULE DOES NOT MODIFY EXECUTION.
THIS MODULE DOES NOT ATTACH OBSERVERS.

CLOSED ENUMS:
- ObservationPoint: 5 members
- EvidenceType: 5 members
- StopCondition: 10 members

FROZEN DATACLASSES:
- EvidenceRecord: 7 fields
- ObservationContext: 5 fields
- EvidenceChain: 4 fields

ENGINE FUNCTIONS (VALIDATION ONLY):
- validate_evidence_record
- validate_observation_context
- validate_chain_integrity
- is_stop_condition_met
- get_observation_state

PASSIVE OBSERVATION ONLY.
EXECUTION WAITS.
"""
from .phase31_types import (
    ObservationPoint,
    EvidenceType,
    StopCondition,
)
from .phase31_context import (
    EvidenceRecord,
    ObservationContext,
    EvidenceChain,
)
from .phase31_engine import (
    validate_evidence_record,
    validate_observation_context,
    validate_chain_integrity,
    is_stop_condition_met,
    get_observation_state,
)

__all__ = [
    # Types
    "ObservationPoint",
    "EvidenceType",
    "StopCondition",
    # Context
    "EvidenceRecord",
    "ObservationContext",
    "EvidenceChain",
    # Engine
    "validate_evidence_record",
    "validate_observation_context",
    "validate_chain_integrity",
    "is_stop_condition_met",
    "get_observation_state",
]
