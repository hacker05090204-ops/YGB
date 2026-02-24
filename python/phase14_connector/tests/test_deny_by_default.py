"""
Tests for Phase-14 Deny-By-Default.

Tests:
- Unknown → blocked
- No forbidden imports
- No phase15+ imports
"""
import pytest


class TestDenyByDefault:
    """Test deny-by-default behavior."""

    def test_missing_decision_treated_as_blocked(self):
        """Missing handoff_decision → blocked output."""
        from python.phase14_connector.connector_types import ConnectorRequestType
        from python.phase14_connector.connector_context import ConnectorInput
        from python.phase14_connector.connector_engine import create_default_output

        input = ConnectorInput(
            bug_id="BUG-001",
            target_id="TARGET-001",
            request_type=ConnectorRequestType.STATUS_CHECK,
            timestamp="2026-01-25T04:50:00-05:00",
            handoff_decision=None  # No decision
        )

        output = create_default_output(input)
        assert output.can_proceed is False
        assert output.is_blocked is True


class TestNoForbiddenImports:
    """Test no forbidden imports in any file."""

    def test_no_os_import(self):
        """No os import in any module."""
        import python.phase14_connector.connector_types as types_module
        import python.phase14_connector.connector_context as context_module
        import python.phase14_connector.connector_engine as engine_module
        import inspect

        for module in [types_module, context_module, engine_module]:
            source = inspect.getsource(module)
            assert 'import os' not in source

    def test_no_subprocess_import(self):
        """No subprocess import."""
        import python.phase14_connector.connector_engine as module
        import inspect
        source = inspect.getsource(module)
        assert 'import subprocess' not in source

    def test_no_phase15_import(self):
        """No phase15+ imports in implementation files (test files excluded)."""
        import os
        module_dir = os.path.dirname(__file__).replace('/tests', '').replace('\\tests', '')
        for filename in os.listdir(module_dir):
            if filename.endswith('.py') and not filename.startswith('test_'):
                filepath = os.path.join(module_dir, filename)
                with open(filepath, 'r') as f:
                    content = f.read()
                    assert 'phase15' not in content, f"Found phase15 in {filename}"


class TestDeterminism:
    """Test same input produces same output."""

    def test_same_input_same_result(self):
        """Same input produces same result."""
        from python.phase12_evidence.evidence_types import ConfidenceLevel, EvidenceState
        from python.phase13_handoff.handoff_types import (
            ReadinessState, HumanPresence, BugSeverity, TargetType
        )
        from python.phase13_handoff.handoff_context import HandoffContext
        from python.phase13_handoff.readiness_engine import make_handoff_decision
        from python.phase14_connector.connector_types import ConnectorRequestType
        from python.phase14_connector.connector_context import ConnectorInput
        from python.phase14_connector.connector_engine import map_handoff_to_output

        context = HandoffContext(
            bug_id="BUG-001",
            confidence=ConfidenceLevel.HIGH,
            consistency_state=EvidenceState.CONSISTENT,
            human_review_completed=True,
            severity=BugSeverity.MEDIUM,
            target_type=TargetType.STAGING,
            has_active_blockers=False,
            human_confirmed=True
        )
        decision = make_handoff_decision(context)

        input = ConnectorInput(
            bug_id="BUG-001",
            target_id="TARGET-001",
            request_type=ConnectorRequestType.FULL_EVALUATION,
            timestamp="2026-01-25T04:50:00-05:00",
            handoff_decision=decision
        )

        output1 = map_handoff_to_output(input, decision)
        output2 = map_handoff_to_output(input, decision)
        output3 = map_handoff_to_output(input, decision)

        assert output1.can_proceed == output2.can_proceed == output3.can_proceed
        assert output1.reason_code == output2.reason_code == output3.reason_code
