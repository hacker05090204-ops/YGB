"""
Tests for DecisionContext dataclass - Phase-06.

Tests verify:
- DecisionContext exists and is frozen
- Contains all required fields
- Cannot be mutated after creation
"""

import pytest
from dataclasses import FrozenInstanceError


class TestDecisionContextExists:
    """Test DecisionContext dataclass existence."""
    
    def test_decision_context_exists(self):
        """DecisionContext must exist."""
        from python.phase06_decision.decision_context import DecisionContext
        assert DecisionContext is not None
    
    def test_decision_context_is_dataclass(self):
        """DecisionContext must be a dataclass."""
        from python.phase06_decision.decision_context import DecisionContext
        from dataclasses import is_dataclass
        assert is_dataclass(DecisionContext)


class TestDecisionContextFields:
    """Test DecisionContext has required fields."""
    
    def test_has_validation_response_field(self):
        """DecisionContext must have validation_response field."""
        from python.phase06_decision.decision_context import DecisionContext
        import dataclasses
        fields = {f.name for f in dataclasses.fields(DecisionContext)}
        assert 'validation_response' in fields
    
    def test_has_transition_response_field(self):
        """DecisionContext must have transition_response field."""
        from python.phase06_decision.decision_context import DecisionContext
        import dataclasses
        fields = {f.name for f in dataclasses.fields(DecisionContext)}
        assert 'transition_response' in fields
    
    def test_has_actor_type_field(self):
        """DecisionContext must have actor_type field."""
        from python.phase06_decision.decision_context import DecisionContext
        import dataclasses
        fields = {f.name for f in dataclasses.fields(DecisionContext)}
        assert 'actor_type' in fields
    
    def test_has_trust_zone_field(self):
        """DecisionContext must have trust_zone field."""
        from python.phase06_decision.decision_context import DecisionContext
        import dataclasses
        fields = {f.name for f in dataclasses.fields(DecisionContext)}
        assert 'trust_zone' in fields


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


class TestDecisionContextImmutability:
    """Test DecisionContext is frozen (immutable)."""
    
    def test_decision_context_is_frozen(self):
        """DecisionContext must be frozen."""
        from python.phase06_decision.decision_context import DecisionContext
        from python.phase02_actors.actors import ActorType
        from python.phase03_trust.trust_zones import TrustZone
        from python.phase04_validation.validation_results import ValidationResult
        from python.phase05_workflow.states import WorkflowState
        from python.phase05_workflow.transitions import StateTransition
        
        validation_response = _create_validation_response(ValidationResult.ALLOW)
        transition_response = _create_transition_response(
            WorkflowState.VALIDATED,
            StateTransition.COMPLETE,
            True,
            WorkflowState.COMPLETED
        )
        
        context = DecisionContext(
            validation_response=validation_response,
            transition_response=transition_response,
            actor_type=ActorType.HUMAN,
            trust_zone=TrustZone.SYSTEM
        )
        
        with pytest.raises(FrozenInstanceError):
            context.actor_type = ActorType.SYSTEM


class TestDecisionContextCreation:
    """Test DecisionContext can be created with valid inputs."""
    
    def test_can_create_decision_context(self):
        """Can create DecisionContext with all required fields."""
        from python.phase06_decision.decision_context import DecisionContext
        from python.phase02_actors.actors import ActorType
        from python.phase03_trust.trust_zones import TrustZone
        from python.phase04_validation.validation_results import ValidationResult
        from python.phase05_workflow.states import WorkflowState
        from python.phase05_workflow.transitions import StateTransition
        
        validation_response = _create_validation_response(ValidationResult.ALLOW)
        transition_response = _create_transition_response(
            WorkflowState.VALIDATED,
            StateTransition.COMPLETE,
            True,
            WorkflowState.COMPLETED
        )
        
        context = DecisionContext(
            validation_response=validation_response,
            transition_response=transition_response,
            actor_type=ActorType.HUMAN,
            trust_zone=TrustZone.SYSTEM
        )
        
        assert context.validation_response == validation_response
        assert context.transition_response == transition_response
        assert context.actor_type == ActorType.HUMAN
        assert context.trust_zone == TrustZone.SYSTEM
