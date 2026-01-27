# Phase-39: Parallel Execution Governor - Types Module
# GOVERNANCE LAYER ONLY - No threading/multiprocessing
# Implements scheduling and arbitration contracts

"""
Phase-39 defines the governance types for parallel execution.
This module implements:
- Scheduling enums (CLOSED)
- Arbitration enums (CLOSED)
- Executor dataclasses (frozen=True)

NO THREADING/MULTIPROCESSING - PURE GOVERNANCE LOGIC
"""

from dataclasses import dataclass
from enum import Enum
from typing import Optional, List, Dict


# =============================================================================
# CLOSED ENUMS - Scheduling
# =============================================================================

class SchedulingAlgorithm(Enum):
    """
    CLOSED ENUM - 4 members
    Scheduling algorithm for parallel execution.
    """
    FIFO = "FIFO"                    # First-in-first-out
    FAIR_SHARE = "FAIR_SHARE"        # Weighted fair queuing
    PRIORITY_AGED = "PRIORITY_AGED"  # Priority with aging
    ROUND_ROBIN = "ROUND_ROBIN"      # Equal time slices


class ExecutorState(Enum):
    """
    CLOSED ENUM - 8 members
    States in executor lifecycle.
    """
    PENDING = "PENDING"           # Waiting in queue
    ADMITTED = "ADMITTED"         # Passed admission control
    INITIALIZING = "INITIALIZING" # Setting up isolation
    RUNNING = "RUNNING"           # Actively executing
    PAUSED = "PAUSED"             # Human-paused
    TERMINATING = "TERMINATING"   # Cleanup in progress
    COMPLETED = "COMPLETED"       # Finished successfully
    FAILED = "FAILED"             # Finished with error


class ExecutorPriority(Enum):
    """
    CLOSED ENUM - 5 members
    Priority levels for executors.
    """
    CRITICAL = "CRITICAL"  # Human-safety related
    HIGH = "HIGH"          # Time-sensitive
    NORMAL = "NORMAL"      # Default
    LOW = "LOW"            # Background
    IDLE = "IDLE"          # Only when nothing else


class ParallelDecision(Enum):
    """
    CLOSED ENUM - 5 members
    Decisions for parallel execution requests.
    """
    ALLOW = "ALLOW"        # Execute immediately
    QUEUE = "QUEUE"        # Wait for resources
    SERIALIZE = "SERIALIZE"  # Execute after conflict resolves
    DENY = "DENY"          # Reject execution
    ESCALATE = "ESCALATE"  # Human decides


class IsolationLevel(Enum):
    """
    CLOSED ENUM - 4 members
    Isolation levels for executors.
    """
    PROCESS = "PROCESS"      # Separate OS process
    CONTAINER = "CONTAINER"  # Container isolation
    VM = "VM"                # Virtual machine
    NONE = "NONE"            # No isolation (FORBIDDEN)


class ArbitrationType(Enum):
    """
    CLOSED ENUM - 5 members
    Types of arbitration for conflicts.
    """
    FIRST_REGISTERED = "FIRST_REGISTERED"  # First request wins
    SERIALIZE = "SERIALIZE"                # Execute serially
    DENY_ALL = "DENY_ALL"                  # Deny all conflicting
    ESCALATE_HUMAN = "ESCALATE_HUMAN"      # Ask human to decide
    MERGE_SAFE = "MERGE_SAFE"              # Merge if non-conflicting


class ConflictType(Enum):
    """
    CLOSED ENUM - 5 members
    Types of conflicts between executors.
    """
    RESOURCE_CONTENTION = "RESOURCE_CONTENTION"
    TARGET_OVERLAP = "TARGET_OVERLAP"
    CAPABILITY_CONFLICT = "CAPABILITY_CONFLICT"
    AUTHORITY_DISPUTE = "AUTHORITY_DISPUTE"
    UNKNOWN_CONFLICT = "UNKNOWN_CONFLICT"


class ResourceType(Enum):
    """
    CLOSED ENUM - 7 members
    Types of resources that can be consumed.
    """
    CPU_TIME = "CPU_TIME"
    WALL_TIME = "WALL_TIME"
    MEMORY = "MEMORY"
    FILE_DESCRIPTORS = "FILE_DESCRIPTORS"
    DISK_BYTES = "DISK_BYTES"
    NETWORK_BYTES = "NETWORK_BYTES"
    EXECUTOR_SLOTS = "EXECUTOR_SLOTS"


class LifecycleEvent(Enum):
    """
    CLOSED ENUM - 10 members
    Events in executor lifecycle.
    """
    QUEUED = "QUEUED"
    ADMITTED = "ADMITTED"
    INITIALIZED = "INITIALIZED"
    STARTED = "STARTED"
    PAUSED = "PAUSED"
    RESUMED = "RESUMED"
    TIMEOUT = "TIMEOUT"
    KILLED = "KILLED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class HumanOverrideAction(Enum):
    """
    CLOSED ENUM - 8 members
    Human override actions for parallel execution.
    """
    PAUSE_ALL = "PAUSE_ALL"
    PAUSE_ONE = "PAUSE_ONE"
    RESUME_ALL = "RESUME_ALL"
    RESUME_ONE = "RESUME_ONE"
    KILL_ALL = "KILL_ALL"
    KILL_ONE = "KILL_ONE"
    ADJUST_LIMITS = "ADJUST_LIMITS"
    ADJUST_PRIORITY = "ADJUST_PRIORITY"


# =============================================================================
# FROZEN DATACLASSES
# =============================================================================

@dataclass(frozen=True)
class ResourceQuota:
    """
    Frozen dataclass for resource quota specification.
    """
    resource_type: ResourceType
    soft_limit: int
    hard_limit: int
    burst_allowed: bool
    burst_duration_seconds: int


@dataclass(frozen=True)
class ExecutionRequest:
    """
    Frozen dataclass for a parallel execution request.
    """
    request_id: str
    executor_type: str
    priority: ExecutorPriority
    isolation_level: IsolationLevel
    timeout_seconds: int
    context_hash: str
    requester_id: str
    description: str


@dataclass(frozen=True)
class SchedulingResult:
    """
    Frozen dataclass for scheduling decision result.
    """
    request_id: str
    decision: ParallelDecision
    reason_code: str
    executor_id: str
    queue_position: int
    estimated_wait_seconds: int


@dataclass(frozen=True)
class ExecutorStatus:
    """
    Frozen dataclass for executor status.
    """
    executor_id: str
    state: ExecutorState
    started_at: str
    elapsed_seconds: int


@dataclass(frozen=True)
class ConflictDetectionResult:
    """
    Frozen dataclass for conflict detection outcome.
    """
    has_conflict: bool
    conflict_type: Optional[ConflictType]
    conflicting_request_id: Optional[str]
    description: str


@dataclass(frozen=True)
class ArbitrationResult:
    """
    Frozen dataclass for arbitration outcome.
    """
    arbitration_type: ArbitrationType
    winner_request_id: Optional[str]
    loser_request_ids: tuple  # Tuple for immutability
    reason: str


@dataclass(frozen=True)
class ParallelAuditEntry:
    """
    Frozen dataclass for parallel execution audit entries.
    """
    audit_id: str
    event: LifecycleEvent
    request_id: str
    executor_id: str
    decision: ParallelDecision
    reason_code: str
    timestamp: str
