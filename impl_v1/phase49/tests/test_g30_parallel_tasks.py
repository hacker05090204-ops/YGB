# Test G30: Parallel Task Governor
"""
Tests for parallel task governor.

100% coverage required.
"""

import pytest
from impl_v1.phase49.governors.g30_parallel_tasks import (
    TaskType,
    TaskPriority,
    TaskStatus,
    ExecutionBackend,
    TaskSpec,
    TaskResult,
    QueueStatus,
    ResourceLimits,
    can_task_exploit,
    can_task_submit,
    can_task_mutate_state,
    can_task_write,
    can_task_bypass_isolation,
    detect_gpu_availability,
    get_execution_backend,
    create_task_id,
    create_discovery_task,
    create_scope_scan_task,
    create_cve_lookup_task,
    ParallelTaskEngine,
    TaskWorkerPool,
    create_parallel_engine,
    aggregate_results,
    generate_execution_report,
    is_parallelism_safe,
)


class TestGuards:
    """Test all security guards."""
    
    def test_can_task_exploit_always_false(self):
        """Guard: Tasks cannot exploit."""
        assert can_task_exploit() is False
    
    def test_can_task_submit_always_false(self):
        """Guard: Tasks cannot submit."""
        assert can_task_submit() is False
    
    def test_can_task_mutate_state_always_false(self):
        """Guard: Tasks cannot mutate."""
        assert can_task_mutate_state() is False
    
    def test_can_task_write_always_false(self):
        """Guard: Tasks cannot write."""
        assert can_task_write() is False
    
    def test_can_task_bypass_isolation_always_false(self):
        """Guard: Tasks cannot bypass isolation."""
        assert can_task_bypass_isolation() is False


class TestGpuDetection:
    """Test GPU detection."""
    
    def test_detect_gpu_availability(self):
        """Detect GPU returns a bool (real CUDA detection)."""
        result = detect_gpu_availability()
        assert isinstance(result, bool)
    
    def test_get_execution_backend(self):
        """Get backend based on real GPU availability."""
        backend = get_execution_backend()
        assert backend in (ExecutionBackend.CPU, ExecutionBackend.GPU)


class TestTaskBuilders:
    """Test task builder functions."""
    
    def test_create_task_id(self):
        """Create task ID."""
        tid = create_task_id()
        assert tid.startswith("TSK-")
    
    def test_create_discovery_task(self):
        """Create discovery task."""
        task = create_discovery_task("https://example.com")
        
        assert task.task_type == TaskType.DISCOVERY
        assert task.priority == TaskPriority.NORMAL
        assert task.target_url == "https://example.com"
    
    def test_create_discovery_task_high_priority(self):
        """Create high priority discovery task."""
        task = create_discovery_task(
            "https://example.com",
            priority=TaskPriority.HIGH,
        )
        
        assert task.priority == TaskPriority.HIGH
    
    def test_create_scope_scan_task(self):
        """Create scope scan task."""
        task = create_scope_scan_task(
            "https://example.com",
            ("example.com", "api.example.com"),
        )
        
        assert task.task_type == TaskType.SCOPE_SCAN
        assert len(task.parameters) == 2
    
    def test_create_cve_lookup_task(self):
        """Create CVE lookup task."""
        task = create_cve_lookup_task(
            "https://example.com",
            ("CVE-2024-1234", "CVE-2024-5678"),
        )
        
        assert task.task_type == TaskType.CVE_LOOKUP
        assert task.priority == TaskPriority.HIGH


