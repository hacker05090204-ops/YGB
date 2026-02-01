"""
Tests for Phase-13 Handoff Blocking.

Tests:
- Handoff decision table
- No browser handoff without approval
- Blocking conditions
"""
import pytest


class TestHandoffDecision:
    """Test handoff decision table."""

    def test_not_ready_cannot_proceed(self):
        """NOT_READY → cannot proceed."""
        from python.phase12_evidence.evidence_types import ConfidenceLevel, EvidenceState
        from python.phase13_handoff.handoff_types import BugSeverity, TargetType
        from python.phase13_handoff.handoff_context import HandoffContext
        from python.phase13_handoff.readiness_engine import make_handoff_decision

        context = HandoffContext(
            bug_id="BUG-001",
            confidence=ConfidenceLevel.LOW,
            consistency_state=EvidenceState.UNVERIFIED,
            human_review_completed=False,
            severity=BugSeverity.HIGH,
            target_type=TargetType.PRODUCTION,
            has_active_blockers=False,
            human_confirmed=False
        )

        decision = make_handoff_decision(context)
        assert decision.can_proceed is False
        assert decision.is_blocked is True

    def test_blockers_list_populated(self):
        """Active blockers → blockers list populated."""
        from python.phase12_evidence.evidence_types import ConfidenceLevel, EvidenceState
        from python.phase13_handoff.handoff_types import BugSeverity, TargetType
        from python.phase13_handoff.handoff_context import HandoffContext
        from python.phase13_handoff.readiness_engine import make_handoff_decision

        context = HandoffContext(
            bug_id="BUG-001",
            confidence=ConfidenceLevel.HIGH,
            consistency_state=EvidenceState.CONSISTENT,
            human_review_completed=True,
            severity=BugSeverity.HIGH,
            target_type=TargetType.PRODUCTION,
            has_active_blockers=True,  # Active blockers
            human_confirmed=True
        )

        decision = make_handoff_decision(context)
        assert "ACTIVE_BLOCKER" in decision.blockers

    def test_review_required_cannot_proceed(self):
        """REVIEW_REQUIRED → cannot proceed."""
        from python.phase12_evidence.evidence_types import ConfidenceLevel, EvidenceState
        from python.phase13_handoff.handoff_types import BugSeverity, TargetType
        from python.phase13_handoff.handoff_context import HandoffContext
        from python.phase13_handoff.readiness_engine import make_handoff_decision

        context = HandoffContext(
            bug_id="BUG-001",
            confidence=ConfidenceLevel.HIGH,
            consistency_state=EvidenceState.RAW,
            human_review_completed=True,
            severity=BugSeverity.HIGH,
            target_type=TargetType.PRODUCTION,
            has_active_blockers=False,
            human_confirmed=False
        )

        decision = make_handoff_decision(context)
        assert decision.can_proceed is False

    def test_ready_required_not_confirmed_cannot_proceed(self):
        """READY + REQUIRED + not confirmed → cannot proceed."""
        from python.phase12_evidence.evidence_types import ConfidenceLevel, EvidenceState
        from python.phase13_handoff.handoff_types import BugSeverity, TargetType
        from python.phase13_handoff.handoff_context import HandoffContext
        from python.phase13_handoff.readiness_engine import make_handoff_decision

        context = HandoffContext(
            bug_id="BUG-001",
            confidence=ConfidenceLevel.HIGH,
            consistency_state=EvidenceState.CONSISTENT,
            human_review_completed=True,
            severity=BugSeverity.CRITICAL,  # Requires human
            target_type=TargetType.PRODUCTION,
            has_active_blockers=False,
            human_confirmed=False  # Not confirmed
        )

        decision = make_handoff_decision(context)
        assert decision.can_proceed is False

    def test_ready_required_confirmed_can_proceed(self):
        """READY + REQUIRED + confirmed → can proceed."""
        from python.phase12_evidence.evidence_types import ConfidenceLevel, EvidenceState
        from python.phase13_handoff.handoff_types import BugSeverity, TargetType
        from python.phase13_handoff.handoff_context import HandoffContext
        from python.phase13_handoff.readiness_engine import make_handoff_decision

        context = HandoffContext(
            bug_id="BUG-001",
            confidence=ConfidenceLevel.HIGH,
            consistency_state=EvidenceState.CONSISTENT,
            human_review_completed=True,
            severity=BugSeverity.CRITICAL,
            target_type=TargetType.PRODUCTION,
            has_active_blockers=False,
            human_confirmed=True  # Confirmed
        )

        decision = make_handoff_decision(context)
        assert decision.can_proceed is True

    def test_ready_optional_can_proceed(self):
        """READY + OPTIONAL → can proceed."""
        from python.phase12_evidence.evidence_types import ConfidenceLevel, EvidenceState
        from python.phase13_handoff.handoff_types import BugSeverity, TargetType
        from python.phase13_handoff.handoff_context import HandoffContext
        from python.phase13_handoff.readiness_engine import make_handoff_decision

        context = HandoffContext(
            bug_id="BUG-001",
            confidence=ConfidenceLevel.HIGH,
            consistency_state=EvidenceState.CONSISTENT,
            human_review_completed=True,
            severity=BugSeverity.MEDIUM,  # Optional human
            target_type=TargetType.STAGING,
            has_active_blockers=False,
            human_confirmed=False  # Not required
        )

        decision = make_handoff_decision(context)
        assert decision.can_proceed is True


class TestIsBlocked:
    """Test is_blocked function."""

    def test_blockers_true(self):
        """Active blockers → blocked."""
        from python.phase12_evidence.evidence_types import ConfidenceLevel, EvidenceState
        from python.phase13_handoff.handoff_types import BugSeverity, TargetType
        from python.phase13_handoff.handoff_context import HandoffContext
        from python.phase13_handoff.readiness_engine import is_blocked

        context = HandoffContext(
            bug_id="BUG-001",
            confidence=ConfidenceLevel.HIGH,
            consistency_state=EvidenceState.CONSISTENT,
            human_review_completed=True,
            severity=BugSeverity.HIGH,
            target_type=TargetType.PRODUCTION,
            has_active_blockers=True,
            human_confirmed=True
        )

        assert is_blocked(context) is True

    def test_no_blockers_not_blocked(self):
        """No blockers → not blocked."""
        from python.phase12_evidence.evidence_types import ConfidenceLevel, EvidenceState
        from python.phase13_handoff.handoff_types import BugSeverity, TargetType
        from python.phase13_handoff.handoff_context import HandoffContext
        from python.phase13_handoff.readiness_engine import is_blocked

        context = HandoffContext(
            bug_id="BUG-001",
            confidence=ConfidenceLevel.HIGH,
            consistency_state=EvidenceState.CONSISTENT,
            human_review_completed=True,
            severity=BugSeverity.HIGH,
            target_type=TargetType.PRODUCTION,
            has_active_blockers=False,
            human_confirmed=True
        )

        assert is_blocked(context) is False


class TestHandoffDecisionFrozen:
    """Test HandoffDecision immutability."""

    def test_handoff_decision_is_frozen(self):
        """HandoffDecision is frozen."""
        from python.phase13_handoff.handoff_types import ReadinessState, HumanPresence
        from python.phase13_handoff.readiness_engine import HandoffDecision

        decision = HandoffDecision(
            bug_id="BUG-001",
            readiness=ReadinessState.NOT_READY,
            human_presence=HumanPresence.BLOCKING,
            can_proceed=False,
            is_blocked=True,
            reason_code="HD-001",
            reason_description="Not ready",
            blockers=()
        )

        with pytest.raises(Exception):
            decision.can_proceed = True
