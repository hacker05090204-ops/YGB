"""
impl_v1 Phase-26 Execution Readiness Context.

NON-AUTHORITATIVE MIRROR of governance Phase-26.
Contains FROZEN dataclasses only.

THIS MODULE HAS NO EXECUTION AUTHORITY.

ALL DATACLASSES ARE FROZEN (frozen=True):
- ExecutionReadinessContext: 5 fields
- ReadinessResult: 3 fields

IMMUTABILITY GUARANTEE:
- No mutation permitted after creation
- Attempting mutation raises FrozenInstanceError
"""
from dataclasses import dataclass
from typing import Tuple

from .phase26_types import ReadinessStatus, ReadinessBlocker


@dataclass(frozen=True)
class ExecutionReadinessContext:
    """Context for evaluating execution readiness.
    
    Immutable once created.
    
    Attributes:
        authorization_ok: Whether authorization is granted
        intent_bound: Whether intent is bound to envelope
        handshake_valid: Whether handshake validation passed
        observation_valid: Whether observation data is valid
        human_decision_final: Whether human decision is finalized
    """
    authorization_ok: bool
    intent_bound: bool
    handshake_valid: bool
    observation_valid: bool
    human_decision_final: bool


@dataclass(frozen=True)
class ReadinessResult:
    """Result of readiness evaluation.
    
    Immutable once created.
    
    Attributes:
        status: Final readiness status
        blockers: Tuple of blockers (empty if READY)
        evaluated_at: Timestamp of evaluation (ISO-8601)
    """
    status: ReadinessStatus
    blockers: Tuple[ReadinessBlocker, ...]
    evaluated_at: str
