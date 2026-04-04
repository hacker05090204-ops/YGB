"""
Tests for resolve_decision function - Phase-06.

Tests verify:
- HUMAN override always wins
- Terminal workflow blocks all decisions
- DENY by default for unknown combinations
- ESCALATE propagation
- SYSTEM cannot ALLOW critical decisions
- Reasons are non-empty
- No forbidden imports
- No phase07+ imports
"""

import pytest
import os


# Helper functions for creating valid test objects

def _create_action_request(actor_type=None, action_type=None, trust_zone=None):
    """Helper to create a valid ActionRequest."""
    from python.phase02_actors.actors import ActorType
    from python.phase03_trust.trust_zones import TrustZone
    from python.phase04_validation.action_types import ActionType
    from python.phase04_validation.requests import ActionRequest
    
    return ActionRequest(
        actor_type=actor_type or ActorType.HUMAN,
        action_type=action_type or ActionType.READ,
        trust_zone=trust_zone or TrustZone.SYSTEM,
        target="test_resource"
    )


def _create_validation_response(result, reason="Test validation", requires_human=False):
    """Helper to create a valid ValidationResponse."""
    from python.phase04_validation.requests import ValidationResponse
    
    return ValidationResponse(
        request=_create_action_request(),
        result=result,
        reason=reason,
        requires_human=requires_human
    )


def _create_transition_request(current_state, transition, actor_type=None):
    """Helper to create a valid TransitionRequest."""
    from python.phase02_actors.actors import ActorType
    from python.phase05_workflow.state_machine import TransitionRequest
    
    return TransitionRequest(
        current_state=current_state,
        transition=transition,
        actor_type=actor_type or ActorType.HUMAN
    )


def _create_transition_response(current_state, transition, allowed, new_state=None, actor_type=None):
    """Helper to create a valid TransitionResponse."""
    from python.phase05_workflow.state_machine import TransitionResponse
    
    return TransitionResponse(
        request=_create_transition_request(current_state, transition, actor_type),
        allowed=allowed,
        new_state=new_state,
        reason="Test transition"
    )


def _create_decision_context(
    validation_result,
    current_state,
    transition,
    allowed,
    new_state=None,
    actor_type=None,
    trust_zone=None
):
    """Helper to create a valid DecisionContext."""
    from python.phase02_actors.actors import ActorType
    from python.phase03_trust.trust_zones import TrustZone
    from python.phase06_decision.decision_context import DecisionContext
    
    return DecisionContext(
        validation_response=_create_validation_response(validation_result),
        transition_response=_create_transition_response(
            current_state, transition, allowed, new_state, actor_type
        ),
        actor_type=actor_type or ActorType.HUMAN,
        trust_zone=trust_zone or TrustZone.SYSTEM
    )


class TestResolveFunctionExists:
    """Test resolve_decision function exists."""
    
    def test_resolve_decision_exists(self):
        """resolve_decision function must exist."""
        from python.phase06_decision.decision_engine import resolve_decision
        assert resolve_decision is not None
        assert callable(resolve_decision)


class TestHumanOverrideAlwaysWins:
    """Test that HUMAN authority always overrides."""
    
    def test_human_allow_overrides_system(self):
        """HUMAN with ALLOW validation always gets ALLOW."""
        from python.phase06_decision.decision_engine import resolve_decision
        from python.phase06_decision.decision_types import FinalDecision
        from python.phase02_actors.actors import ActorType
        from python.phase04_validation.validation_results import ValidationResult
        from python.phase05_workflow.states import WorkflowState
        from python.phase05_workflow.transitions import StateTransition
        
        context = _create_decision_context(
            validation_result=ValidationResult.ALLOW,
            current_state=WorkflowState.VALIDATED,
            transition=StateTransition.COMPLETE,
            allowed=True,
            new_state=WorkflowState.COMPLETED,
            actor_type=ActorType.HUMAN
        )
        
        result = resolve_decision(context)
        
        assert result.decision == FinalDecision.ALLOW
        assert "HUMAN" in result.reason


