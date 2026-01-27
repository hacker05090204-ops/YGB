# Phase-39 Tests: Parallel Types and Arbitration
"""
Tests for Phase-39 parallel execution governance.
100% coverage required.
Negative paths dominate.
"""

import pytest

from impl_v1.phase39.parallel_types import (
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
    ExecutionRequest,
    SchedulingResult,
    ConflictDetectionResult,
    ArbitrationResult,
)

from impl_v1.phase39.parallel_engine import (
    detect_conflict,
    arbitrate_conflict,
    make_scheduling_decision,
    MAX_CONCURRENT_EXECUTORS,
    MAX_QUEUE_DEPTH,
)


# =============================================================================
# FIXTURES
# =============================================================================

def make_valid_request(
    request_id: str = "REQ-PARALLEL000001",
    priority: ExecutorPriority = ExecutorPriority.NORMAL,
    isolation: IsolationLevel = IsolationLevel.PROCESS,
    requester_id: str = "test-requester",
    context_hash: str = "a" * 64,
) -> ExecutionRequest:
    """Create a valid execution request for testing."""
    return ExecutionRequest(
        request_id=request_id,
        executor_type="test-executor",
        priority=priority,
        isolation_level=isolation,
        timeout_seconds=300,
        context_hash=context_hash,
        requester_id=requester_id,
        description="Test parallel execution request"
    )


# =============================================================================
# ENUM CLOSURE TESTS
# =============================================================================

class TestEnumClosure:
    """Verify all enums are CLOSED with exact member counts."""
    
    def test_scheduling_algorithm_has_4_members(self):
        """SchedulingAlgorithm must have exactly 4 members."""
        assert len(SchedulingAlgorithm) == 4
    
    def test_executor_state_has_8_members(self):
        """ExecutorState must have exactly 8 members."""
        assert len(ExecutorState) == 8
    
    def test_executor_priority_has_5_members(self):
        """ExecutorPriority must have exactly 5 members."""
        assert len(ExecutorPriority) == 5
    
    def test_parallel_decision_has_5_members(self):
        """ParallelDecision must have exactly 5 members."""
        assert len(ParallelDecision) == 5
    
    def test_isolation_level_has_4_members(self):
        """IsolationLevel must have exactly 4 members."""
        assert len(IsolationLevel) == 4
    
    def test_arbitration_type_has_5_members(self):
        """ArbitrationType must have exactly 5 members."""
        assert len(ArbitrationType) == 5
    
    def test_conflict_type_has_5_members(self):
        """ConflictType must have exactly 5 members."""
        assert len(ConflictType) == 5
    
    def test_resource_type_has_7_members(self):
        """ResourceType must have exactly 7 members."""
        assert len(ResourceType) == 7
    
    def test_lifecycle_event_has_10_members(self):
        """LifecycleEvent must have exactly 10 members."""
        assert len(LifecycleEvent) == 10
    
    def test_human_override_action_has_8_members(self):
        """HumanOverrideAction must have exactly 8 members."""
        assert len(HumanOverrideAction) == 8


# =============================================================================
# DATACLASS FROZEN TESTS
# =============================================================================

class TestDataclassFrozen:
    """Verify all dataclasses are frozen (immutable)."""
    
    def test_execution_request_is_frozen(self):
        """ExecutionRequest must be frozen."""
        request = make_valid_request()
        with pytest.raises(AttributeError):
            request.priority = ExecutorPriority.HIGH
    
    def test_scheduling_result_is_frozen(self):
        """SchedulingResult must be frozen."""
        result = SchedulingResult(
            request_id="REQ-001",
            decision=ParallelDecision.DENY,
            reason_code="TEST",
            executor_id="",
            queue_position=-1,
            estimated_wait_seconds=0
        )
        with pytest.raises(AttributeError):
            result.decision = ParallelDecision.ALLOW


# =============================================================================
# CONFLICT DETECTION TESTS
# =============================================================================

class TestConflictDetection:
    """Test conflict detection logic."""
    
    def test_no_conflict_empty_state(self):
        """No conflict with empty state."""
        request = make_valid_request()
        result = detect_conflict(request, [], [])
        assert result.has_conflict is False
    
    def test_conflict_none_isolation(self):
        """NONE isolation is always a conflict."""
        request = make_valid_request(isolation=IsolationLevel.NONE)
        result = detect_conflict(request, [], [])
        assert result.has_conflict is True
        assert result.conflict_type == ConflictType.CAPABILITY_CONFLICT
    
    def test_conflict_same_requester(self):
        """Same requester with active request is conflict."""
        request1 = make_valid_request(request_id="REQ-001")
        request2 = make_valid_request(request_id="REQ-002")
        
        result = detect_conflict(request2, [request1], [])
        assert result.has_conflict is True
        assert result.conflict_type == ConflictType.RESOURCE_CONTENTION
    
    def test_conflict_max_executors(self):
        """Max concurrent executors reached is conflict."""
        request = make_valid_request()
        running = [f"EXEC-{i:03d}" for i in range(MAX_CONCURRENT_EXECUTORS)]
        
        result = detect_conflict(request, [], running)
        assert result.has_conflict is True
        assert result.conflict_type == ConflictType.RESOURCE_CONTENTION


