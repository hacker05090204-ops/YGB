"""
Phase-11: Work Scheduling, Fair Distribution & Delegation Governance.

This module provides pure backend logic for work scheduling and delegation.

NO browser logic. NO execution logic. NO network access.
All dataclasses are frozen. All functions are pure.

Exports:
    - WorkSlotStatus: Enum for slot status
    - DelegationDecision: Enum for delegation result
    - WorkerLoadLevel: Enum for load classification
    - WorkerProfile: Immutable worker profile
    - SchedulingPolicy: Immutable policy definition
    - WorkTarget: Immutable target description
    - WorkAssignmentContext: Immutable assignment context
    - DelegationContext: Immutable delegation context
    - AssignmentResult: Immutable assignment result
    - assign_work: Assign work to worker
    - delegate_work: Process delegation request
    - get_worker_load: Get worker load count
    - classify_load: Classify load level
    - is_eligible_for_target: Check worker eligibility
"""
from python.phase11_scheduling.scheduling_types import (
    WorkSlotStatus,
    DelegationDecision,
    WorkerLoadLevel,
)
from python.phase11_scheduling.scheduling_context import (
    WorkerProfile,
    SchedulingPolicy,
    WorkTarget,
    WorkAssignmentContext,
    DelegationContext,
)
from python.phase11_scheduling.scheduling_engine import (
    AssignmentResult,
    assign_work,
    delegate_work,
    get_worker_load,
    classify_load,
    is_eligible_for_target,
)

__all__ = [
    "WorkSlotStatus",
    "DelegationDecision",
    "WorkerLoadLevel",
    "WorkerProfile",
    "SchedulingPolicy",
    "WorkTarget",
    "WorkAssignmentContext",
    "DelegationContext",
    "AssignmentResult",
    "assign_work",
    "delegate_work",
    "get_worker_load",
    "classify_load",
    "is_eligible_for_target",
]
