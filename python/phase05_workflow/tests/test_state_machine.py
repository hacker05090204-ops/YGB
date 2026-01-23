"""
Test State Machine - Phase-05 Workflow
REIMPLEMENTED-2026

Tests for state machine transition logic.
These tests are written BEFORE implementation (Test-First).
"""

import pytest


class TestTransitionRequestClass:
    """Tests for TransitionRequest dataclass."""

    def test_transition_request_exists(self):
        """Verify TransitionRequest class exists."""
        from python.phase05_workflow.state_machine import TransitionRequest
        assert TransitionRequest is not None

    def test_transition_request_is_frozen(self):
        """Verify TransitionRequest is frozen dataclass."""
        from python.phase05_workflow.state_machine import TransitionRequest
        from python.phase05_workflow.states import WorkflowState
        from python.phase05_workflow.transitions import StateTransition
        from python.phase02_actors.actors import ActorType
        
        request = TransitionRequest(
            current_state=WorkflowState.INIT,
            transition=StateTransition.VALIDATE,
            actor_type=ActorType.SYSTEM,
        )
        with pytest.raises((AttributeError, TypeError)):
            request.current_state = WorkflowState.VALIDATED


class TestTransitionResponseClass:
    """Tests for TransitionResponse dataclass."""

    def test_transition_response_exists(self):
        """Verify TransitionResponse class exists."""
        from python.phase05_workflow.state_machine import TransitionResponse
        assert TransitionResponse is not None

    def test_transition_response_is_frozen(self):
        """Verify TransitionResponse is frozen dataclass."""
        from python.phase05_workflow.state_machine import TransitionRequest, TransitionResponse
        from python.phase05_workflow.states import WorkflowState
        from python.phase05_workflow.transitions import StateTransition
        from python.phase02_actors.actors import ActorType
        
        request = TransitionRequest(
            current_state=WorkflowState.INIT,
            transition=StateTransition.VALIDATE,
            actor_type=ActorType.HUMAN,
        )
        response = TransitionResponse(
            request=request,
            allowed=True,
            new_state=WorkflowState.VALIDATED,
            reason="Transition allowed",
        )
        with pytest.raises((AttributeError, TypeError)):
            response.allowed = False


class TestAttemptTransitionFunction:
    """Tests for attempt_transition function."""

    def test_attempt_transition_exists(self):
        """Verify attempt_transition function exists."""
        from python.phase05_workflow.state_machine import attempt_transition
        assert attempt_transition is not None


