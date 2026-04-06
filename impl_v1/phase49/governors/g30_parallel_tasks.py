# G30: Parallel Task Governor
"""
Safe parallel task execution engine.

Features:
✓ Task queue with priority
✓ Parallel READ-ONLY headless sessions
✓ Browser-based scanning (no API dependency)
✓ GPU auto-detection (CPU fallback)
✓ Resource isolation

STRICTLY FORBIDDEN:
✗ Exploitation
✗ Submission
✗ State mutation
✗ Write operations
"""

from dataclasses import dataclass
from enum import Enum
from typing import List, Optional, Tuple, Dict, Any, Protocol, Sequence, runtime_checkable
import uuid
from datetime import datetime, UTC
from concurrent.futures import ThreadPoolExecutor, Future
import threading
import math


_UNSUPPORTED_PARALLEL_EXECUTION_MESSAGE = (
    "UNSUPPORTED: Real parallel task execution is not implemented; "
    "mock or stub task execution is not allowed in production"
)

_MISSING_DISPATCHER_MESSAGE = (
    "UNSUPPORTED: Real parallel task execution requires a wired "
    "RealBackendDispatcher; mock or stub task execution is not allowed in production"
)


class TaskType(Enum):
    """CLOSED ENUM - Task types."""
    DISCOVERY = "DISCOVERY"
    SCOPE_SCAN = "SCOPE_SCAN"
    DUPLICATE_CHECK = "DUPLICATE_CHECK"
    CVE_LOOKUP = "CVE_LOOKUP"
    METADATA_EXTRACT = "METADATA_EXTRACT"


class TaskPriority(Enum):
    """CLOSED ENUM - Task priority levels."""
    LOW = 1
    NORMAL = 2
    HIGH = 3
    CRITICAL = 4


class TaskStatus(Enum):
    """CLOSED ENUM - Task status."""
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class ExecutionBackend(Enum):
    """CLOSED ENUM - Execution backend."""
    CPU = "CPU"
    GPU = "GPU"


@runtime_checkable
class RealBackendDispatcher(Protocol):
    """Production dispatcher contract for real parallel task execution."""

    def dispatch(self, task_type: TaskType, target_url: str, parameters: tuple) -> dict:
        ...


@dataclass(frozen=True)
class TaskSpec:
    """Task specification."""
    task_id: str
    task_type: TaskType
    priority: TaskPriority
    target_url: str
    parameters: Tuple[Tuple[str, str], ...]
    created_at: str
    timeout_seconds: int


@dataclass(frozen=True)
class TaskResult:
    """Task execution result."""
    task_id: str
    status: TaskStatus
    started_at: str
    completed_at: str
    result_data: Optional[Dict[str, Any]]
    error_message: Optional[str]
    execution_time_ms: int
    backend_used: ExecutionBackend


@dataclass(frozen=True)
class QueueStatus:
    """Queue status snapshot."""
    queued_count: int
    running_count: int
    completed_count: int
    failed_count: int
    total_processed: int


@dataclass(frozen=True)
class ResourceLimits:
    """Resource limits for parallel execution."""
    max_parallel_tasks: int
    max_memory_mb: int
    max_cpu_percent: int
    timeout_seconds: int


@dataclass(frozen=True)
class TaskMetrics:
    """Per-task execution metrics snapshot."""

    task_id: str
    task_type: str
    duration_ms: int
    worker_id: str
    queue_wait_ms: int


@dataclass(frozen=True)
class ParallelExecutionReport:
    """Aggregate report for a completed parallel execution batch."""

    total_tasks: int
    completed: int
    failed: int
    mean_duration_ms: float
    p95_duration_ms: float
    generated_at: str


def _utc_now() -> str:
    """Return the current UTC timestamp in ISO-8601 format."""

    return datetime.now(UTC).isoformat()


