"""
Tests for Phase-14 Phase Chain Execution.

Tests:
- Mapping from Phase-13 to ConnectorOutput
- Pass-through of all values
"""
import pytest


class TestPhaseChainMapping:
    """Test phase chain mapping."""

    def test_map_handoff_to_output(self):
        """Map HandoffDecision to ConnectorOutput."""
        from python.phase12_evidence.evidence_types import ConfidenceLevel, EvidenceState
        from python.phase13_handoff.handoff_types import (
            ReadinessState, HumanPresence, BugSeverity, TargetType
        )
        from python.phase13_handoff.handoff_context import HandoffContext
        from python.phase13_handoff.readiness_engine import make_handoff_decision
        from python.phase14_connector.connector_types import ConnectorRequestType
        from python.phase14_connector.connector_context import ConnectorInput
        from python.phase14_connector.connector_engine import map_handoff_to_output

        # Create Phase-13 decision
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

        # Create connector input
        input = ConnectorInput(
            bug_id="BUG-001",
            target_id="TARGET-001",
            request_type=ConnectorRequestType.FULL_EVALUATION,
            timestamp="2026-01-25T04:50:00-05:00",
            handoff_decision=decision
        )

        # Map to output
        output = map_handoff_to_output(input, decision)

        # Verify pass-through
        assert output.bug_id == "BUG-001"
        assert output.target_id == "TARGET-001"
        assert output.readiness == decision.readiness
        assert output.human_presence == decision.human_presence
        assert output.can_proceed == decision.can_proceed
        assert output.is_blocked == decision.is_blocked

    def test_output_reflects_phase13_decision(self):
        """Output exactly reflects Phase-13 decision."""
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
            bug_id="BUG-002",
            confidence=ConfidenceLevel.LOW,
            consistency_state=EvidenceState.INCONSISTENT,
            human_review_completed=False,
            severity=BugSeverity.HIGH,
            target_type=TargetType.PRODUCTION,
            has_active_blockers=True,
            human_confirmed=False
        )
        decision = make_handoff_decision(context)

        input = ConnectorInput(
            bug_id="BUG-002",
            target_id="TARGET-002",
            request_type=ConnectorRequestType.READINESS_CHECK,
            timestamp="2026-01-25T04:50:00-05:00",
            handoff_decision=decision
        )

        output = map_handoff_to_output(input, decision)

        # Decision was blocked - output must reflect
        assert output.can_proceed is False
        assert output.is_blocked is True


class TestConnectorOutputFrozen:
    """Test ConnectorOutput immutability."""

    def test_connector_output_is_frozen(self):
        """ConnectorOutput is frozen."""
        from python.phase12_evidence.evidence_types import ConfidenceLevel, EvidenceState
        from python.phase13_handoff.handoff_types import ReadinessState, HumanPresence
        from python.phase14_connector.connector_context import ConnectorOutput

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

        with pytest.raises(Exception):
            output.can_proceed = False
