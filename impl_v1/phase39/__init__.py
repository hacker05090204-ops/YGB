# Phase-39 Package Init
"""
Phase-39: Parallel Execution Governor
GOVERNANCE LAYER ONLY - No threading/multiprocessing

Exports:
- Types (enums, dataclasses)
- Arbitration engine
"""

from .parallel_types import (
    # Enums
    SchedulingAlgorithm,
    ExecutorState,
    ExecutorPriority,
    ParallelDecision,
    IsolationLevel,
    ArbitrationType,
    ConflictType,
    ResourceType,
    LifecycleEvent,
    HumanOverrideAction,
    # Dataclasses
    ResourceQuota,
    ExecutionRequest,
    SchedulingResult,
    ExecutorStatus,
    ConflictDetectionResult,
    ArbitrationResult,
    ParallelAuditEntry,
)

from .parallel_engine import (
    detect_conflict,
    arbitrate_conflict,
    make_scheduling_decision,
    create_parallel_audit_entry,
    MAX_CONCURRENT_EXECUTORS,
    MAX_QUEUE_DEPTH,
)

__all__ = [
    # Enums
    "SchedulingAlgorithm",
    "ExecutorState",
    "ExecutorPriority",
    "ParallelDecision",
    "IsolationLevel",
    "ArbitrationType",
    "ConflictType",
    "ResourceType",
    "LifecycleEvent",
    "HumanOverrideAction",
    # Dataclasses
    "ResourceQuota",
    "ExecutionRequest",
    "SchedulingResult",
    "ExecutorStatus",
    "ConflictDetectionResult",
    "ArbitrationResult",
    "ParallelAuditEntry",
    # Engine
    "detect_conflict",
    "arbitrate_conflict",
    "make_scheduling_decision",
    "create_parallel_audit_entry",
    "MAX_CONCURRENT_EXECUTORS",
    "MAX_QUEUE_DEPTH",
]
