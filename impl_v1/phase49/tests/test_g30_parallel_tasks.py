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
    create_parallel_engine,
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
        """Detect GPU (mock returns False)."""
        assert detect_gpu_availability() is False
    
    def test_get_execution_backend(self):
        """Get backend (falls back to CPU)."""
        backend = get_execution_backend()
        assert backend == ExecutionBackend.CPU


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
        assert engine.backend == ExecutionBackend.CPU
    
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
        """Run next task."""
        engine = ParallelTaskEngine()
        task = create_discovery_task("https://example.com")
        engine.enqueue(task)
        
        result = engine.run_next()
        
        assert result is not None
        assert result.status == TaskStatus.COMPLETED
        assert result.task_id == task.task_id
    
    def test_run_next_empty(self):
        """Run next with empty queue."""
        engine = ParallelTaskEngine()
        result = engine.run_next()
        assert result is None
    
    def test_run_all(self):
        """Run all tasks in parallel."""
        engine = ParallelTaskEngine(max_workers=2)
        engine.enqueue(create_discovery_task("https://a.com"))
        engine.enqueue(create_discovery_task("https://b.com"))
        engine.enqueue(create_scope_scan_task("https://c.com", ("c.com",)))
        
        results = engine.run_all()
        
        assert len(results) == 3
        assert all(r.status == TaskStatus.COMPLETED for r in results)
    
    def test_priority_ordering(self):
        """Tasks are ordered by priority."""
        engine = ParallelTaskEngine()
        engine.enqueue(create_discovery_task("https://low.com", TaskPriority.LOW))
        engine.enqueue(create_discovery_task("https://high.com", TaskPriority.HIGH))
        engine.enqueue(create_discovery_task("https://normal.com", TaskPriority.NORMAL))
        
        # High priority should run first
        result1 = engine.run_next()
        assert "high.com" in result1.result_data.get("target", "")
    
    def test_get_queue_status(self):
        """Get queue status."""
        engine = ParallelTaskEngine()
        engine.enqueue(create_discovery_task("https://example.com"))
        
        status = engine.get_queue_status()
        
        assert status.queued_count == 1
        assert status.running_count == 0
        assert status.completed_count == 0
    
    def test_get_result(self):
        """Get result for specific task."""
        engine = ParallelTaskEngine()
        task = create_discovery_task("https://example.com")
        engine.enqueue(task)
        engine.run_next()
        
        result = engine.get_result(task.task_id)
        
        assert result is not None
        assert result.task_id == task.task_id
    
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
        """Discovery task returns results."""
        engine = ParallelTaskEngine()
        engine.enqueue(create_discovery_task("https://example.com"))
        result = engine.run_next()
        
        assert result.result_data["discovered"] is True
        assert "endpoints_found" in result.result_data
    
    def test_scope_scan_result(self):
        """Scope scan returns results."""
        engine = ParallelTaskEngine()
        engine.enqueue(create_scope_scan_task("https://example.com", ("example.com",)))
        result = engine.run_next()
        
        assert "in_scope" in result.result_data
    
    def test_cve_lookup_result(self):
        """CVE lookup returns results."""
        engine = ParallelTaskEngine()
        engine.enqueue(create_cve_lookup_task("https://example.com", ("CVE-2024-1234",)))
        result = engine.run_next()
        
        assert "cves_checked" in result.result_data
    
    def test_duplicate_check_result(self):
        """Duplicate check returns results."""
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
        result = engine.run_next()
        
        assert "is_duplicate" in result.result_data
    
    def test_metadata_extract_result(self):
        """Metadata extract returns results."""
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
        result = engine.run_next()
        
        assert "metadata" in result.result_data
        assert "title" in result.result_data["metadata"]


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