class TestTerminalWorkflowBlocks:
    """Test that terminal workflow states block all decisions."""
    
    def test_completed_state_denies(self):
        """COMPLETED workflow state results in DENY."""
        from python.phase06_decision.decision_engine import resolve_decision
        from python.phase06_decision.decision_types import FinalDecision
        from python.phase02_actors.actors import ActorType
        from python.phase04_validation.validation_results import ValidationResult
        from python.phase05_workflow.states import WorkflowState
        from python.phase05_workflow.transitions import StateTransition
        
        context = _create_decision_context(
            validation_result=ValidationResult.ALLOW,
            current_state=WorkflowState.COMPLETED,
            transition=StateTransition.COMPLETE,
            allowed=False,
            new_state=None,
            actor_type=ActorType.HUMAN
        )
        
        result = resolve_decision(context)
        
        assert result.decision == FinalDecision.DENY
        assert "terminal" in result.reason.lower() or "COMPLETED" in result.reason
    
    def test_aborted_state_denies(self):
        """ABORTED workflow state results in DENY."""
        from python.phase06_decision.decision_engine import resolve_decision
        from python.phase06_decision.decision_types import FinalDecision
        from python.phase02_actors.actors import ActorType
        from python.phase04_validation.validation_results import ValidationResult
        from python.phase05_workflow.states import WorkflowState
        from python.phase05_workflow.transitions import StateTransition
        
        context = _create_decision_context(
            validation_result=ValidationResult.ALLOW,
            current_state=WorkflowState.ABORTED,
            transition=StateTransition.COMPLETE,
            allowed=False,
            actor_type=ActorType.HUMAN
        )
        
        result = resolve_decision(context)
        
        assert result.decision == FinalDecision.DENY
    
    def test_rejected_state_denies(self):
        """REJECTED workflow state results in DENY."""
        from python.phase06_decision.decision_engine import resolve_decision
        from python.phase06_decision.decision_types import FinalDecision
        from python.phase02_actors.actors import ActorType
        from python.phase04_validation.validation_results import ValidationResult
        from python.phase05_workflow.states import WorkflowState
        from python.phase05_workflow.transitions import StateTransition
        
        context = _create_decision_context(
            validation_result=ValidationResult.ALLOW,
            current_state=WorkflowState.REJECTED,
            transition=StateTransition.COMPLETE,
            allowed=False,
            actor_type=ActorType.HUMAN
        )
        
        result = resolve_decision(context)
        
        assert result.decision == FinalDecision.DENY


class TestTransitionDenied:
    """Test that denied transitions result in DENY."""
    
    def test_transition_denied_results_in_deny(self):
        """If workflow transition is denied, result is DENY."""
        from python.phase06_decision.decision_engine import resolve_decision
        from python.phase06_decision.decision_types import FinalDecision
        from python.phase02_actors.actors import ActorType
        from python.phase04_validation.validation_results import ValidationResult
        from python.phase05_workflow.states import WorkflowState
        from python.phase05_workflow.transitions import StateTransition
        
        context = _create_decision_context(
            validation_result=ValidationResult.ALLOW,
            current_state=WorkflowState.INIT,
            transition=StateTransition.COMPLETE,  # Invalid transition
            allowed=False,
            actor_type=ActorType.HUMAN
        )
        
        result = resolve_decision(context)
        
        assert result.decision == FinalDecision.DENY


class TestEscalatePropagation:
    """Test that ESCALATE from validation propagates."""
    
    def test_validation_escalate_results_in_escalate(self):
        """If validation returns ESCALATE, result is ESCALATE."""
        from python.phase06_decision.decision_engine import resolve_decision
        from python.phase06_decision.decision_types import FinalDecision
        from python.phase02_actors.actors import ActorType
        from python.phase04_validation.validation_results import ValidationResult
        from python.phase05_workflow.states import WorkflowState
        from python.phase05_workflow.transitions import StateTransition
        
        context = _create_decision_context(
            validation_result=ValidationResult.ESCALATE,
            current_state=WorkflowState.VALIDATED,
            transition=StateTransition.ESCALATE,
            allowed=True,
            new_state=WorkflowState.ESCALATED,
            actor_type=ActorType.SYSTEM
        )
        
        result = resolve_decision(context)
        
        assert result.decision == FinalDecision.ESCALATE


class TestValidationDeny:
    """Test that validation DENY results in DENY."""
    
    def test_validation_deny_results_in_deny(self):
        """If validation returns DENY, result is DENY."""
        from python.phase06_decision.decision_engine import resolve_decision
        from python.phase06_decision.decision_types import FinalDecision
        from python.phase02_actors.actors import ActorType
        from python.phase04_validation.validation_results import ValidationResult
        from python.phase05_workflow.states import WorkflowState
        from python.phase05_workflow.transitions import StateTransition
        
        context = _create_decision_context(
            validation_result=ValidationResult.DENY,
            current_state=WorkflowState.VALIDATED,
            transition=StateTransition.COMPLETE,
            allowed=True,
            new_state=WorkflowState.COMPLETED,
            actor_type=ActorType.HUMAN
        )
        
        result = resolve_decision(context)
        
        assert result.decision == FinalDecision.DENY


class TestUntrustedZone:
    """Test that untrusted zone requires escalation."""
    
    def test_untrusted_zone_escalates(self):
        """Untrusted zone with SYSTEM actor requires ESCALATE."""
        from python.phase06_decision.decision_engine import resolve_decision
        from python.phase06_decision.decision_types import FinalDecision
        from python.phase02_actors.actors import ActorType
        from python.phase03_trust.trust_zones import TrustZone
        from python.phase04_validation.validation_results import ValidationResult
        from python.phase05_workflow.states import WorkflowState
        from python.phase05_workflow.transitions import StateTransition
        
        context = _create_decision_context(
            validation_result=ValidationResult.ALLOW,
            current_state=WorkflowState.VALIDATED,
            transition=StateTransition.ESCALATE,
            allowed=True,
            new_state=WorkflowState.ESCALATED,
            actor_type=ActorType.SYSTEM,
            trust_zone=TrustZone.EXTERNAL
        )
        
        result = resolve_decision(context)
        
        assert result.decision == FinalDecision.ESCALATE


