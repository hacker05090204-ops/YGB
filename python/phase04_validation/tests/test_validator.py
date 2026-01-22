"""
Test Validate Action - Phase-04 Validation
REIMPLEMENTED-2026

Tests for validate_action pure function.
These tests are written BEFORE implementation (Test-First).
"""

import pytest


class TestValidateActionFunction:
    """Tests for validate_action function."""

    def test_validate_action_exists(self):
        """Verify validate_action function exists."""
        from python.phase04_validation.validator import validate_action
        assert validate_action is not None


class TestHumanActorValidation:
    """Tests for human actor validation - should always ALLOW."""

    def test_human_actor_always_allowed(self):
        """Verify HUMAN actor is always allowed."""
        from python.phase04_validation.validator import validate_action
        from python.phase04_validation.requests import ActionRequest
        from python.phase04_validation.action_types import ActionType
        from python.phase04_validation.validation_results import ValidationResult
        from python.phase02_actors.actors import ActorType
        from python.phase03_trust.trust_zones import TrustZone
        
        for action in ActionType:
            request = ActionRequest(
                actor_type=ActorType.HUMAN,
                action_type=action,
                trust_zone=TrustZone.SYSTEM,
                target="test",
            )
            response = validate_action(request)
            assert response.result == ValidationResult.ALLOW

    def test_human_zone_always_allowed(self):
        """Verify HUMAN trust zone is always allowed."""
        from python.phase04_validation.validator import validate_action
        from python.phase04_validation.requests import ActionRequest
        from python.phase04_validation.action_types import ActionType
        from python.phase04_validation.validation_results import ValidationResult
        from python.phase02_actors.actors import ActorType
        from python.phase03_trust.trust_zones import TrustZone
        
        for action in ActionType:
            request = ActionRequest(
                actor_type=ActorType.SYSTEM,
                action_type=action,
                trust_zone=TrustZone.HUMAN,
                target="test",
            )
            response = validate_action(request)
            assert response.result == ValidationResult.ALLOW


class TestDenyByDefault:
    """Tests for deny-by-default behavior."""

    def test_external_write_denied(self):
        """Verify EXTERNAL zone write is DENIED."""
        from python.phase04_validation.validator import validate_action
        from python.phase04_validation.requests import ActionRequest
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
        response = validate_action(request)
        assert response.result == ValidationResult.DENY

    def test_external_delete_denied(self):
        """Verify EXTERNAL zone delete is DENIED."""
        from python.phase04_validation.validator import validate_action
        from python.phase04_validation.requests import ActionRequest
        from python.phase04_validation.action_types import ActionType
        from python.phase04_validation.validation_results import ValidationResult
        from python.phase02_actors.actors import ActorType
        from python.phase03_trust.trust_zones import TrustZone
        
        request = ActionRequest(
            actor_type=ActorType.SYSTEM,
            action_type=ActionType.DELETE,
            trust_zone=TrustZone.EXTERNAL,
            target="test",
        )
        response = validate_action(request)
        assert response.result == ValidationResult.DENY

    def test_external_execute_denied(self):
        """Verify EXTERNAL zone execute is DENIED."""
        from python.phase04_validation.validator import validate_action
        from python.phase04_validation.requests import ActionRequest
        from python.phase04_validation.action_types import ActionType
        from python.phase04_validation.validation_results import ValidationResult
        from python.phase02_actors.actors import ActorType
        from python.phase03_trust.trust_zones import TrustZone
        
        request = ActionRequest(
            actor_type=ActorType.SYSTEM,
            action_type=ActionType.EXECUTE,
            trust_zone=TrustZone.EXTERNAL,
            target="test",
        )
        response = validate_action(request)
        assert response.result == ValidationResult.DENY


