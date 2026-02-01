"""
Phase-11 Scheduling Engine.

Core scheduling and delegation logic.

All functions are:
- Pure (no side effects)
- Deterministic (same input → same output)
- Total (handle all possible inputs)
"""
from dataclasses import dataclass
from typing import Optional

from python.phase11_scheduling.scheduling_types import (
    WorkSlotStatus,
    DelegationDecision,
    WorkerLoadLevel,
)
from python.phase11_scheduling.scheduling_context import (
    WorkerProfile,
    WorkTarget,
    SchedulingPolicy,
    WorkAssignmentContext,
    DelegationContext,
)


@dataclass(frozen=True)
class AssignmentResult:
    """Immutable assignment decision result.

    Attributes:
        request_id: ID of the original request
        target_id: Target identifier
        status: Resulting slot status
        assigned: Whether assignment was granted
        reason_code: Machine-readable reason
        reason_description: Human-readable reason
        worker_id: Assigned worker (if any)
    """

    request_id: str
    target_id: str
    status: WorkSlotStatus
    assigned: bool
    reason_code: str
    reason_description: str
    worker_id: Optional[str]


def get_worker_load(current_assignments: frozenset[str]) -> int:
    """Get worker's current load count.

    Args:
        current_assignments: Set of current assignment IDs

    Returns:
        Number of current assignments
    """
    return len(current_assignments)


def classify_load(load: int, policy: SchedulingPolicy) -> WorkerLoadLevel:
    """Classify load into level based on policy thresholds.

    Args:
        load: Current assignment count
        policy: Scheduling policy with thresholds

    Returns:
        WorkerLoadLevel classification
    """
    if load <= policy.light_load_threshold:
        return WorkerLoadLevel.LIGHT
    elif load <= policy.medium_load_threshold:
        return WorkerLoadLevel.MEDIUM
    else:
        return WorkerLoadLevel.HEAVY


def is_eligible_for_target(worker: WorkerProfile, target: WorkTarget) -> bool:
    """Check if worker is eligible for target based on capabilities.

    Checks GPU requirements if target requires GPU.

    Args:
        worker: Worker profile
        target: Target description

    Returns:
        True if worker is eligible, False otherwise
    """
    # If target doesn't require GPU, any worker is eligible
    if not target.requires_gpu:
        return True

    # Target requires GPU
    if not worker.has_gpu:
        return False

    # Check GPU memory requirement
    if worker.gpu_memory_gb < target.min_gpu_memory_gb:
        return False

    return True


def assign_work(context: WorkAssignmentContext) -> AssignmentResult:
    """Assign work to a worker based on policy.

    Decision precedence:
    1. Check policy is active
    2. Check worker is active
    3. Check worker eligibility (GPU, etc.)
    4. Check for duplicate in team
    5. Check worker capacity
    6. Apply load-based decision

    Args:
        context: Immutable assignment context

    Returns:
        AssignmentResult with decision and reasoning
    """
    target_id = context.target.target_id
    worker = context.worker
    policy = context.policy

    # Decision 1: Check policy is active
    if not policy.active:
        return AssignmentResult(
            request_id=context.request_id,
            target_id=target_id,
            status=WorkSlotStatus.DENIED,
            assigned=False,
            reason_code="DN-004",
            reason_description="Policy is inactive",
            worker_id=None
        )

    # Decision 2: Check worker is active
    if not worker.active:
        return AssignmentResult(
            request_id=context.request_id,
            target_id=target_id,
            status=WorkSlotStatus.DENIED,
            assigned=False,
            reason_code="DN-005",
            reason_description="Worker is inactive",
            worker_id=None
        )

    # Decision 3: Check eligibility
    if not is_eligible_for_target(worker, context.target):
        return AssignmentResult(
            request_id=context.request_id,
            target_id=target_id,
            status=WorkSlotStatus.DENIED,
            assigned=False,
            reason_code="DN-001",
            reason_description="Worker not eligible for target (capability mismatch)",
            worker_id=None
        )

    # Decision 4: Check for duplicate in team
    if target_id in context.team_assignments:
        return AssignmentResult(
            request_id=context.request_id,
            target_id=target_id,
            status=WorkSlotStatus.DENIED,
            assigned=False,
            reason_code="DN-002",
            reason_description="Target already assigned to team member",
            worker_id=None
        )

    # Decision 5: Check worker capacity
    current_load = get_worker_load(context.current_assignments)
    if current_load >= worker.max_parallel:
        return AssignmentResult(
            request_id=context.request_id,
            target_id=target_id,
            status=WorkSlotStatus.DENIED,
            assigned=False,
            reason_code="DN-003",
            reason_description="Worker at maximum parallel capacity",
            worker_id=None
        )

    # Decision 6: Apply load-based decision
    load_level = classify_load(current_load, policy)

    if load_level == WorkerLoadLevel.HEAVY:
        return AssignmentResult(
            request_id=context.request_id,
            target_id=target_id,
            status=WorkSlotStatus.QUEUED,
            assigned=False,
            reason_code="AS-002",
            reason_description="Assignment queued (worker has heavy load)",
            worker_id=worker.worker_id
        )

    if load_level == WorkerLoadLevel.MEDIUM and context.target.difficulty == "high":
        return AssignmentResult(
            request_id=context.request_id,
            target_id=target_id,
            status=WorkSlotStatus.QUEUED,
            assigned=False,
            reason_code="AS-002",
            reason_description="Assignment queued (medium load + high difficulty)",
            worker_id=worker.worker_id
        )

    # Assign
    return AssignmentResult(
        request_id=context.request_id,
        target_id=target_id,
        status=WorkSlotStatus.ASSIGNED,
        assigned=True,
        reason_code="AS-001",
        reason_description="Assignment granted",
        worker_id=worker.worker_id
    )


def delegate_work(context: DelegationContext) -> DelegationDecision:
    """Process a delegation request.

    Decision precedence:
    1. HUMAN/ADMINISTRATOR always allowed
    2. SYSTEM never allowed
    3. OPERATOR on own target allowed
    4. OPERATOR on other's target requires consent

    Args:
        context: Delegation context

    Returns:
        DelegationDecision result
    """
    role = context.delegator_role.upper()

    # Decision 1: Human and Administrator always allowed
    if role in ("HUMAN", "ADMINISTRATOR"):
        return DelegationDecision.ALLOWED

    # Decision 2: System cannot delegate
    if role == "SYSTEM":
        return DelegationDecision.DENIED_SYSTEM_DELEGATION

    # Decision 3: Operator rules
    if role == "OPERATOR":
        # Operator delegating own target
        if context.target_owner_id == role or context.target_owner_id == "OPERATOR":
            return DelegationDecision.ALLOWED

        # Operator delegating other's target needs consent
        if context.explicit_consent:
            return DelegationDecision.ALLOWED
        else:
            return DelegationDecision.DENIED_NO_CONSENT

    # Unknown role, deny by default
    return DelegationDecision.DENIED_NO_CONSENT
