"""
Tests for Phase-14 No Authority.

Tests:
- Connector cannot approve anything
- Connector cannot change values
- Connector is pass-through only
"""
import pytest


class TestNoAuthority:
    """Test zero-authority constraints."""

    def test_cannot_upgrade_blocked_to_proceed(self):
        """Connector cannot change is_blocked=True to can_proceed=True."""
        from python.phase12_evidence.evidence_types import ConfidenceLevel, EvidenceState
        from python.phase13_handoff.handoff_types import (
            ReadinessState, HumanPresence, BugSeverity, TargetType
        )
        from python.phase13_handoff.handoff_context import HandoffContext
        from python.phase13_handoff.readiness_engine import make_handoff_decision
        from python.phase14_connector.connector_types import ConnectorRequestType
        from python.phase14_connector.connector_context import ConnectorInput
        from python.phase14_connector.connector_engine import map_handoff_to_output

        # Create blocked decision
        context = HandoffContext(
            bug_id="BUG-001",
            confidence=ConfidenceLevel.LOW,
            consistency_state=EvidenceState.UNVERIFIED,
            human_review_completed=False,
            severity=BugSeverity.HIGH,
            target_type=TargetType.PRODUCTION,
            has_active_blockers=True,
            human_confirmed=False
        )
        decision = make_handoff_decision(context)
        assert decision.can_proceed is False

        input = ConnectorInput(
            bug_id="BUG-001",
            target_id="TARGET-001",
            request_type=ConnectorRequestType.FULL_EVALUATION,
            timestamp="2026-01-25T04:50:00-05:00",
            handoff_decision=decision
        )

        output = map_handoff_to_output(input, decision)

        # Connector CANNOT change False to True
        assert output.can_proceed is False
        assert output.is_blocked is True

    def test_reason_code_preserved(self):
        """Reason code is preserved from Phase-13."""
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

        output = map_handoff_to_output(input, decision)

        # Reason code must match
        assert output.reason_code == decision.reason_code


class TestCreateResult:
    """Test create_result function."""

    def test_create_result_success(self):
        """Create result with success."""
        from python.phase12_evidence.evidence_types import ConfidenceLevel, EvidenceState
        from python.phase13_handoff.handoff_types import ReadinessState, HumanPresence
        from python.phase14_connector.connector_types import ConnectorRequestType
        from python.phase14_connector.connector_context import ConnectorInput, ConnectorOutput
        from python.phase14_connector.connector_engine import create_result

        input = ConnectorInput(
            bug_id="BUG-001",
            target_id="TARGET-001",
            request_type=ConnectorRequestType.STATUS_CHECK,
            timestamp="2026-01-25T04:50:00-05:00",
            handoff_decision=None
        )

        output = ConnectorOutput(
            bug_id="BUG-001",
            target_id="TARGET-001",
            confidence=ConfidenceLevel.HIGH,
            evidence_state=EvidenceState.CONSISTENT,
            readiness=ReadinessState.READY_FOR_BROWSER,
            human_presence=HumanPresence.OPTIONAL,
            can_proceed=True,
            is_blocked=False,
            blockers=(),
            reason_code="HD-006",
            reason_description="Human optional"
        )

        result = create_result(input, output, success=True)
        assert result.success is True
        assert result.input == input
        assert result.output == output


class TestConnectorResultFrozen:
    """Test ConnectorResult immutability."""

    def test_connector_result_is_frozen(self):
        """ConnectorResult is frozen."""
        from python.phase12_evidence.evidence_types import ConfidenceLevel, EvidenceState
        from python.phase13_handoff.handoff_types import ReadinessState, HumanPresence
        from python.phase14_connector.connector_types import ConnectorRequestType
        from python.phase14_connector.connector_context import (
            ConnectorInput, ConnectorOutput, ConnectorResult
        )

        input = ConnectorInput(
            bug_id="BUG-001",
            target_id="TARGET-001",
            request_type=ConnectorRequestType.STATUS_CHECK,
            timestamp="2026-01-25T04:50:00-05:00",
            handoff_decision=None
        )

        output = ConnectorOutput(
            bug_id="BUG-001",
            target_id="TARGET-001",
            confidence=ConfidenceLevel.HIGH,
            evidence_state=EvidenceState.CONSISTENT,
            readiness=ReadinessState.READY_FOR_BROWSER,
            human_presence=HumanPresence.OPTIONAL,
            can_proceed=True,
            is_blocked=False,
            blockers=(),
            reason_code="HD-006",
            reason_description="Human optional"
        )

        result = ConnectorResult(
            input=input,
            output=output,
            success=True,
            error_code=None,
            error_description=None
        )

        with pytest.raises(Exception):
            result.success = False