class TestEscalationPaths:
    """Tests for escalation to human approval."""

    def test_system_delete_escalates(self):
        """Verify SYSTEM zone delete requires escalation."""
        from python.phase04_validation.validator import validate_action
        from python.phase04_validation.requests import ActionRequest
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
        response = validate_action(request)
        assert response.result == ValidationResult.ESCALATE
        assert response.requires_human is True

    def test_system_execute_escalates(self):
        """Verify SYSTEM zone execute requires escalation."""
        from python.phase04_validation.validator import validate_action
        from python.phase04_validation.requests import ActionRequest
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
        response = validate_action(request)
        assert response.result == ValidationResult.ESCALATE
        assert response.requires_human is True

    def test_system_write_escalates(self):
        """Verify SYSTEM zone write requires escalation."""
        from python.phase04_validation.validator import validate_action
        from python.phase04_validation.requests import ActionRequest
        from python.phase04_validation.action_types import ActionType
        from python.phase04_validation.validation_results import ValidationResult
        from python.phase02_actors.actors import ActorType
        from python.phase03_trust.trust_zones import TrustZone
        
        request = ActionRequest(
            actor_type=ActorType.SYSTEM,
            action_type=ActionType.WRITE,
            trust_zone=TrustZone.SYSTEM,
            target="test",
        )
        response = validate_action(request)
        assert response.result == ValidationResult.ESCALATE
        assert response.requires_human is True


class TestLowRiskOperations:
    """Tests for low-risk operations that are allowed."""

    def test_system_read_allowed(self):
        """Verify SYSTEM zone read is ALLOWED (low risk)."""
        from python.phase04_validation.validator import validate_action
        from python.phase04_validation.requests import ActionRequest
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
        response = validate_action(request)
        assert response.result == ValidationResult.ALLOW

    def test_governance_read_allowed(self):
        """Verify GOVERNANCE zone read is ALLOWED."""
        from python.phase04_validation.validator import validate_action
        from python.phase04_validation.requests import ActionRequest
        from python.phase04_validation.action_types import ActionType
        from python.phase04_validation.validation_results import ValidationResult
        from python.phase02_actors.actors import ActorType
        from python.phase03_trust.trust_zones import TrustZone
        
        request = ActionRequest(
            actor_type=ActorType.SYSTEM,
            action_type=ActionType.READ,
            trust_zone=TrustZone.GOVERNANCE,
            target="test",
        )
        response = validate_action(request)
        assert response.result == ValidationResult.ALLOW


class TestHumanOverridePrecedence:
    """Tests for human override precedence."""

    def test_response_includes_original_request(self):
        """Verify response includes the original request."""
        from python.phase04_validation.validator import validate_action
        from python.phase04_validation.requests import ActionRequest
        from python.phase04_validation.action_types import ActionType
        from python.phase02_actors.actors import ActorType
        from python.phase03_trust.trust_zones import TrustZone
        
        request = ActionRequest(
            actor_type=ActorType.SYSTEM,
            action_type=ActionType.READ,
            trust_zone=TrustZone.SYSTEM,
            target="test_target",
        )
        response = validate_action(request)
        assert response.request == request

    def test_response_includes_reason(self):
        """Verify response includes explanation."""
        from python.phase04_validation.validator import validate_action
        from python.phase04_validation.requests import ActionRequest
        from python.phase04_validation.action_types import ActionType
        from python.phase02_actors.actors import ActorType
        from python.phase03_trust.trust_zones import TrustZone
        
        request = ActionRequest(
            actor_type=ActorType.SYSTEM,
            action_type=ActionType.DELETE,
            trust_zone=TrustZone.SYSTEM,
            target="test",
        )
        response = validate_action(request)
        assert len(response.reason) > 0


