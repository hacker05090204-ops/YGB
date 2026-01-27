# Phase-39: Parallel Execution Governor - Arbitration Engine
# GOVERNANCE LAYER ONLY - No threading/multiprocessing
# Implements deterministic conflict resolution

"""
Phase-39 Parallel Arbitration Engine

Implements deterministic conflict detection and resolution:
- Resource contention detection
- Conflict arbitration
- Scheduling decisions

NO THREADING/MULTIPROCESSING - PURE DETERMINISTIC LOGIC
"""

import uuid
from datetime import datetime
from typing import Optional, List, Dict

from .parallel_types import (
    ExecutionRequest,
    SchedulingResult,
    ConflictDetectionResult,
    ArbitrationResult,
    ParallelAuditEntry,
    ExecutorState,
    ExecutorPriority,
    ParallelDecision,
    IsolationLevel,
    ArbitrationType,
    ConflictType,
    LifecycleEvent,
)


# =============================================================================
# CONSTANTS
# =============================================================================

MAX_CONCURRENT_EXECUTORS = 4
MAX_QUEUE_DEPTH = 10


# =============================================================================
# CONFLICT DETECTION
# =============================================================================

def detect_conflict(
    request: ExecutionRequest,
    pending_requests: List[ExecutionRequest],
    running_executors: List[str],
) -> ConflictDetectionResult:
    """
    Detect conflicts between a request and existing state.
    
    Conflict Rules:
    - Same requester_id with active request → RESOURCE_CONTENTION
    - Same executor_type in same context → TARGET_OVERLAP
    - NONE isolation → Capability conflict (forbidden)
    """
    
    # Check forbidden isolation
    if request.isolation_level == IsolationLevel.NONE:
        return ConflictDetectionResult(
            has_conflict=True,
            conflict_type=ConflictType.CAPABILITY_CONFLICT,
            conflicting_request_id=None,
            description="NONE isolation level is forbidden"
        )
    
    # Check against pending requests
    for pending in pending_requests:
        if pending.request_id == request.request_id:
            continue
            
        # Same requester with active request
        if (pending.requester_id == request.requester_id and
            pending.context_hash == request.context_hash):
            return ConflictDetectionResult(
                has_conflict=True,
                conflict_type=ConflictType.RESOURCE_CONTENTION,
                conflicting_request_id=pending.request_id,
                description="Requester already has pending request in this context"
            )
    
    # Check capacity
    if len(running_executors) >= MAX_CONCURRENT_EXECUTORS:
        return ConflictDetectionResult(
            has_conflict=True,
            conflict_type=ConflictType.RESOURCE_CONTENTION,
            conflicting_request_id=None,
            description="Maximum concurrent executors reached"
        )
    
    # No conflict
    return ConflictDetectionResult(
        has_conflict=False,
        conflict_type=None,
        conflicting_request_id=None,
        description="No conflict detected"
    )


# =============================================================================
# ARBITRATION
# =============================================================================

def arbitrate_conflict(
    conflict: ConflictDetectionResult,
    request: ExecutionRequest,
    conflicting_requests: List[ExecutionRequest],
) -> ArbitrationResult:
    """
    Resolve conflicts deterministically.
    
    Arbitration Rules:
    - RESOURCE_CONTENTION → FIRST_REGISTERED wins
    - TARGET_OVERLAP → SERIALIZE
    - CAPABILITY_CONFLICT → DENY_ALL
    - AUTHORITY_DISPUTE → ESCALATE_HUMAN
    - UNKNOWN → DENY_ALL
    """
    
    if not conflict.has_conflict:
        return ArbitrationResult(
            arbitration_type=ArbitrationType.MERGE_SAFE,
            winner_request_id=request.request_id,
            loser_request_ids=(),
            reason="No conflict to arbitrate"
        )
    
    if conflict.conflict_type == ConflictType.RESOURCE_CONTENTION:
        # First registered wins
        return ArbitrationResult(
            arbitration_type=ArbitrationType.FIRST_REGISTERED,
            winner_request_id=conflict.conflicting_request_id,
            loser_request_ids=(request.request_id,),
            reason="Resource contention: first registered wins"
        )
    
    if conflict.conflict_type == ConflictType.TARGET_OVERLAP:
        return ArbitrationResult(
            arbitration_type=ArbitrationType.SERIALIZE,
            winner_request_id=None,
            loser_request_ids=(request.request_id,),
            reason="Target overlap: serialize execution"
        )
    
    if conflict.conflict_type == ConflictType.CAPABILITY_CONFLICT:
        all_ids = [request.request_id] + [r.request_id for r in conflicting_requests]
        return ArbitrationResult(
            arbitration_type=ArbitrationType.DENY_ALL,
            winner_request_id=None,
            loser_request_ids=tuple(all_ids),
            reason="Capability conflict: all denied"
        )
    
    if conflict.conflict_type == ConflictType.AUTHORITY_DISPUTE:
        return ArbitrationResult(
            arbitration_type=ArbitrationType.ESCALATE_HUMAN,
            winner_request_id=None,
            loser_request_ids=(),
            reason="Authority dispute: escalate to human"
        )
    
    # UNKNOWN or others → DENY_ALL
    return ArbitrationResult(
        arbitration_type=ArbitrationType.DENY_ALL,
        winner_request_id=None,
        loser_request_ids=(request.request_id,),
        reason="Unknown conflict type: deny by default"
    )