class TestValidTransitions:
    """Tests for valid state transitions."""

    def test_init_to_validated_by_human(self):
        """Verify INIT -> VALIDATED by HUMAN is allowed."""
        from python.phase05_workflow.state_machine import attempt_transition, TransitionRequest
        from python.phase05_workflow.states import WorkflowState
        from python.phase05_workflow.transitions import StateTransition
        from python.phase02_actors.actors import ActorType
        
        request = TransitionRequest(
            current_state=WorkflowState.INIT,
            transition=StateTransition.VALIDATE,
            actor_type=ActorType.HUMAN,
        )
        response = attempt_transition(request)
        assert response.allowed is True
        assert response.new_state == WorkflowState.VALIDATED

    def test_init_to_validated_by_system(self):
        """Verify INIT -> VALIDATED by SYSTEM is allowed."""
        from python.phase05_workflow.state_machine import attempt_transition, TransitionRequest
        from python.phase05_workflow.states import WorkflowState
        from python.phase05_workflow.transitions import StateTransition
        from python.phase02_actors.actors import ActorType
        
        request = TransitionRequest(
            current_state=WorkflowState.INIT,
            transition=StateTransition.VALIDATE,
            actor_type=ActorType.SYSTEM,
        )
        response = attempt_transition(request)
        assert response.allowed is True
        assert response.new_state == WorkflowState.VALIDATED

    def test_validated_to_escalated(self):
        """Verify VALIDATED -> ESCALATED is allowed."""
        from python.phase05_workflow.state_machine import attempt_transition, TransitionRequest
        from python.phase05_workflow.states import WorkflowState
        from python.phase05_workflow.transitions import StateTransition
        from python.phase02_actors.actors import ActorType
        
        request = TransitionRequest(
            current_state=WorkflowState.VALIDATED,
            transition=StateTransition.ESCALATE,
            actor_type=ActorType.SYSTEM,
        )
        response = attempt_transition(request)
        assert response.allowed is True
        assert response.new_state == WorkflowState.ESCALATED

    def test_escalated_to_approved_by_human(self):
        """Verify ESCALATED -> APPROVED by HUMAN is allowed."""
        from python.phase05_workflow.state_machine import attempt_transition, TransitionRequest
        from python.phase05_workflow.states import WorkflowState
        from python.phase05_workflow.transitions import StateTransition
        from python.phase02_actors.actors import ActorType
        
        request = TransitionRequest(
            current_state=WorkflowState.ESCALATED,
            transition=StateTransition.APPROVE,
            actor_type=ActorType.HUMAN,
        )
        response = attempt_transition(request)
        assert response.allowed is True
        assert response.new_state == WorkflowState.APPROVED

    def test_escalated_to_rejected_by_human(self):
        """Verify ESCALATED -> REJECTED by HUMAN is allowed."""
        from python.phase05_workflow.state_machine import attempt_transition, TransitionRequest
        from python.phase05_workflow.states import WorkflowState
        from python.phase05_workflow.transitions import StateTransition
        from python.phase02_actors.actors import ActorType
        
        request = TransitionRequest(
            current_state=WorkflowState.ESCALATED,
            transition=StateTransition.REJECT,
            actor_type=ActorType.HUMAN,
        )
        response = attempt_transition(request)
        assert response.allowed is True
        assert response.new_state == WorkflowState.REJECTED

    def test_approved_to_completed(self):
        """Verify APPROVED -> COMPLETED is allowed."""
        from python.phase05_workflow.state_machine import attempt_transition, TransitionRequest
        from python.phase05_workflow.states import WorkflowState
        from python.phase05_workflow.transitions import StateTransition
        from python.phase02_actors.actors import ActorType
        
        request = TransitionRequest(
            current_state=WorkflowState.APPROVED,
            transition=StateTransition.COMPLETE,
            actor_type=ActorType.SYSTEM,
        )
        response = attempt_transition(request)
        assert response.allowed is True
        assert response.new_state == WorkflowState.COMPLETED

    def test_validated_to_completed_by_human(self):
        """Verify VALIDATED -> COMPLETED by HUMAN is allowed (skip escalation)."""
        from python.phase05_workflow.state_machine import attempt_transition, TransitionRequest
        from python.phase05_workflow.states import WorkflowState
        from python.phase05_workflow.transitions import StateTransition
        from python.phase02_actors.actors import ActorType
        
        request = TransitionRequest(
            current_state=WorkflowState.VALIDATED,
            transition=StateTransition.COMPLETE,
            actor_type=ActorType.HUMAN,
        )
        response = attempt_transition(request)
        assert response.allowed is True
        assert response.new_state == WorkflowState.COMPLETED


class TestAbortTransitions:
    """Tests for ABORT transitions (HUMAN only)."""

    def test_init_abort_by_human(self):
        """Verify INIT -> ABORTED by HUMAN is allowed."""
        from python.phase05_workflow.state_machine import attempt_transition, TransitionRequest
        from python.phase05_workflow.states import WorkflowState
        from python.phase05_workflow.transitions import StateTransition
        from python.phase02_actors.actors import ActorType
        
        request = TransitionRequest(
            current_state=WorkflowState.INIT,
            transition=StateTransition.ABORT,
            actor_type=ActorType.HUMAN,
        )
        response = attempt_transition(request)
        assert response.allowed is True
        assert response.new_state == WorkflowState.ABORTED

    def test_validated_abort_by_human(self):
        """Verify VALIDATED -> ABORTED by HUMAN is allowed."""
        from python.phase05_workflow.state_machine import attempt_transition, TransitionRequest
        from python.phase05_workflow.states import WorkflowState
        from python.phase05_workflow.transitions import StateTransition
        from python.phase02_actors.actors import ActorType
        
        request = TransitionRequest(
            current_state=WorkflowState.VALIDATED,
            transition=StateTransition.ABORT,
            actor_type=ActorType.HUMAN,
        )
        response = attempt_transition(request)
        assert response.allowed is True

    def test_escalated_abort_by_human(self):
        """Verify ESCALATED -> ABORTED by HUMAN is allowed."""
        from python.phase05_workflow.state_machine import attempt_transition, TransitionRequest
        from python.phase05_workflow.states import WorkflowState
        from python.phase05_workflow.transitions import StateTransition
        from python.phase02_actors.actors import ActorType
        
        request = TransitionRequest(
            current_state=WorkflowState.ESCALATED,
            transition=StateTransition.ABORT,
            actor_type=ActorType.HUMAN,
        )
        response = attempt_transition(request)
        assert response.allowed is True

    def test_approved_abort_by_human(self):
        """Verify APPROVED -> ABORTED by HUMAN is allowed."""
        from python.phase05_workflow.state_machine import attempt_transition, TransitionRequest
        from python.phase05_workflow.states import WorkflowState
        from python.phase05_workflow.transitions import StateTransition
        from python.phase02_actors.actors import ActorType
        
        request = TransitionRequest(
            current_state=WorkflowState.APPROVED,
            transition=StateTransition.ABORT,
            actor_type=ActorType.HUMAN,
        )
        response = attempt_transition(request)
        assert response.allowed is True