def _get_percentile_value(values: Sequence[int], percentile: float) -> float:
    """Return a nearest-rank percentile from the observed duration distribution."""

    if not values:
        return 0.0

    sorted_values = sorted(values)
    index = max(0, min(len(sorted_values) - 1, math.ceil(len(sorted_values) * percentile) - 1))
    return float(sorted_values[index])


def _missing_dispatcher_error(task_type: TaskType) -> RuntimeError:
    """Return the fail-closed dispatcher wiring error."""

    return RuntimeError(f"{_MISSING_DISPATCHER_MESSAGE} (task_type={task_type.value})")


def _is_missing_dispatcher_error(error: RuntimeError) -> bool:
    """Check whether a runtime error represents a missing real dispatcher."""

    return str(error).startswith(_MISSING_DISPATCHER_MESSAGE)


class TaskWorkerPool:
    """Thread-backed worker pool for real dispatcher execution."""

    def __init__(
        self,
        max_workers: int = 4,
        dispatcher: Optional[RealBackendDispatcher] = None,
        backend: Optional[ExecutionBackend] = None,
    ):
        self.max_workers = max_workers
        self._dispatcher = dispatcher
        self._backend = backend or get_execution_backend()
        self._executor = ThreadPoolExecutor(max_workers=max_workers)
        self._active_workers = 0
        self._queued_tasks = 0
        self._completed_total = 0
        self._failed_total = 0
        self._lock = threading.Lock()

    def submit(self, task: TaskSpec) -> Future:
        """Submit a task to the pool."""

        with self._lock:
            self._queued_tasks += 1
        return self._executor.submit(self._execute_task, task)

    def _execute_task(self, task: TaskSpec) -> TaskResult:
        """Execute a submitted task through the real dispatcher."""

        started_at = datetime.now(UTC)
        with self._lock:
            self._queued_tasks -= 1
            self._active_workers += 1

        try:
            if self._dispatcher is None:
                raise _missing_dispatcher_error(task.task_type)

            result_data = self._dispatcher.dispatch(task.task_type, task.target_url, task.parameters)
            completed_at = datetime.now(UTC)
            elapsed_ms = int((completed_at - started_at).total_seconds() * 1000)

            with self._lock:
                self._completed_total += 1

            return TaskResult(
                task_id=task.task_id,
                status=TaskStatus.COMPLETED,
                started_at=started_at.isoformat(),
                completed_at=completed_at.isoformat(),
                result_data=result_data,
                error_message=None,
                execution_time_ms=elapsed_ms,
                backend_used=self._backend,
            )
        except RuntimeError as e:
            completed_at = datetime.now(UTC)
            elapsed_ms = int((completed_at - started_at).total_seconds() * 1000)

            with self._lock:
                self._failed_total += 1

            if _is_missing_dispatcher_error(e):
                raise

            return TaskResult(
                task_id=task.task_id,
                status=TaskStatus.FAILED,
                started_at=started_at.isoformat(),
                completed_at=completed_at.isoformat(),
                result_data=None,
                error_message=str(e),
                execution_time_ms=elapsed_ms,
                backend_used=self._backend,
            )
        except Exception as e:  # pragma: no cover - defensive exception handling
            completed_at = datetime.now(UTC)  # pragma: no cover
            elapsed_ms = int((completed_at - started_at).total_seconds() * 1000)  # pragma: no cover

            with self._lock:
                self._failed_total += 1

            return TaskResult(  # pragma: no cover
                task_id=task.task_id,
                status=TaskStatus.FAILED,
                started_at=started_at.isoformat(),
                completed_at=completed_at.isoformat(),
                result_data=None,
                error_message=str(e),
                execution_time_ms=elapsed_ms,
                backend_used=self._backend,
            )
        finally:
            with self._lock:
                self._active_workers -= 1

    def get_pool_stats(self) -> dict:
        """Return current worker-pool statistics."""

        with self._lock:
            return {
                "active_workers": self._active_workers,
                "queued_tasks": self._queued_tasks,
                "completed_total": self._completed_total,
                "failed_total": self._failed_total,
            }

    def shutdown(self) -> None:
        """Shutdown the pool executor."""

        self._executor.shutdown(wait=False)