# =============================================================================
# SCHEDULING DECISION
# =============================================================================

def make_scheduling_decision(
    request: ExecutionRequest,
    pending_requests: List[ExecutionRequest] = None,
    running_executors: List[str] = None,
    queue_depth: int = 0,
    human_approved: Optional[bool] = None,
) -> SchedulingResult:
    """
    Make a scheduling decision for an execution request.
    
    Decision Flow:
    1. Check forbidden isolation (NONE → DENY)
    2. Detect conflicts
    3. Apply arbitration
    4. Return decision
    """
    pending_requests = pending_requests or []
    running_executors = running_executors or []
    
    # Step 1: Check forbidden isolation
    if request.isolation_level == IsolationLevel.NONE:
        return SchedulingResult(
            request_id=request.request_id,
            decision=ParallelDecision.DENY,
            reason_code="FORBIDDEN_ISOLATION",
            executor_id="",
            queue_position=-1,
            estimated_wait_seconds=0,
        )
    
    # Step 2: Check queue depth
    if queue_depth >= MAX_QUEUE_DEPTH:
        return SchedulingResult(
            request_id=request.request_id,
            decision=ParallelDecision.DENY,
            reason_code="QUEUE_FULL",
            executor_id="",
            queue_position=-1,
            estimated_wait_seconds=0,
        )
    
    # Step 3: Detect conflicts
    conflict = detect_conflict(request, pending_requests, running_executors)
    
    if conflict.has_conflict:
        # Apply arbitration
        arbitration = arbitrate_conflict(conflict, request, pending_requests)
        
        if arbitration.arbitration_type == ArbitrationType.DENY_ALL:
            return SchedulingResult(
                request_id=request.request_id,
                decision=ParallelDecision.DENY,
                reason_code=conflict.conflict_type.value if conflict.conflict_type else "CONFLICT",
                executor_id="",
                queue_position=-1,
                estimated_wait_seconds=0,
            )
        
        if arbitration.arbitration_type == ArbitrationType.FIRST_REGISTERED:
            if request.request_id not in arbitration.loser_request_ids:
                # This request wins, but still needs to queue
                return SchedulingResult(
                    request_id=request.request_id,
                    decision=ParallelDecision.QUEUE,
                    reason_code="WINNER_QUEUED",
                    executor_id="",
                    queue_position=queue_depth + 1,
                    estimated_wait_seconds=60,
                )
            else:
                return SchedulingResult(
                    request_id=request.request_id,
                    decision=ParallelDecision.DENY,
                    reason_code="LOST_ARBITRATION",
                    executor_id="",
                    queue_position=-1,
                    estimated_wait_seconds=0,
                )
        
        if arbitration.arbitration_type == ArbitrationType.SERIALIZE:
            return SchedulingResult(
                request_id=request.request_id,
                decision=ParallelDecision.SERIALIZE,
                reason_code="SERIALIZED",
                executor_id="",
                queue_position=queue_depth + 1,
                estimated_wait_seconds=120,
            )
        
        if arbitration.arbitration_type == ArbitrationType.ESCALATE_HUMAN:
            if human_approved is True:
                return SchedulingResult(
                    request_id=request.request_id,
                    decision=ParallelDecision.ALLOW,
                    reason_code="HUMAN_APPROVED",
                    executor_id=f"EXEC-{uuid.uuid4().hex[:12].upper()}",
                    queue_position=0,
                    estimated_wait_seconds=0,
                )
            elif human_approved is False:
                return SchedulingResult(
                    request_id=request.request_id,
                    decision=ParallelDecision.DENY,
                    reason_code="HUMAN_DENIED",
                    executor_id="",
                    queue_position=-1,
                    estimated_wait_seconds=0,
                )
            else:
                return SchedulingResult(
                    request_id=request.request_id,
                    decision=ParallelDecision.ESCALATE,
                    reason_code="ESCALATE_REQUIRED",
                    executor_id="",
                    queue_position=-1,
                    estimated_wait_seconds=0,
                )
    
    # Step 4: No conflict, check capacity
    if len(running_executors) >= MAX_CONCURRENT_EXECUTORS:
        return SchedulingResult(
            request_id=request.request_id,
            decision=ParallelDecision.QUEUE,
            reason_code="CAPACITY_LIMITED",
            executor_id="",
            queue_position=queue_depth + 1,
            estimated_wait_seconds=30,
        )
    
    # Step 5: Allow execution
    return SchedulingResult(
        request_id=request.request_id,
        decision=ParallelDecision.ALLOW,
        reason_code="VALIDATED",
        executor_id=f"EXEC-{uuid.uuid4().hex[:12].upper()}",
        queue_position=0,
        estimated_wait_seconds=0,
    )


# =============================================================================
# AUDIT LOGGING
# =============================================================================

def create_parallel_audit_entry(
    request: ExecutionRequest,
    event: LifecycleEvent,
    decision: ParallelDecision,
    reason_code: str,
    executor_id: str = "",
) -> ParallelAuditEntry:
    """Create an audit entry for a parallel execution event."""
    return ParallelAuditEntry(
        audit_id=f"PAUD-{uuid.uuid4().hex[:16].upper()}",
        event=event,
        request_id=request.request_id,
        executor_id=executor_id,
        decision=decision,
        reason_code=reason_code,
        timestamp=datetime.utcnow().isoformat() + "Z",
    )
