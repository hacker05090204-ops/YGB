"""
Test Action Request - Phase-04 Validation
REIMPLEMENTED-2026

Tests for ActionRequest frozen dataclass.
These tests are written BEFORE implementation (Test-First).
"""

import pytest


class TestActionRequestClass:
    """Tests for ActionRequest dataclass."""

    def test_action_request_exists(self):
        """Verify ActionRequest class exists."""
        from python.phase04_validation.requests import ActionRequest
        assert ActionRequest is not None

    def test_action_request_is_frozen(self):
        """Verify ActionRequest is frozen dataclass."""
        from python.phase04_validation.requests import ActionRequest
        from python.phase04_validation.action_types import ActionType
        from python.phase02_actors.actors import ActorType
        from python.phase03_trust.trust_zones import TrustZone
        
        request = ActionRequest(
            actor_type=ActorType.SYSTEM,
            action_type=ActionType.READ,
            trust_zone=TrustZone.SYSTEM,
            target="test_resource",
        )
        with pytest.raises((AttributeError, TypeError)):
            request.target = "changed"

    def test_action_request_has_actor_type(self):
        """Verify ActionRequest has actor_type field."""
        from python.phase04_validation.requests import ActionRequest
        from python.phase04_validation.action_types import ActionType
        from python.phase02_actors.actors import ActorType
        from python.phase03_trust.trust_zones import TrustZone
        
        request = ActionRequest(
            actor_type=ActorType.HUMAN,
            action_type=ActionType.READ,
            trust_zone=TrustZone.HUMAN,
            target="test",
        )
        assert request.actor_type == ActorType.HUMAN

    def test_action_request_has_action_type(self):
        """Verify ActionRequest has action_type field."""
        from python.phase04_validation.requests import ActionRequest
        from python.phase04_validation.action_types import ActionType
        from python.phase02_actors.actors import ActorType
        from python.phase03_trust.trust_zones import TrustZone
        
        request = ActionRequest(
            actor_type=ActorType.HUMAN,
            action_type=ActionType.WRITE,
            trust_zone=TrustZone.HUMAN,
            target="test",
        )
        assert request.action_type == ActionType.WRITE

    def test_action_request_has_trust_zone(self):
        """Verify ActionRequest has trust_zone field."""
        from python.phase04_validation.requests import ActionRequest
        from python.phase04_validation.action_types import ActionType
        from python.phase02_actors.actors import ActorType
        from python.phase03_trust.trust_zones import TrustZone
        
        request = ActionRequest(
            actor_type=ActorType.SYSTEM,
            action_type=ActionType.READ,
            trust_zone=TrustZone.EXTERNAL,
            target="test",
        )
        assert request.trust_zone == TrustZone.EXTERNAL

    def test_action_request_has_target(self):
        """Verify ActionRequest has target field."""
        from python.phase04_validation.requests import ActionRequest
        from python.phase04_validation.action_types import ActionType
        from python.phase02_actors.actors import ActorType
        from python.phase03_trust.trust_zones import TrustZone
        
        request = ActionRequest(
            actor_type=ActorType.SYSTEM,
            action_type=ActionType.READ,
            trust_zone=TrustZone.SYSTEM,
            target="my_resource",
        )
        assert request.target == "my_resource"


class TestValidationResponseClass:
    """Tests for ValidationResponse dataclass."""

    def test_validation_response_exists(self):
        """Verify ValidationResponse class exists."""
        from python.phase04_validation.requests import ValidationResponse
        assert ValidationResponse is not None

    def test_validation_response_is_frozen(self):
        """Verify ValidationResponse is frozen dataclass."""
        from python.phase04_validation.requests import ActionRequest, ValidationResponse
        from python.phase04_validation.action_types import ActionType
        from python.phase04_validation.validation_results import ValidationResult
        from python.phase02_actors.actors import ActorType
        from python.phase03_trust.trust_zones import TrustZone
        
        request = ActionRequest(
            actor_type=ActorType.SYSTEM,
            action_type=ActionType.READ,
            trust_zone=TrustZone.SYSTEM,
            target="test",
        )
        response = ValidationResponse(
            request=request,
            result=ValidationResult.ALLOW,
            reason="Test allowed",
            requires_human=False,
        )
        with pytest.raises((AttributeError, TypeError)):
            response.result = ValidationResult.DENY

    def test_validation_response_has_request(self):
        """Verify ValidationResponse has request field."""
        from python.phase04_validation.requests import ActionRequest, ValidationResponse
        from python.phase04_validation.action_types import ActionType
        from python.phase04_validation.validation_results import ValidationResult
        from python.phase02_actors.actors import ActorType
        from python.phase03_trust.trust_zones import TrustZone
        
        request = ActionRequest(
            actor_type=ActorType.HUMAN,
            action_type=ActionType.READ,
            trust_zone=TrustZone.HUMAN,
            target="test",
        )
        response = ValidationResponse(
            request=request,
            result=ValidationResult.ALLOW,
            reason="Human allowed",
            requires_human=False,
        )
        assert response.request == request

    def test_validation_response_has_result(self):
        """Verify ValidationResponse has result field."""
        from python.phase04_validation.requests import ActionRequest, ValidationResponse
        from python.phase04_validation.action_types import ActionType
        from python.phase04_validation.validation_results import ValidationResult
        from python.phase02_actors.actors import ActorType
        from python.phase03_trust.trust_zones import TrustZone
        
        request = ActionRequest(
            actor_type=ActorType.SYSTEM,
            action_type=ActionType.WRITE,
            trust_zone=TrustZone.EXTERNAL,
            target="test",
        )
        response = ValidationResponse(
            request=request,
            result=ValidationResult.DENY,
            reason="Denied",
            requires_human=False,
        )
        assert response.result == ValidationResult.DENY

    def test_validation_response_has_reason(self):
        """Verify ValidationResponse has reason field."""
        from python.phase04_validation.requests import ActionRequest, ValidationResponse
        from python.phase04_validation.action_types import ActionType
        from python.phase04_validation.validation_results import ValidationResult
        from python.phase02_actors.actors import ActorType
        from python.phase03_trust.trust_zones import TrustZone
        
        request = ActionRequest(
            actor_type=ActorType.SYSTEM,
            action_type=ActionType.DELETE,
            trust_zone=TrustZone.SYSTEM,
            target="test",
        )
        response = ValidationResponse(
            request=request,
            result=ValidationResult.ESCALATE,
            reason="Critical action requires human approval",
            requires_human=True,
        )
        assert "Critical" in response.reason

    def test_validation_response_has_requires_human(self):
        """Verify ValidationResponse has requires_human field."""
        from python.phase04_validation.requests import ActionRequest, ValidationResponse
        from python.phase04_validation.action_types import ActionType
        from python.phase04_validation.validation_results import ValidationResult
        from python.phase02_actors.actors import ActorType
        from python.phase03_trust.trust_zones import TrustZone
        
        request = ActionRequest(
            actor_type=ActorType.SYSTEM,
            action_type=ActionType.EXECUTE,
            trust_zone=TrustZone.SYSTEM,
            target="test",
        )
        response = ValidationResponse(
            request=request,
            result=ValidationResult.ESCALATE,
            reason="Needs human",
            requires_human=True,
        )
        assert response.requires_human is True