class TestParallelEngine:
    """Test parallel task engine."""
    
    def test_create_engine(self):
        """Create parallel engine."""
        engine = create_parallel_engine()
        assert engine.max_workers == 4
        assert engine.backend in (ExecutionBackend.CPU, ExecutionBackend.GPU)
    
    def test_create_engine_custom_workers(self):
        """Create engine with custom workers."""
        engine = create_parallel_engine(max_workers=8)
        assert engine.max_workers == 8
    
    def test_enqueue_task(self):
        """Enqueue task."""
        engine = ParallelTaskEngine()
        task = create_discovery_task("https://example.com")
        
        result = engine.enqueue(task)
        assert result is True
        
        status = engine.get_queue_status()
        assert status.queued_count == 1
    
    def test_enqueue_batch(self):
        """Enqueue batch of tasks."""
        engine = ParallelTaskEngine()
        tasks = [
            create_discovery_task("https://a.com"),
            create_discovery_task("https://b.com"),
        ]
        
        count = engine.enqueue_batch(tasks)
        assert count == 2
    
    def test_run_next(self):
        """Run next task fails closed when no real dispatcher is wired."""
        engine = ParallelTaskEngine()
        task = create_discovery_task("https://example.com")
        engine.enqueue(task)

        with pytest.raises(RuntimeError, match="RealBackendDispatcher"):
            engine.run_next()
    
    def test_run_next_empty(self):
        """Run next with empty queue."""
        engine = ParallelTaskEngine()
        result = engine.run_next()
        assert result is None
    
    def test_run_all(self):
        """Run all tasks fails closed when no real dispatcher is wired."""
        engine = ParallelTaskEngine(max_workers=2)
        engine.enqueue(create_discovery_task("https://a.com"))
        engine.enqueue(create_discovery_task("https://b.com"))
        engine.enqueue(create_scope_scan_task("https://c.com", ("c.com",)))

        with pytest.raises(RuntimeError, match="RealBackendDispatcher"):
            engine.run_all()
    
    def test_priority_ordering(self):
        """Tasks are ordered by priority."""
        engine = ParallelTaskEngine()
        low_task = create_discovery_task("https://low.com", TaskPriority.LOW)
        high_task = create_discovery_task("https://high.com", TaskPriority.HIGH)
        normal_task = create_discovery_task("https://normal.com", TaskPriority.NORMAL)
        engine.enqueue(low_task)
        engine.enqueue(high_task)
        engine.enqueue(normal_task)

        assert engine._queue[0].task_id == high_task.task_id
    
    def test_get_queue_status(self):
        """Get queue status."""
        engine = ParallelTaskEngine()
        engine.enqueue(create_discovery_task("https://example.com"))
        
        status = engine.get_queue_status()
        
        assert status.queued_count == 1
        assert status.running_count == 0
        assert status.completed_count == 0
    
    def test_get_result(self):
        """Get result remains empty after fail-closed dispatcher rejection."""
        engine = ParallelTaskEngine()
        task = create_discovery_task("https://example.com")
        engine.enqueue(task)

        with pytest.raises(RuntimeError, match="RealBackendDispatcher"):
            engine.run_next()

        result = engine.get_result(task.task_id)

        assert result is None
    
    def test_get_result_not_found(self):
        """Get result for unknown task."""
        engine = ParallelTaskEngine()
        result = engine.get_result("UNKNOWN-ID")
        assert result is None
    
    def test_cancel_all(self):
        """Cancel all queued tasks."""
        engine = ParallelTaskEngine()
        engine.enqueue(create_discovery_task("https://a.com"))
        engine.enqueue(create_discovery_task("https://b.com"))
        
        count = engine.cancel_all()
        
        assert count == 2
        assert engine.get_queue_status().queued_count == 0
    
    def test_shutdown(self):
        """Shutdown engine."""
        engine = ParallelTaskEngine()
        engine.shutdown()  # Should not raise


class TestTaskExecution:
    """Test task execution logic."""
    
    def test_discovery_task_result(self):
        """Discovery task hard-fails until a real execution backend exists."""
        engine = ParallelTaskEngine()
        engine.enqueue(create_discovery_task("https://example.com"))

        with pytest.raises(RuntimeError, match="RealBackendDispatcher"):
            engine.run_next()
    
    def test_scope_scan_result(self):
        """Scope scan hard-fails until a real execution backend exists."""
        engine = ParallelTaskEngine()
        engine.enqueue(create_scope_scan_task("https://example.com", ("example.com",)))

        with pytest.raises(RuntimeError, match="RealBackendDispatcher"):
            engine.run_next()
    
    def test_cve_lookup_result(self):
        """CVE lookup hard-fails until a real execution backend exists."""
        engine = ParallelTaskEngine()
        engine.enqueue(create_cve_lookup_task("https://example.com", ("CVE-2024-1234",)))

        with pytest.raises(RuntimeError, match="RealBackendDispatcher"):
            engine.run_next()
    
    def test_duplicate_check_result(self):
        """Duplicate check hard-fails until a real execution backend exists."""
        engine = ParallelTaskEngine()
        # Create duplicate check task directly
        task = TaskSpec(
            task_id=create_task_id(),
            task_type=TaskType.DUPLICATE_CHECK,
            priority=TaskPriority.NORMAL,
            target_url="https://example.com",
            parameters=(),
            created_at="2026-01-28T00:00:00Z",
            timeout_seconds=30,
        )
        engine.enqueue(task)

        with pytest.raises(RuntimeError, match="RealBackendDispatcher"):
            engine.run_next()
    
    def test_metadata_extract_result(self):
        """Metadata extraction hard-fails until a real execution backend exists."""
        engine = ParallelTaskEngine()
        # Create metadata extract task directly
        task = TaskSpec(
            task_id=create_task_id(),
            task_type=TaskType.METADATA_EXTRACT,
            priority=TaskPriority.NORMAL,
            target_url="https://example.com",
            parameters=(),
            created_at="2026-01-28T00:00:00Z",
            timeout_seconds=30,
        )
        engine.enqueue(task)

        with pytest.raises(RuntimeError, match="RealBackendDispatcher"):
            engine.run_next()