class TestDenyByDefault:
    """Test deny-by-default behavior."""
    
    def test_system_with_allow_and_valid_transition_allows(self):
        """SYSTEM with ALLOW and valid transition gets ALLOW if all checks pass."""
        from python.phase06_decision.decision_engine import resolve_decision
        from python.phase06_decision.decision_types import FinalDecision
        from python.phase02_actors.actors import ActorType
        from python.phase04_validation.validation_results import ValidationResult
        from python.phase05_workflow.states import WorkflowState
        from python.phase05_workflow.transitions import StateTransition
        
        context = _create_decision_context(
            validation_result=ValidationResult.ALLOW,
            current_state=WorkflowState.APPROVED,
            transition=StateTransition.COMPLETE,
            allowed=True,
            new_state=WorkflowState.COMPLETED,
            actor_type=ActorType.SYSTEM
        )
        
        result = resolve_decision(context)
        
        # SYSTEM can get ALLOW if all conditions pass
        assert result.decision == FinalDecision.ALLOW


class TestExplicitReasons:
    """Test that all decisions have explicit non-empty reasons."""
    
    def test_allow_has_reason(self):
        """ALLOW decision has non-empty reason."""
        from python.phase06_decision.decision_engine import resolve_decision
        from python.phase02_actors.actors import ActorType
        from python.phase04_validation.validation_results import ValidationResult
        from python.phase05_workflow.states import WorkflowState
        from python.phase05_workflow.transitions import StateTransition
        
        context = _create_decision_context(
            validation_result=ValidationResult.ALLOW,
            current_state=WorkflowState.VALIDATED,
            transition=StateTransition.COMPLETE,
            allowed=True,
            new_state=WorkflowState.COMPLETED,
            actor_type=ActorType.HUMAN
        )
        
        result = resolve_decision(context)
        
        assert result.reason is not None
        assert len(result.reason) > 0
    
    def test_deny_has_reason(self):
        """DENY decision has non-empty reason."""
        from python.phase06_decision.decision_engine import resolve_decision
        from python.phase04_validation.validation_results import ValidationResult
        from python.phase05_workflow.states import WorkflowState
        from python.phase05_workflow.transitions import StateTransition
        
        context = _create_decision_context(
            validation_result=ValidationResult.DENY,
            current_state=WorkflowState.VALIDATED,
            transition=StateTransition.COMPLETE,
            allowed=True,
            new_state=WorkflowState.COMPLETED
        )
        
        result = resolve_decision(context)
        
        assert result.reason is not None
        assert len(result.reason) > 0


class TestNoForbiddenImports:
    """Test that implementation has no forbidden imports."""
    
    def test_no_os_import(self):
        """No os import in decision_engine.py."""
        engine_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            'decision_engine.py'
        )
        with open(engine_path, 'r') as f:
            content = f.read()
        assert 'import os' not in content
    
    def test_no_subprocess_import(self):
        """No subprocess import."""
        engine_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            'decision_engine.py'
        )
        with open(engine_path, 'r') as f:
            content = f.read()
        assert 'import subprocess' not in content
    
    def test_no_socket_import(self):
        """No socket import."""
        engine_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            'decision_engine.py'
        )
        with open(engine_path, 'r') as f:
            content = f.read()
        assert 'import socket' not in content
    
    def test_no_asyncio_import(self):
        """No asyncio import."""
        engine_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            'decision_engine.py'
        )
        with open(engine_path, 'r') as f:
            content = f.read()
        assert 'import asyncio' not in content
    
    def test_no_threading_import(self):
        """No threading import."""
        engine_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            'decision_engine.py'
        )
        with open(engine_path, 'r') as f:
            content = f.read()
        assert 'import threading' not in content


class TestNoFuturePhaseCoupling:
    """Test that no phase07+ imports exist."""
    
    def test_no_phase07_import(self):
        """No phase07 imports in any Phase-06 file."""
        phase06_dir = os.path.dirname(os.path.dirname(__file__))
        for filename in os.listdir(phase06_dir):
            if filename.endswith('.py'):
                filepath = os.path.join(phase06_dir, filename)
                with open(filepath, 'r') as f:
                    content = f.read().lower()
                assert 'phase07' not in content, f"Found phase07 in {filename}"
                assert 'phase08' not in content, f"Found phase08 in {filename}"


class TestNoExecuteMethod:
    """Test that no execute methods exist."""
    
    def test_no_execute_function(self):
        """No execute or auto_execute function."""
        engine_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            'decision_engine.py'
        )
        with open(engine_path, 'r') as f:
            content = f.read()
        assert 'def execute' not in content.lower()
        assert 'def auto_execute' not in content.lower()
        assert 'def run_action' not in content.lower()
