"""
Tests for Phase-13 Readiness State.

Tests:
- ReadinessState enum members
- Readiness decision table
- HIGH confidence alone ≠ READY
"""
import pytest


class TestReadinessStateEnum:
    """Test ReadinessState enum."""

    def test_has_not_ready(self):
        """Has NOT_READY member."""
        from python.phase13_handoff.handoff_types import ReadinessState
        assert hasattr(ReadinessState, 'NOT_READY')

    def test_has_review_required(self):
        """Has REVIEW_REQUIRED member."""
        from python.phase13_handoff.handoff_types import ReadinessState
        assert hasattr(ReadinessState, 'REVIEW_REQUIRED')

    def test_has_ready_for_browser(self):
        """Has READY_FOR_BROWSER member."""
        from python.phase13_handoff.handoff_types import ReadinessState
        assert hasattr(ReadinessState, 'READY_FOR_BROWSER')

    def test_exactly_three_members(self):
        """ReadinessState has exactly 3 members."""
        from python.phase13_handoff.handoff_types import ReadinessState
        assert len(ReadinessState) == 3


class TestReadinessDecisionTable:
    """Test readiness decision table."""

    def test_low_confidence_not_ready(self):
        """LOW confidence → NOT_READY."""
        from python.phase12_evidence.evidence_types import ConfidenceLevel, EvidenceState
        from python.phase13_handoff.handoff_types import ReadinessState, BugSeverity, TargetType
        from python.phase13_handoff.handoff_context import HandoffContext
        from python.phase13_handoff.readiness_engine import check_readiness

        context = HandoffContext(
            bug_id="BUG-001",
            confidence=ConfidenceLevel.LOW,
            consistency_state=EvidenceState.CONSISTENT,
            human_review_completed=True,
            severity=BugSeverity.HIGH,
            target_type=TargetType.PRODUCTION,
            has_active_blockers=False,
            human_confirmed=True
        )

        result = check_readiness(context)
        assert result == ReadinessState.NOT_READY

    def test_medium_confidence_not_ready(self):
        """MEDIUM confidence → NOT_READY."""
        from python.phase12_evidence.evidence_types import ConfidenceLevel, EvidenceState
        from python.phase13_handoff.handoff_types import ReadinessState, BugSeverity, TargetType
        from python.phase13_handoff.handoff_context import HandoffContext
        from python.phase13_handoff.readiness_engine import check_readiness

        context = HandoffContext(
            bug_id="BUG-001",
            confidence=ConfidenceLevel.MEDIUM,
            consistency_state=EvidenceState.CONSISTENT,
            human_review_completed=True,
            severity=BugSeverity.HIGH,
            target_type=TargetType.PRODUCTION,
            has_active_blockers=False,
            human_confirmed=True
        )

        result = check_readiness(context)
        assert result == ReadinessState.NOT_READY

    def test_high_inconsistent_not_ready(self):
        """HIGH + INCONSISTENT → NOT_READY."""
        from python.phase12_evidence.evidence_types import ConfidenceLevel, EvidenceState
        from python.phase13_handoff.handoff_types import ReadinessState, BugSeverity, TargetType
        from python.phase13_handoff.handoff_context import HandoffContext
        from python.phase13_handoff.readiness_engine import check_readiness

        context = HandoffContext(
            bug_id="BUG-001",
            confidence=ConfidenceLevel.HIGH,
            consistency_state=EvidenceState.INCONSISTENT,
            human_review_completed=True,
            severity=BugSeverity.HIGH,
            target_type=TargetType.PRODUCTION,
            has_active_blockers=False,
            human_confirmed=True
        )

        result = check_readiness(context)
        assert result == ReadinessState.NOT_READY

    def test_high_raw_review_required(self):
        """HIGH + RAW → REVIEW_REQUIRED."""
        from python.phase12_evidence.evidence_types import ConfidenceLevel, EvidenceState
        from python.phase13_handoff.handoff_types import ReadinessState, BugSeverity, TargetType
        from python.phase13_handoff.handoff_context import HandoffContext
        from python.phase13_handoff.readiness_engine import check_readiness

        context = HandoffContext(
            bug_id="BUG-001",
            confidence=ConfidenceLevel.HIGH,
            consistency_state=EvidenceState.RAW,
            human_review_completed=True,
            severity=BugSeverity.HIGH,
            target_type=TargetType.PRODUCTION,
            has_active_blockers=False,
            human_confirmed=True
        )

        result = check_readiness(context)
        assert result == ReadinessState.REVIEW_REQUIRED

    def test_high_consistent_no_review_required(self):
        """HIGH + CONSISTENT + no review → REVIEW_REQUIRED."""
        from python.phase12_evidence.evidence_types import ConfidenceLevel, EvidenceState
        from python.phase13_handoff.handoff_types import ReadinessState, BugSeverity, TargetType
        from python.phase13_handoff.handoff_context import HandoffContext
        from python.phase13_handoff.readiness_engine import check_readiness

        context = HandoffContext(
            bug_id="BUG-001",
            confidence=ConfidenceLevel.HIGH,
            consistency_state=EvidenceState.CONSISTENT,
            human_review_completed=False,
            severity=BugSeverity.HIGH,
            target_type=TargetType.PRODUCTION,
            has_active_blockers=False,
            human_confirmed=True
        )

        result = check_readiness(context)
        assert result == ReadinessState.REVIEW_REQUIRED

    def test_high_consistent_reviewed_blockers_not_ready(self):
        """HIGH + CONSISTENT + reviewed + blockers → NOT_READY."""
        from python.phase12_evidence.evidence_types import ConfidenceLevel, EvidenceState
        from python.phase13_handoff.handoff_types import ReadinessState, BugSeverity, TargetType
        from python.phase13_handoff.handoff_context import HandoffContext
        from python.phase13_handoff.readiness_engine import check_readiness

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

        result = check_readiness(context)
        assert result == ReadinessState.NOT_READY

    def test_high_consistent_reviewed_no_blockers_ready(self):
        """HIGH + CONSISTENT + reviewed + no blockers → READY_FOR_BROWSER."""
        from python.phase12_evidence.evidence_types import ConfidenceLevel, EvidenceState
        from python.phase13_handoff.handoff_types import ReadinessState, BugSeverity, TargetType
        from python.phase13_handoff.handoff_context import HandoffContext
        from python.phase13_handoff.readiness_engine import check_readiness

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

        result = check_readiness(context)
        assert result == ReadinessState.READY_FOR_BROWSER

    def test_high_replayable_reviewed_ready(self):
        """HIGH + REPLAYABLE + reviewed → READY_FOR_BROWSER."""
        from python.phase12_evidence.evidence_types import ConfidenceLevel, EvidenceState
        from python.phase13_handoff.handoff_types import ReadinessState, BugSeverity, TargetType
        from python.phase13_handoff.handoff_context import HandoffContext
        from python.phase13_handoff.readiness_engine import check_readiness

        context = HandoffContext(
            bug_id="BUG-001",
            confidence=ConfidenceLevel.HIGH,
            consistency_state=EvidenceState.REPLAYABLE,
            human_review_completed=True,
            severity=BugSeverity.HIGH,
            target_type=TargetType.PRODUCTION,
            has_active_blockers=False,
            human_confirmed=True
        )

        result = check_readiness(context)
        assert result == ReadinessState.READY_FOR_BROWSER

    def test_high_replayable_no_review_required(self):
        """HIGH + REPLAYABLE + no review → REVIEW_REQUIRED."""
        from python.phase12_evidence.evidence_types import ConfidenceLevel, EvidenceState
        from python.phase13_handoff.handoff_types import ReadinessState, BugSeverity, TargetType
        from python.phase13_handoff.handoff_context import HandoffContext
        from python.phase13_handoff.readiness_engine import check_readiness

        context = HandoffContext(
            bug_id="BUG-001",
            confidence=ConfidenceLevel.HIGH,
            consistency_state=EvidenceState.REPLAYABLE,
            human_review_completed=False,  # No review
            severity=BugSeverity.HIGH,
            target_type=TargetType.PRODUCTION,
            has_active_blockers=False,
            human_confirmed=True
        )

        result = check_readiness(context)
        assert result == ReadinessState.REVIEW_REQUIRED

    def test_high_replayable_with_blockers_not_ready(self):
        """HIGH + REPLAYABLE + reviewed + blockers → NOT_READY."""
        from python.phase12_evidence.evidence_types import ConfidenceLevel, EvidenceState
        from python.phase13_handoff.handoff_types import ReadinessState, BugSeverity, TargetType
        from python.phase13_handoff.handoff_context import HandoffContext
        from python.phase13_handoff.readiness_engine import check_readiness

        context = HandoffContext(
            bug_id="BUG-001",
            confidence=ConfidenceLevel.HIGH,
            consistency_state=EvidenceState.REPLAYABLE,
            human_review_completed=True,
            severity=BugSeverity.HIGH,
            target_type=TargetType.PRODUCTION,
            has_active_blockers=True,  # Blockers
            human_confirmed=True
        )

        result = check_readiness(context)
        assert result == ReadinessState.NOT_READY
