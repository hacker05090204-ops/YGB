# AMSE Tests: Adaptive Method Synthesis Engine
"""
CRITICAL TESTS for method synthesis.
- Human approval mandatory
- No silent autonomy
- Full audit trail
"""

import pytest
from impl_v1.amse.amse_types import *
from impl_v1.amse.amse_engine import *


class TestEnumClosure:
    """Verify all enums are CLOSED."""
    def test_method_state_6(self): assert len(MethodState) == 6
    def test_method_confidence_5(self): assert len(MethodConfidence) == 5
    def test_synthesis_reason_5(self): assert len(SynthesisReason) == 5
    def test_failure_mode_8(self): assert len(FailureMode) == 8
    def test_applicability_scope_4(self): assert len(ApplicabilityScope) == 4


class TestDataclassFrozen:
    """Verify all dataclasses are frozen."""
    def test_synthesized_method_frozen(self):
        method = SynthesizedMethod(
            method_id="M-001", name="test", description="test method",
            reason=SynthesisReason.ALL_METHODS_FAILED,
            preconditions=(), assumptions=(), applicability=ApplicabilityScope.EXPERIMENTAL,
            failure_modes=(), confidence=MethodConfidence.LOW,
            state=MethodState.PROPOSED, created_at="2026-01-27",
            human_reviewed=False, human_reviewer_id=None,
        )
        with pytest.raises(AttributeError):
            method.state = MethodState.APPROVED


class TestSynthesis:
    """Test method synthesis."""
    
    def setup_method(self):
        clear_registry()
    
    def test_synthesize_requires_description(self):
        result = synthesize_method(
            name="test",
            description="",  # Empty - should fail
            reason=SynthesisReason.ALL_METHODS_FAILED,
            preconditions=[MethodPrecondition("P-1", "test", True, True)],
            assumptions=[],
            failure_modes=[],
        )
        assert result is None
    
    def test_synthesize_requires_preconditions(self):
        result = synthesize_method(
            name="test",
            description="A valid description here",
            reason=SynthesisReason.ALL_METHODS_FAILED,
            preconditions=[],  # Empty - should fail for this reason
            assumptions=[],
            failure_modes=[],
        )
        assert result is None
    
    def test_synthesize_creates_pending_method(self):
        precond = MethodPrecondition("P-1", "Target must be accessible", True, True)
        assumption = MethodAssumption("A-1", "Target uses standard HTTP", MethodConfidence.HIGH)
        
        method = synthesize_method(
            name="HTTP Header Check",
            description="Check for missing security headers",
            reason=SynthesisReason.ALL_METHODS_FAILED,
            preconditions=[precond],
            assumptions=[assumption],
            failure_modes=[FailureMode.FALSE_POSITIVE],
        )
        
        assert method is not None
        assert method.state == MethodState.PENDING_HUMAN
        assert method.human_reviewed is False


class TestHumanApproval:
    """Test mandatory human approval."""
    
    def setup_method(self):
        clear_registry()
    
    def _create_method(self) -> SynthesizedMethod:
        precond = MethodPrecondition("P-1", "Test precondition", True, True)
        assumption = MethodAssumption("A-1", "Test assumption", MethodConfidence.HIGH)
        return synthesize_method(
            name="Test Method",
            description="A test method for approval",
            reason=SynthesisReason.ALL_METHODS_FAILED,
            preconditions=[precond],
            assumptions=[assumption],
            failure_modes=[FailureMode.FALSE_POSITIVE],
        )
    
    def test_approval_changes_state(self):
        method = self._create_method()
        assert method.state == MethodState.PENDING_HUMAN
        
        approved = approve_method(method.method_id, "human-reviewer-001")
        
        assert approved is not None
        assert approved.state == MethodState.APPROVED
        assert approved.human_reviewed is True
        assert approved.human_reviewer_id == "human-reviewer-001"
    
    def test_rejection_changes_state(self):
        method = self._create_method()
        
        rejected = reject_method(method.method_id, "human-reviewer-001", "Too risky")
        
        assert rejected is not None
        assert rejected.state == MethodState.REJECTED
        assert rejected.human_reviewed is True
    
    def test_cannot_approve_nonexistent(self):
        result = approve_method("MTH-NOTEXIST", "reviewer")
        assert result is None
    
    def test_cannot_approve_already_approved(self):
        method = self._create_method()
        approve_method(method.method_id, "reviewer-1")
        
        # Try to approve again
        result = approve_method(method.method_id, "reviewer-2")
        assert result is None