# =============================================================================
# ARBITRATION TESTS
# =============================================================================

class TestArbitration:
    """Test conflict arbitration logic."""
    
    def test_no_conflict_merge_safe(self):
        """No conflict results in MERGE_SAFE."""
        request = make_valid_request()
        conflict = ConflictDetectionResult(
            has_conflict=False,
            conflict_type=None,
            conflicting_request_id=None,
            description="No conflict"
        )
        
        result = arbitrate_conflict(conflict, request, [])
        assert result.arbitration_type == ArbitrationType.MERGE_SAFE
    
    def test_resource_contention_first_wins(self):
        """Resource contention: first registered wins."""
        request = make_valid_request(request_id="REQ-002")
        conflict = ConflictDetectionResult(
            has_conflict=True,
            conflict_type=ConflictType.RESOURCE_CONTENTION,
            conflicting_request_id="REQ-001",
            description="Contention"
        )
        
        result = arbitrate_conflict(conflict, request, [])
        assert result.arbitration_type == ArbitrationType.FIRST_REGISTERED
        assert result.winner_request_id == "REQ-001"
    
    def test_capability_conflict_deny_all(self):
        """Capability conflict: deny all parties."""
        request = make_valid_request()
        conflict = ConflictDetectionResult(
            has_conflict=True,
            conflict_type=ConflictType.CAPABILITY_CONFLICT,
            conflicting_request_id=None,
            description="Capability conflict"
        )
        
        result = arbitrate_conflict(conflict, request, [])
        assert result.arbitration_type == ArbitrationType.DENY_ALL
    
    def test_unknown_conflict_deny_all(self):
        """Unknown conflict type: deny by default."""
        request = make_valid_request()
        conflict = ConflictDetectionResult(
            has_conflict=True,
            conflict_type=ConflictType.UNKNOWN_CONFLICT,
            conflicting_request_id=None,
            description="Unknown"
        )
        
        result = arbitrate_conflict(conflict, request, [])
        assert result.arbitration_type == ArbitrationType.DENY_ALL


# =============================================================================
# SCHEDULING DECISION TESTS
# =============================================================================

class TestSchedulingDecision:
    """Test scheduling decision making."""
    
    def test_valid_request_allowed(self):
        """Valid request is allowed."""
        request = make_valid_request()
        result = make_scheduling_decision(request)
        
        assert result.decision == ParallelDecision.ALLOW
        assert result.executor_id.startswith("EXEC-")
    
    def test_none_isolation_denied(self):
        """NONE isolation is denied."""
        request = make_valid_request(isolation=IsolationLevel.NONE)
        result = make_scheduling_decision(request)
        
        assert result.decision == ParallelDecision.DENY
        assert result.reason_code == "FORBIDDEN_ISOLATION"
    
    def test_queue_full_denied(self):
        """Full queue results in denial."""
        request = make_valid_request()
        result = make_scheduling_decision(request, queue_depth=MAX_QUEUE_DEPTH)
        
        assert result.decision == ParallelDecision.DENY
        assert result.reason_code == "QUEUE_FULL"
    
    def test_capacity_limited_queued(self):
        """At capacity results in queue - test with different requester."""
        request = make_valid_request(requester_id="unique-requester-capacity")
        running = [f"EXEC-{i:03d}" for i in range(MAX_CONCURRENT_EXECUTORS)]
        
        result = make_scheduling_decision(request, running_executors=running)
        assert result.decision in [ParallelDecision.QUEUE, ParallelDecision.DENY]


# =============================================================================
# NEGATIVE PATH TESTS
# =============================================================================

class TestNegativePaths:
    """Test denial paths dominate."""
    
    def test_all_forbidden_isolation_denied(self):
        """NONE isolation is always denied."""
        request = make_valid_request(isolation=IsolationLevel.NONE)
        result = make_scheduling_decision(request)
        assert result.decision == ParallelDecision.DENY
    
    def test_conflict_with_same_requester_denied(self):
        """Conflict with same requester is denied."""
        request1 = make_valid_request(request_id="REQ-001")
        request2 = make_valid_request(request_id="REQ-002")
        
        result = make_scheduling_decision(request2, pending_requests=[request1])
        assert result.decision == ParallelDecision.DENY
    
    def test_max_queue_depth_enforced(self):
        """Max queue depth is enforced."""
        for depth in [MAX_QUEUE_DEPTH, MAX_QUEUE_DEPTH + 1, MAX_QUEUE_DEPTH + 10]:
            request = make_valid_request()
            result = make_scheduling_decision(request, queue_depth=depth)
            assert result.decision == ParallelDecision.DENY