class TestConfigureActionEscalation:
    """Tests for CONFIGURE action escalation."""

    def test_system_configure_escalates(self):
        """Verify SYSTEM zone configure requires escalation."""
        from python.phase04_validation.validator import validate_action
        from python.phase04_validation.requests import ActionRequest
        from python.phase04_validation.action_types import ActionType
        from python.phase04_validation.validation_results import ValidationResult
        from python.phase02_actors.actors import ActorType
        from python.phase03_trust.trust_zones import TrustZone
        
        request = ActionRequest(
            actor_type=ActorType.SYSTEM,
            action_type=ActionType.CONFIGURE,
            trust_zone=TrustZone.SYSTEM,
            target="settings",
        )
        response = validate_action(request)
        assert response.result == ValidationResult.ESCALATE
        assert response.requires_human is True

    def test_governance_configure_escalates(self):
        """Verify GOVERNANCE zone configure requires escalation."""
        from python.phase04_validation.validator import validate_action
        from python.phase04_validation.requests import ActionRequest
        from python.phase04_validation.action_types import ActionType
        from python.phase04_validation.validation_results import ValidationResult
        from python.phase02_actors.actors import ActorType
        from python.phase03_trust.trust_zones import TrustZone
        
        request = ActionRequest(
            actor_type=ActorType.SYSTEM,
            action_type=ActionType.CONFIGURE,
            trust_zone=TrustZone.GOVERNANCE,
            target="config",
        )
        response = validate_action(request)
        assert response.result == ValidationResult.ESCALATE
        assert response.requires_human is True


class TestDefaultDenyBehavior:
    """Tests for default deny behavior (fail-safe)."""

    def test_governance_write_escalates(self):
        """Verify GOVERNANCE zone write requires escalation (not default deny)."""
        from python.phase04_validation.validator import validate_action
        from python.phase04_validation.requests import ActionRequest
        from python.phase04_validation.action_types import ActionType
        from python.phase04_validation.validation_results import ValidationResult
        from python.phase02_actors.actors import ActorType
        from python.phase03_trust.trust_zones import TrustZone
        
        # GOVERNANCE WRITE should hit default DENY since it's not covered by specific rules
        request = ActionRequest(
            actor_type=ActorType.SYSTEM,
            action_type=ActionType.WRITE,
            trust_zone=TrustZone.GOVERNANCE,
            target="gov_data",
        )
        response = validate_action(request)
        # This should be DENY by default (governance zone write is not explicitly allowed)
        assert response.result == ValidationResult.DENY


class TestForbiddenBehavior:
    """Tests to verify no forbidden behavior."""

    def test_no_auto_execute_method(self):
        """Verify no auto_execute method exists."""
        import python.phase04_validation.validator as v
        assert not hasattr(v, 'auto_execute')

    def test_no_bypass_validation_method(self):
        """Verify no bypass_validation method exists."""
        import python.phase04_validation.validator as v
        assert not hasattr(v, 'bypass_validation')

    def test_no_skip_human_method(self):
        """Verify no skip_human method exists."""
        import python.phase04_validation.validator as v
        assert not hasattr(v, 'skip_human')


class TestNoFuturePhaseCoupling:
    """Tests to verify no future phase coupling."""

    def test_no_phase05_imports(self):
        """Verify no Phase-05+ imports in Phase-04."""
        from pathlib import Path
        
        phase04_path = Path(__file__).parent.parent
        for py_file in phase04_path.glob('*.py'):
            content = py_file.read_text()
            assert 'phase05' not in content.lower()
            assert 'phase06' not in content.lower()

    def test_no_network_imports(self):
        """Verify Phase-04 has no network imports."""
        from pathlib import Path
        import re
        
        phase04_path = Path(__file__).parent.parent
        for py_file in phase04_path.glob('*.py'):
            content = py_file.read_text()
            matches = re.findall(r'\bimport\s+(?:socket|requests|urllib|http)\b', content)
            assert len(matches) == 0

    def test_no_subprocess_imports(self):
        """Verify Phase-04 has no subprocess imports."""
        from pathlib import Path
        import re
        
        phase04_path = Path(__file__).parent.parent
        for py_file in phase04_path.glob('*.py'):
            content = py_file.read_text()
            matches = re.findall(r'\bimport\s+subprocess\b', content)
            assert len(matches) == 0
