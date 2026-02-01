"""
Tests for Phase-14 Blocking Propagation.

Tests:
- BLOCKING propagates immediately
- is_blocked pass-through
- can_proceed pass-through
"""
import pytest


class TestBlockingPropagation:
    """Test blocking propagation."""

    def test_blocked_propagates(self):
        """is_blocked=True propagates to output."""
        from python.phase12_evidence.evidence_types import ConfidenceLevel, EvidenceState
        from python.phase13_handoff.handoff_types import (
            ReadinessState, HumanPresence, BugSeverity, TargetType
        )
        from python.phase13_handoff.handoff_context import HandoffContext
        from python.phase13_handoff.readiness_engine import make_handoff_decision
        from python.phase14_connector.connector_types import ConnectorRequestType
        from python.phase14_connector.connector_context import ConnectorInput
        from python.phase14_connector.connector_engine import (
            map_handoff_to_output, propagate_blocking
        )

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

        # Verify blocking propagates
        assert propagate_blocking(decision) is True

    def test_not_blocked_propagates(self):
        """is_blocked=False propagates to output."""
        from python.phase12_evidence.evidence_types import ConfidenceLevel, EvidenceState
        from python.phase13_handoff.handoff_types import (
            ReadinessState, HumanPresence, BugSeverity, TargetType
        )
        from python.phase13_handoff.handoff_context import HandoffContext
        from python.phase13_handoff.readiness_engine import make_handoff_decision
        from python.phase14_connector.connector_engine import propagate_blocking

        # Create non-blocked decision
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

        # Verify not blocking
        assert propagate_blocking(decision) is False

    def test_can_proceed_false_preserved(self):
        """can_proceed=False is preserved in output."""
        from python.phase12_evidence.evidence_types import ConfidenceLevel, EvidenceState
        from python.phase13_handoff.handoff_types import (
            ReadinessState, HumanPresence, BugSeverity, TargetType
        )
        from python.phase13_handoff.handoff_context import HandoffContext
        from python.phase13_handoff.readiness_engine import make_handoff_decision
        from python.phase14_connector.connector_types import ConnectorRequestType
        from python.phase14_connector.connector_context import ConnectorInput
        from python.phase14_connector.connector_engine import map_handoff_to_output

        # Create decision that cannot proceed
        context = HandoffContext(
            bug_id="BUG-001",
            confidence=ConfidenceLevel.MEDIUM,
            consistency_state=EvidenceState.RAW,
            human_review_completed=False,
            severity=BugSeverity.HIGH,
            target_type=TargetType.PRODUCTION,
            has_active_blockers=False,
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
        assert output.can_proceed is False

    def test_blockers_preserved(self):
        """Blockers tuple is preserved in output."""
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
            severity=BugSeverity.HIGH,
            target_type=TargetType.PRODUCTION,
            has_active_blockers=True,  # Has blockers
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
        # Blockers from decision must be preserved
        assert output.blockers == decision.blockers