class TestParallelExecutionReporting:
    """Test Group A reporting helpers."""

    @staticmethod
    def _result(task_id: str, status: TaskStatus, execution_time_ms: int) -> TaskResult:
        return TaskResult(
            task_id=task_id,
            status=status,
            started_at="2026-01-28T00:00:00+00:00",
            completed_at="2026-01-28T00:00:01+00:00",
            result_data={"task_id": task_id} if status == TaskStatus.COMPLETED else None,
            error_message=None if status == TaskStatus.COMPLETED else status.value,
            execution_time_ms=execution_time_ms,
            backend_used=ExecutionBackend.CPU,
        )

    def test_generate_execution_report_uses_actual_p95_distribution(self):
        """Execution report computes p95 from observed durations."""
        results = [
            self._result("TSK-1", TaskStatus.COMPLETED, 10),
            self._result("TSK-2", TaskStatus.COMPLETED, 20),
            self._result("TSK-3", TaskStatus.COMPLETED, 30),
            self._result("TSK-4", TaskStatus.COMPLETED, 40),
            self._result("TSK-5", TaskStatus.FAILED, 200),
        ]

        report = generate_execution_report(results)

        assert report.total_tasks == 5
        assert report.completed == 4
        assert report.failed == 1
        assert report.mean_duration_ms == 60.0
        assert report.p95_duration_ms == 200.0
        assert report.generated_at.endswith("+00:00")

    def test_aggregate_results_returns_correct_counts(self):
        """Aggregate counts reflect each observed task status."""
        results = [
            self._result("TSK-1", TaskStatus.QUEUED, 0),
            self._result("TSK-2", TaskStatus.RUNNING, 5),
            self._result("TSK-3", TaskStatus.COMPLETED, 10),
            self._result("TSK-4", TaskStatus.COMPLETED, 15),
            self._result("TSK-5", TaskStatus.FAILED, 20),
            self._result("TSK-6", TaskStatus.CANCELLED, 0),
        ]

        counts = aggregate_results(results)

        assert counts == {
            "total_tasks": 6,
            "queued": 1,
            "running": 1,
            "completed": 2,
            "failed": 1,
            "cancelled": 1,
        }


class TestTaskWorkerPool:
    """Test Group A worker-pool accounting."""

    def test_get_pool_stats_tracks_failed_dispatch_without_dispatcher(self):
        """Pool stats reflect a fail-closed task when no dispatcher is wired."""
        pool = TaskWorkerPool(max_workers=1)
        future = pool.submit(create_discovery_task("https://example.com"))

        with pytest.raises(RuntimeError, match="RealBackendDispatcher"):
            future.result(timeout=1)

        stats = pool.get_pool_stats()
        pool.shutdown()

        assert stats == {
            "active_workers": 0,
            "queued_tasks": 0,
            "completed_total": 0,
            "failed_total": 1,
        }


class TestParallelismSafety:
    """Test parallelism safety checks."""
    
    def test_is_parallelism_safe_discovery(self):
        """Discovery is safe."""
        task = create_discovery_task("https://example.com")
        assert is_parallelism_safe(task) is True
    
    def test_is_parallelism_safe_scope_scan(self):
        """Scope scan is safe."""
        task = create_scope_scan_task("https://example.com", ("example.com",))
        assert is_parallelism_safe(task) is True


class TestDataclasses:
    """Test dataclass immutability."""
    
    def test_task_spec_frozen(self):
        """TaskSpec is immutable."""
        task = create_discovery_task("https://example.com")
        with pytest.raises(Exception):
            task.target_url = "changed"
    
    def test_task_result_frozen(self):
        """TaskResult is immutable."""
        result = TaskResult(
            "TSK-1", TaskStatus.COMPLETED,
            "2026-01-28T00:00:00Z", "2026-01-28T00:00:01Z",
            {}, None, 1000, ExecutionBackend.CPU
        )
        with pytest.raises(Exception):
            result.status = TaskStatus.FAILED
    
    def test_resource_limits_frozen(self):
        """ResourceLimits is immutable."""
        limits = ResourceLimits(4, 1024, 80, 300)
        with pytest.raises(Exception):
            limits.max_parallel_tasks = 8
