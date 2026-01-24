"""
Phase-11 Scheduling Context.

Defines immutable dataclasses for scheduling and delegation.
"""
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class WorkerProfile:
    """Immutable worker profile for scheduling.

    Attributes:
        worker_id: Unique worker identifier
        worker_type: standard, premium, etc.
        max_parallel: Maximum parallel assignments
        has_gpu: GPU capability flag
        gpu_memory_gb: GPU memory (if applicable)
        active: Whether worker is active
    """

    worker_id: str
    worker_type: str
    max_parallel: int
    has_gpu: bool
    gpu_memory_gb: int
    active: bool


@dataclass(frozen=True)
class SchedulingPolicy:
    """Immutable scheduling policy definition.

    Attributes:
        policy_id: Unique policy identifier
        light_load_threshold: Max assignments for "light" load
        medium_load_threshold: Max assignments for "medium" load
        allow_gpu_override: Allow GPU tasks to bypass load limits
        active: Whether policy is active
    """

    policy_id: str
    light_load_threshold: int
    medium_load_threshold: int
    allow_gpu_override: bool
    active: bool


@dataclass(frozen=True)
class WorkTarget:
    """Immutable work target description.

    Attributes:
        target_id: Unique target identifier
        difficulty: low, medium, high
        requires_gpu: Whether target requires GPU
        min_gpu_memory_gb: Minimum GPU memory required
    """

    target_id: str
    difficulty: str
    requires_gpu: bool
    min_gpu_memory_gb: int


@dataclass(frozen=True)
class WorkAssignmentContext:
    """Immutable context for assignment decisions.

    Attributes:
        request_id: Unique request identifier
        worker: Worker requesting assignment
        target: Target to be assigned
        policy: Scheduling policy to apply
        current_assignments: Worker's current assignment target IDs
        team_assignments: All team assignment target IDs
    """

    request_id: str
    worker: WorkerProfile
    target: WorkTarget
    policy: SchedulingPolicy
    current_assignments: frozenset[str]
    team_assignments: frozenset[str]


@dataclass(frozen=True)
class DelegationContext:
    """Immutable context for delegation decisions.

    Attributes:
        request_id: Unique request identifier
        delegator_role: Role of person delegating (HUMAN, OPERATOR, etc.)
        target_owner_id: Current owner of target
        new_owner_id: Intended new owner
        target_id: Target being delegated
        explicit_consent: Whether explicit consent was given
    """

    request_id: str
    delegator_role: str
    target_owner_id: str
    new_owner_id: str
    target_id: str
    explicit_consent: bool