# =============================================================================
# GUARDS (MANDATORY - ABSOLUTE)
# =============================================================================

def can_task_exploit() -> bool:
    """
    Guard: Can tasks perform exploitation?
    
    ANSWER: NEVER.
    """
    return False


def can_task_submit() -> bool:
    """
    Guard: Can tasks submit data?
    
    ANSWER: NEVER.
    """
    return False


def can_task_mutate_state() -> bool:
    """
    Guard: Can tasks mutate external state?
    
    ANSWER: NEVER.
    """
    return False


def can_task_write() -> bool:
    """
    Guard: Can tasks perform write operations?
    
    ANSWER: NEVER.
    """
    return False


def can_task_bypass_isolation() -> bool:
    """
    Guard: Can tasks bypass isolation?
    
    ANSWER: NEVER.
    """
    return False


# =============================================================================
# GPU DETECTION
# =============================================================================

def detect_gpu_availability() -> bool:
    """Detect if GPU is available for acceleration."""
    try:
        import torch
        return torch.cuda.is_available()
    except ImportError:
        return False  # PyTorch not installed — CPU fallback


def get_execution_backend() -> ExecutionBackend:
    """Get the execution backend to use."""
    if detect_gpu_availability():  # pragma: no cover - GPU not detected in current env
        return ExecutionBackend.GPU  # pragma: no cover
    return ExecutionBackend.CPU


# =============================================================================
# TASK BUILDERS
# =============================================================================

def create_task_id() -> str:
    """Generate unique task ID."""
    return f"TSK-{uuid.uuid4().hex[:12].upper()}"


def create_discovery_task(
    target_url: str,
    priority: TaskPriority = TaskPriority.NORMAL,
    timeout_seconds: int = 60,
) -> TaskSpec:
    """Create a discovery task."""
    return TaskSpec(
        task_id=create_task_id(),
        task_type=TaskType.DISCOVERY,
        priority=priority,
        target_url=target_url,
        parameters=(),
        created_at=datetime.now(UTC).isoformat(),
        timeout_seconds=timeout_seconds,
    )


def create_scope_scan_task(
    target_url: str,
    scope_domains: Tuple[str, ...],
    priority: TaskPriority = TaskPriority.NORMAL,
) -> TaskSpec:
    """Create a scope scanning task."""
    params = tuple(("domain", d) for d in scope_domains)
    return TaskSpec(
        task_id=create_task_id(),
        task_type=TaskType.SCOPE_SCAN,
        priority=priority,
        target_url=target_url,
        parameters=params,
        created_at=datetime.now(UTC).isoformat(),
        timeout_seconds=120,
    )


def create_cve_lookup_task(
    target_url: str,
    cve_ids: Tuple[str, ...],
    priority: TaskPriority = TaskPriority.HIGH,
) -> TaskSpec:
    """Create a CVE lookup task."""
    params = tuple(("cve", c) for c in cve_ids)
    return TaskSpec(
        task_id=create_task_id(),
        task_type=TaskType.CVE_LOOKUP,
        priority=priority,
        target_url=target_url,
        parameters=params,
        created_at=datetime.now(UTC).isoformat(),
        timeout_seconds=30,
    )


# =============================================================================
# PARALLEL TASK ENGINE
# =============================================================================