class TestAuditLog:
    """Test audit logging."""
    
    def setup_method(self):
        clear_registry()
    
    def test_synthesis_logged(self):
        precond = MethodPrecondition("P-1", "Test", True, True)
        synthesize_method(
            name="Test",
            description="Test method test",
            reason=SynthesisReason.CONTEXT_NOVEL,
            preconditions=[precond],
            assumptions=[],
            failure_modes=[],
        )
        
        log = get_audit_log()
        assert len(log) >= 1
        assert log[0].event_type == "PROPOSED"
    
    def test_approval_logged(self):
        precond = MethodPrecondition("P-1", "Test", True, True)
        method = synthesize_method(
            name="Test",
            description="Test method test",
            reason=SynthesisReason.CONTEXT_NOVEL,
            preconditions=[precond],
            assumptions=[],
            failure_modes=[],
        )
        
        approve_method(method.method_id, "reviewer")
        
        log = get_audit_log()
        assert any(e.event_type == "APPROVED" for e in log)


class TestExecutionPlan:
    """Test execution plan creation."""
    
    def setup_method(self):
        clear_registry()
    
    def test_plan_requires_approval(self):
        precond = MethodPrecondition("P-1", "Test", True, True)
        method = synthesize_method(
            name="Test",
            description="Test method test",
            reason=SynthesisReason.CONTEXT_NOVEL,
            preconditions=[precond],
            assumptions=[],
            failure_modes=[],
        )
        
        # Method not yet approved
        plan = create_execution_plan(
            method.method_id, ["Step 1"], 60, ["CPU"], ["Rollback"]
        )
        assert plan is None
    
    def test_plan_for_approved_method(self):
        precond = MethodPrecondition("P-1", "Test", True, True)
        method = synthesize_method(
            name="Test",
            description="Test method test",
            reason=SynthesisReason.CONTEXT_NOVEL,
            preconditions=[precond],
            assumptions=[],
            failure_modes=[],
        )
        
        approve_method(method.method_id, "reviewer")
        
        plan = create_execution_plan(
            method.method_id,
            ["Step 1: Check", "Step 2: Execute"],
            120,
            ["CPU", "Memory"],
            ["Rollback step 1"],
        )
        
        assert plan is not None
        assert plan.plan_id.startswith("PLN-")
        assert len(plan.steps) == 2


class TestConfidence:
    """Test confidence calculation."""
    
    def test_no_assumptions_experimental(self):
        conf = calculate_confidence([], [])
        assert conf == MethodConfidence.EXPERIMENTAL
    
    def test_high_confidence_assumptions(self):
        assumptions = [
            MethodAssumption("A-1", "Test", MethodConfidence.VERY_HIGH),
            MethodAssumption("A-2", "Test", MethodConfidence.HIGH),
        ]
        conf = calculate_confidence(assumptions, [FailureMode.FALSE_POSITIVE])
        assert conf == MethodConfidence.HIGH
    
    def test_many_failure_modes_reduces_confidence(self):
        assumptions = [
            MethodAssumption("A-1", "Test", MethodConfidence.VERY_HIGH),
        ]
        many_failures = [FailureMode.FALSE_POSITIVE] * 6
        conf = calculate_confidence(assumptions, many_failures)
        # Penalty should reduce confidence
        assert conf in [MethodConfidence.MEDIUM, MethodConfidence.LOW]


class TestNoSilentAutonomy:
    """CRITICAL: Verify no silent autonomy."""
    
    def setup_method(self):
        clear_registry()
    
    def test_synthesized_method_not_auto_approved(self):
        """Synthesized methods must NEVER be auto-approved."""
        precond = MethodPrecondition("P-1", "Test", True, True)
        method = synthesize_method(
            name="Test",
            description="Test method test",
            reason=SynthesisReason.ALL_METHODS_FAILED,
            preconditions=[precond],
            assumptions=[],
            failure_modes=[],
        )
        
        # State must be PENDING_HUMAN, never APPROVED
        assert method.state == MethodState.PENDING_HUMAN
        assert method.state != MethodState.APPROVED
    
    def test_execution_blocked_without_approval(self):
        """Execution plans cannot be created without human approval."""
        precond = MethodPrecondition("P-1", "Test", True, True)
        method = synthesize_method(
            name="Test",
            description="Test method test",
            reason=SynthesisReason.ALL_METHODS_FAILED,
            preconditions=[precond],
            assumptions=[],
            failure_modes=[],
        )
        
        plan = create_execution_plan(method.method_id, ["Step"], 60, [], [])
        assert plan is None  # Blocked!
