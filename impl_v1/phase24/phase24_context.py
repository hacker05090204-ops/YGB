"""
impl_v1 Phase-24 Execution Orchestration Boundary Context.

NON-AUTHORITATIVE MIRROR of governance Phase-24.
Contains FROZEN dataclasses only.

THIS MODULE HAS NO EXECUTION AUTHORITY.

ALL DATACLASSES ARE FROZEN (frozen=True):
- OrchestrationContext: 5 fields
- OrchestrationResult: 3 fields
"""
from dataclasses import dataclass
from typing import Tuple

from .phase24_types import OrchestrationState, OrchestrationViolation


@dataclass(frozen=True)
class OrchestrationContext:
    """Context for orchestration validation.
    
    Immutable once created.
    
    Attributes:
        execution_id: Unique identifier for the execution
        stages: Tuple of stage names in current order
        completed_stages: Tuple of completed stage names
        expected_order: Tuple of stage names in expected order
        created_at: Timestamp of creation (ISO-8601)
    """
    execution_id: str
    stages: Tuple[str, ...]
    completed_stages: Tuple[str, ...]
    expected_order: Tuple[str, ...]
    created_at: str


@dataclass(frozen=True)
class OrchestrationResult:
    """Result of orchestration evaluation.
    
    Immutable once created.
    
    Attributes:
        state: Final orchestration state
        violations: Tuple of violations (empty if VALIDATED)
        evaluated_at: Timestamp of evaluation (ISO-8601)
    """
    state: OrchestrationState
    violations: Tuple[OrchestrationViolation, ...]
    evaluated_at: str