class TestSystemCannotApproveOrReject:
    """Tests to verify SYSTEM cannot approve or reject."""

    def test_system_cannot_approve(self):
        """Verify SYSTEM cannot approve."""
        from python.phase05_workflow.state_machine import attempt_transition, TransitionRequest
        from python.phase05_workflow.states import WorkflowState
        from python.phase05_workflow.transitions import StateTransition
        from python.phase02_actors.actors import ActorType
        
        request = TransitionRequest(
            current_state=WorkflowState.ESCALATED,
            transition=StateTransition.APPROVE,
            actor_type=ActorType.SYSTEM,
        )
        response = attempt_transition(request)
        assert response.allowed is False

    def test_system_cannot_reject(self):
        """Verify SYSTEM cannot reject."""
        from python.phase05_workflow.state_machine import attempt_transition, TransitionRequest
        from python.phase05_workflow.states import WorkflowState
        from python.phase05_workflow.transitions import StateTransition
        from python.phase02_actors.actors import ActorType
        
        request = TransitionRequest(
            current_state=WorkflowState.ESCALATED,
            transition=StateTransition.REJECT,
            actor_type=ActorType.SYSTEM,
        )
        response = attempt_transition(request)
        assert response.allowed is False

    def test_system_cannot_abort(self):
        """Verify SYSTEM cannot abort."""
        from python.phase05_workflow.state_machine import attempt_transition, TransitionRequest
        from python.phase05_workflow.states import WorkflowState
        from python.phase05_workflow.transitions import StateTransition
        from python.phase02_actors.actors import ActorType
        
        request = TransitionRequest(
            current_state=WorkflowState.INIT,
            transition=StateTransition.ABORT,
            actor_type=ActorType.SYSTEM,
        )
        response = attempt_transition(request)
        assert response.allowed is False


class TestDenyByDefault:
    """Tests for deny-by-default behavior."""

    def test_invalid_transition_from_completed(self):
        """Verify transitions from COMPLETED are denied."""
        from python.phase05_workflow.state_machine import attempt_transition, TransitionRequest
        from python.phase05_workflow.states import WorkflowState
        from python.phase05_workflow.transitions import StateTransition
        from python.phase02_actors.actors import ActorType
        
        request = TransitionRequest(
            current_state=WorkflowState.COMPLETED,
            transition=StateTransition.VALIDATE,
            actor_type=ActorType.HUMAN,
        )
        response = attempt_transition(request)
        assert response.allowed is False

    def test_invalid_transition_from_aborted(self):
        """Verify transitions from ABORTED are denied."""
        from python.phase05_workflow.state_machine import attempt_transition, TransitionRequest
        from python.phase05_workflow.states import WorkflowState
        from python.phase05_workflow.transitions import StateTransition
        from python.phase02_actors.actors import ActorType
        
        request = TransitionRequest(
            current_state=WorkflowState.ABORTED,
            transition=StateTransition.VALIDATE,
            actor_type=ActorType.HUMAN,
        )
        response = attempt_transition(request)
        assert response.allowed is False

    def test_invalid_transition_from_rejected(self):
        """Verify transitions from REJECTED are denied."""
        from python.phase05_workflow.state_machine import attempt_transition, TransitionRequest
        from python.phase05_workflow.states import WorkflowState
        from python.phase05_workflow.transitions import StateTransition
        from python.phase02_actors.actors import ActorType
        
        request = TransitionRequest(
            current_state=WorkflowState.REJECTED,
            transition=StateTransition.APPROVE,
            actor_type=ActorType.HUMAN,
        )
        response = attempt_transition(request)
        assert response.allowed is False

    def test_system_cannot_complete_from_validated(self):
        """Verify SYSTEM cannot complete from VALIDATED (needs human)."""
        from python.phase05_workflow.state_machine import attempt_transition, TransitionRequest
        from python.phase05_workflow.states import WorkflowState
        from python.phase05_workflow.transitions import StateTransition
        from python.phase02_actors.actors import ActorType
        
        request = TransitionRequest(
            current_state=WorkflowState.VALIDATED,
            transition=StateTransition.COMPLETE,
            actor_type=ActorType.SYSTEM,
        )
        response = attempt_transition(request)
        assert response.allowed is False

    def test_invalid_validate_from_validated(self):
        """Verify VALIDATE from VALIDATED is denied (not in transition table)."""
        from python.phase05_workflow.state_machine import attempt_transition, TransitionRequest
        from python.phase05_workflow.states import WorkflowState
        from python.phase05_workflow.transitions import StateTransition
        from python.phase02_actors.actors import ActorType
        
        request = TransitionRequest(
            current_state=WorkflowState.VALIDATED,
            transition=StateTransition.VALIDATE,
            actor_type=ActorType.HUMAN,
        )
        response = attempt_transition(request)
        assert response.allowed is False
        assert "not valid" in response.reason


