"""
Tests for DecisionResult dataclass - Phase-06.

Tests verify:
- DecisionResult exists and is frozen
- Contains context, decision, reason
- Reason is always non-empty
"""

import pytest
from dataclasses import FrozenInstanceError


class TestDecisionResultExists:
    """Test DecisionResult dataclass existence."""
    
    def test_decision_result_exists(self):
        """DecisionResult must exist."""
        from python.phase06_decision.decision_result import DecisionResult
        assert DecisionResult is not None
    
    def test_decision_result_is_dataclass(self):
        """DecisionResult must be a dataclass."""
        from python.phase06_decision.decision_result import DecisionResult
        from dataclasses import is_dataclass
        assert is_dataclass(DecisionResult)


class TestDecisionResultFields:
    """Test DecisionResult has required fields."""
    
    def test_has_context_field(self):
        """DecisionResult must have context field."""
        from python.phase06_decision.decision_result import DecisionResult
        import dataclasses
        fields = {f.name for f in dataclasses.fields(DecisionResult)}
        assert 'context' in fields
    
    def test_has_decision_field(self):
        """DecisionResult must have decision field."""
        from python.phase06_decision.decision_result import DecisionResult
        import dataclasses
        fields = {f.name for f in dataclasses.fields(DecisionResult)}
        assert 'decision' in fields
    
    def test_has_reason_field(self):
        """DecisionResult must have reason field."""
        from python.phase06_decision.decision_result import DecisionResult
        import dataclasses
        fields = {f.name for f in dataclasses.fields(DecisionResult)}
        assert 'reason' in fields


def _create_action_request():
    """Helper to create a valid ActionRequest."""
    from python.phase02_actors.actors import ActorType
    from python.phase03_trust.trust_zones import TrustZone
    from python.phase04_validation.action_types import ActionType
    from python.phase04_validation.requests import ActionRequest
    
    return ActionRequest(
        actor_type=ActorType.HUMAN,
        action_type=ActionType.READ,
        trust_zone=TrustZone.SYSTEM,
        target="test_resource"
    )


def _create_validation_response(result, reason="Test validation"):
    """Helper to create a valid ValidationResponse."""
    from python.phase04_validation.requests import ValidationResponse
    
    return ValidationResponse(
        request=_create_action_request(),
        result=result,
        reason=reason,
        requires_human=False
    )


def _create_transition_response(current_state, transition, allowed, new_state=None):
    """Helper to create a valid TransitionResponse."""
    from python.phase02_actors.actors import ActorType
    from python.phase05_workflow.state_machine import TransitionRequest, TransitionResponse
    
    request = TransitionRequest(
        current_state=current_state,
        transition=transition,
        actor_type=ActorType.HUMAN
    )
    
    return TransitionResponse(
        request=request,
        allowed=allowed,
        new_state=new_state,
        reason="Test transition"
    )


def _create_decision_context(validation_result, workflow_state, transition, allowed, new_state=None):
    """Helper to create a valid DecisionContext."""
    from python.phase06_decision.decision_context import DecisionContext
    from python.phase02_actors.actors import ActorType
    from python.phase03_trust.trust_zones import TrustZone
    
    return DecisionContext(
        validation_response=_create_validation_response(validation_result),
        transition_response=_create_transition_response(
            workflow_state, transition, allowed, new_state
        ),
        actor_type=ActorType.HUMAN,
        trust_zone=TrustZone.SYSTEM
    )


class TestDecisionResultImmutability:
    """Test DecisionResult is frozen (immutable)."""
    
    def test_decision_result_is_frozen(self):
        """DecisionResult must be frozen."""
        from python.phase06_decision.decision_result import DecisionResult
        from python.phase06_decision.decision_types import FinalDecision
        from python.phase04_validation.validation_results import ValidationResult
        from python.phase05_workflow.states import WorkflowState
        from python.phase05_workflow.transitions import StateTransition
        
        context = _create_decision_context(
            ValidationResult.ALLOW,
            WorkflowState.VALIDATED,
            StateTransition.COMPLETE,
            True,
            WorkflowState.COMPLETED
        )
        
        result = DecisionResult(
            context=context,
            decision=FinalDecision.ALLOW,
            reason="Test reason"
        )
        
        with pytest.raises(FrozenInstanceError):
            result.decision = FinalDecision.DENY


class TestDecisionResultCreation:
    """Test DecisionResult can be created with valid inputs."""
    
    def test_can_create_decision_result(self):
        """Can create DecisionResult with all required fields."""
        from python.phase06_decision.decision_result import DecisionResult
        from python.phase06_decision.decision_types import FinalDecision
        from python.phase04_validation.validation_results import ValidationResult
        from python.phase05_workflow.states import WorkflowState
        from python.phase05_workflow.transitions import StateTransition
        
        context = _create_decision_context(
            ValidationResult.ALLOW,
            WorkflowState.VALIDATED,
            StateTransition.COMPLETE,
            True,
            WorkflowState.COMPLETED
        )
        
        result = DecisionResult(
            context=context,
            decision=FinalDecision.ALLOW,
            reason="All checks passed"
        )
        
        assert result.context == context
        assert result.decision == FinalDecision.ALLOW
        assert result.reason == "All checks passed"
        assert len(result.reason) > 0  # Reason must be non-empty