class ParallelTaskEngine:
    """
    Parallel task execution engine.
    
    Executes READ-ONLY tasks in parallel with isolation.
    """
    
    def __init__(
        self,
        max_workers: int = 4,
        limits: Optional[ResourceLimits] = None,
        dispatcher: Optional[RealBackendDispatcher] = None,
    ):
        self.max_workers = max_workers
        self.limits = limits or ResourceLimits(
            max_parallel_tasks=max_workers,
            max_memory_mb=1024,
            max_cpu_percent=80,
            timeout_seconds=300,
        )
        self._executor = ThreadPoolExecutor(max_workers=max_workers)
        self._queue: List[TaskSpec] = []
        self._running: Dict[str, Future] = {}
        self._results: Dict[str, TaskResult] = {}
        self._lock = threading.Lock()
        self._backend = get_execution_backend()
        self._dispatcher = dispatcher
    
    @property
    def backend(self) -> ExecutionBackend:
        """Get current execution backend."""
        return self._backend
    
    def enqueue(self, task: TaskSpec) -> bool:
        """Add task to queue."""
        # Enforce guards
        if can_task_exploit():  # pragma: no cover
            raise RuntimeError("SECURITY: Task exploitation enabled")  # pragma: no cover
        
        with self._lock:
            self._queue.append(task)
            # Sort by priority (higher first)
            self._queue.sort(key=lambda t: t.priority.value, reverse=True)
        return True
    
    def enqueue_batch(self, tasks: List[TaskSpec]) -> int:
        """Add multiple tasks to queue."""
        count = 0
        for task in tasks:
            if self.enqueue(task):
                count += 1
        return count
    
    def _execute_task(self, task: TaskSpec) -> TaskResult:
        """Execute a single task (internal)."""
        # Enforce guards
        if can_task_mutate_state():  # pragma: no cover
            raise RuntimeError("SECURITY: Task mutation enabled")  # pragma: no cover
        if can_task_write():  # pragma: no cover
            raise RuntimeError("SECURITY: Task write enabled")  # pragma: no cover
        
        started_at = datetime.now(UTC)
        
        try:
            result_data = self._run_task_logic(task)
            
            completed_at = datetime.now(UTC)
            elapsed_ms = int((completed_at - started_at).total_seconds() * 1000)
            
            return TaskResult(
                task_id=task.task_id,
                status=TaskStatus.COMPLETED,
                started_at=started_at.isoformat(),
                completed_at=completed_at.isoformat(),
                result_data=result_data,
                error_message=None,
                execution_time_ms=elapsed_ms,
                backend_used=self._backend,
            )
        except RuntimeError as e:
            if _is_missing_dispatcher_error(e):
                raise

            completed_at = datetime.now(UTC)
            elapsed_ms = int((completed_at - started_at).total_seconds() * 1000)

            return TaskResult(
                task_id=task.task_id,
                status=TaskStatus.FAILED,
                started_at=started_at.isoformat(),
                completed_at=completed_at.isoformat(),
                result_data=None,
                error_message=str(e),
                execution_time_ms=elapsed_ms,
                backend_used=self._backend,
            )
        except Exception as e:  # pragma: no cover - defensive exception handling
            completed_at = datetime.now(UTC)  # pragma: no cover
            elapsed_ms = int((completed_at - started_at).total_seconds() * 1000)  # pragma: no cover
            
            return TaskResult(  # pragma: no cover
                task_id=task.task_id,
                status=TaskStatus.FAILED,
                started_at=started_at.isoformat(),
                completed_at=completed_at.isoformat(),
                result_data=None,
                error_message=str(e),
                execution_time_ms=elapsed_ms,
                backend_used=self._backend,
            )
    
    def _run_task_logic(self, task: TaskSpec) -> Dict[str, Any]:
        """Dispatch a task through the real backend or fail closed."""

        if self._dispatcher is None:
            raise _missing_dispatcher_error(task.task_type)

        return self._dispatcher.dispatch(task.task_type, task.target_url, task.parameters)
    
    def run_next(self) -> Optional[TaskResult]:
        """Run next task from queue synchronously."""
        with self._lock:
            if not self._queue:
                return None
            task = self._queue.pop(0)
        
        result = self._execute_task(task)
        
        with self._lock:
            self._results[task.task_id] = result
        
        return result
    
    def run_all(self) -> List[TaskResult]:
        """Run all queued tasks in parallel."""
        results = []
        
        with self._lock:
            tasks = self._queue.copy()
            self._queue.clear()
        
        futures = []
        for task in tasks:
            future = self._executor.submit(self._execute_task, task)
            futures.append((task.task_id, future))
        
        for task_id, future in futures:
            try:
                result = future.result(timeout=self.limits.timeout_seconds)
            except RuntimeError as e:
                if _is_missing_dispatcher_error(e):
                    raise

                result = TaskResult(
                    task_id=task_id,
                    status=TaskStatus.FAILED,
                    started_at=_utc_now(),
                    completed_at=_utc_now(),
                    result_data=None,
                    error_message=str(e),
                    execution_time_ms=0,
                    backend_used=self._backend,
                )
            except Exception as e:  # pragma: no cover - defensive exception handling
                result = TaskResult(  # pragma: no cover
                    task_id=task_id,
                    status=TaskStatus.FAILED,
                    started_at=_utc_now(),
                    completed_at=_utc_now(),
                    result_data=None,
                    error_message=str(e),
                    execution_time_ms=0,
                    backend_used=self._backend,
                )
            
            results.append(result)
            with self._lock:
                self._results[task_id] = result
        
        return results
    
    def get_queue_status(self) -> QueueStatus:
        """Get current queue status."""
        with self._lock:
            completed = sum(1 for r in self._results.values() if r.status == TaskStatus.COMPLETED)
            failed = sum(1 for r in self._results.values() if r.status == TaskStatus.FAILED)
            
            return QueueStatus(
                queued_count=len(self._queue),
                running_count=len(self._running),
                completed_count=completed,
                failed_count=failed,
                total_processed=len(self._results),
            )
    
    def get_result(self, task_id: str) -> Optional[TaskResult]:
        """Get result for a specific task."""
        with self._lock:
            return self._results.get(task_id)
    
    def cancel_all(self) -> int:
        """Cancel all queued tasks."""
        with self._lock:
            count = len(self._queue)
            self._queue.clear()
        return count
    
    def shutdown(self) -> None:
        """Shutdown the executor."""
        self._executor.shutdown(wait=False)