class TestResponseIncludesReason:
    """Tests for response reason field."""

    def test_allowed_response_has_reason(self):
        """Verify allowed response includes reason."""
        from python.phase05_workflow.state_machine import attempt_transition, TransitionRequest
        from python.phase05_workflow.states import WorkflowState
        from python.phase05_workflow.transitions import StateTransition
        from python.phase02_actors.actors import ActorType
        
        request = TransitionRequest(
            current_state=WorkflowState.INIT,
            transition=StateTransition.VALIDATE,
            actor_type=ActorType.HUMAN,
        )
        response = attempt_transition(request)
        assert len(response.reason) > 0

    def test_denied_response_has_reason(self):
        """Verify denied response includes reason."""
        from python.phase05_workflow.state_machine import attempt_transition, TransitionRequest
        from python.phase05_workflow.states import WorkflowState
        from python.phase05_workflow.transitions import StateTransition
        from python.phase02_actors.actors import ActorType
        
        request = TransitionRequest(
            current_state=WorkflowState.COMPLETED,
            transition=StateTransition.VALIDATE,
            actor_type=ActorType.HUMAN,
        )
        response = attempt_transition(request)
        assert len(response.reason) > 0


class TestNoForbiddenBehavior:
    """Tests to verify no forbidden behavior."""

    def test_no_auto_advance_method(self):
        """Verify no auto_advance method exists."""
        import python.phase05_workflow.state_machine as sm
        assert not hasattr(sm, 'auto_advance')

    def test_no_skip_validation_method(self):
        """Verify no skip_validation method exists."""
        import python.phase05_workflow.state_machine as sm
        assert not hasattr(sm, 'skip_validation')

    def test_no_force_complete_method(self):
        """Verify no force_complete method exists."""
        import python.phase05_workflow.state_machine as sm
        assert not hasattr(sm, 'force_complete')


class TestNoFuturePhaseCoupling:
    """Tests to verify no future phase coupling."""

    def test_no_phase06_imports(self):
        """Verify no Phase-06+ imports in Phase-05."""
        from pathlib import Path
        
        phase05_path = Path(__file__).parent.parent
        for py_file in phase05_path.glob('*.py'):
            content = py_file.read_text()
            assert 'phase06' not in content.lower()
            assert 'phase07' not in content.lower()

    def test_no_network_imports(self):
        """Verify Phase-05 has no network imports."""
        from pathlib import Path
        import re
        
        phase05_path = Path(__file__).parent.parent
        for py_file in phase05_path.glob('*.py'):
            content = py_file.read_text()
            matches = re.findall(r'\bimport\s+(?:socket|requests|urllib|http)\b', content)
            assert len(matches) == 0

    def test_no_subprocess_imports(self):
        """Verify Phase-05 has no subprocess imports."""
        from pathlib import Path
        import re
        
        phase05_path = Path(__file__).parent.parent
        for py_file in phase05_path.glob('*.py'):
            content = py_file.read_text()
            matches = re.findall(r'\bimport\s+subprocess\b', content)
            assert len(matches) == 0