# =============================================================================
# HIGH-LEVEL API
# =============================================================================

def create_parallel_engine(
    max_workers: int = 4,
    limits: Optional[ResourceLimits] = None,
    dispatcher: Optional[RealBackendDispatcher] = None,
) -> ParallelTaskEngine:
    """Create a new parallel task engine."""
    return ParallelTaskEngine(max_workers, limits, dispatcher)


def aggregate_results(results: Sequence[TaskResult]) -> Dict[str, int]:
    """Aggregate task results by status."""

    return {
        "total_tasks": len(results),
        "queued": sum(1 for result in results if result.status == TaskStatus.QUEUED),
        "running": sum(1 for result in results if result.status == TaskStatus.RUNNING),
        "completed": sum(1 for result in results if result.status == TaskStatus.COMPLETED),
        "failed": sum(1 for result in results if result.status == TaskStatus.FAILED),
        "cancelled": sum(1 for result in results if result.status == TaskStatus.CANCELLED),
    }


def generate_execution_report(results: Sequence[TaskResult]) -> ParallelExecutionReport:
    """Generate an execution report from observed task results."""

    counts = aggregate_results(results)
    durations = [result.execution_time_ms for result in results]
    mean_duration_ms = float(sum(durations) / len(durations)) if durations else 0.0

    return ParallelExecutionReport(
        total_tasks=counts["total_tasks"],
        completed=counts["completed"],
        failed=counts["failed"],
        mean_duration_ms=mean_duration_ms,
        p95_duration_ms=_get_percentile_value(durations, 0.95),
        generated_at=_utc_now(),
    )


def is_parallelism_safe(task: TaskSpec) -> bool:
    """Check if task is safe for parallel execution."""
    # All supported task types are READ-ONLY
    return task.task_type in (
        TaskType.DISCOVERY,
        TaskType.SCOPE_SCAN,
        TaskType.DUPLICATE_CHECK,
        TaskType.CVE_LOOKUP,
        TaskType.METADATA_EXTRACT,
    )
