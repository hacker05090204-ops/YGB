"""
Tests for Phase-13 Human Presence Rules.

Tests:
- HumanPresence enum members
- Human presence decision table
- CRITICAL bugs require human
"""
import pytest


class TestHumanPresenceEnum:
    """Test HumanPresence enum."""

    def test_has_required(self):
        """Has REQUIRED member."""
        from python.phase13_handoff.handoff_types import HumanPresence
        assert hasattr(HumanPresence, 'REQUIRED')

    def test_has_optional(self):
        """Has OPTIONAL member."""
        from python.phase13_handoff.handoff_types import HumanPresence
        assert hasattr(HumanPresence, 'OPTIONAL')

    def test_has_blocking(self):
        """Has BLOCKING member."""
        from python.phase13_handoff.handoff_types import HumanPresence
        assert hasattr(HumanPresence, 'BLOCKING')

    def test_exactly_three_members(self):
        """HumanPresence has exactly 3 members."""
        from python.phase13_handoff.handoff_types import HumanPresence
        assert len(HumanPresence) == 3


class TestHumanPresenceDecisionTable:
    """Test human presence decision table."""

    def test_not_ready_blocking(self):
        """NOT_READY → BLOCKING."""
        from python.phase12_evidence.evidence_types import ConfidenceLevel, EvidenceState
        from python.phase13_handoff.handoff_types import (
            ReadinessState, HumanPresence, BugSeverity, TargetType
        )
        from python.phase13_handoff.handoff_context import HandoffContext
        from python.phase13_handoff.readiness_engine import determine_human_presence

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

        result = determine_human_presence(ReadinessState.NOT_READY, context)
        assert result == HumanPresence.BLOCKING

    def test_review_required_required(self):
        """REVIEW_REQUIRED → REQUIRED."""
        from python.phase12_evidence.evidence_types import ConfidenceLevel, EvidenceState
        from python.phase13_handoff.handoff_types import (
            ReadinessState, HumanPresence, BugSeverity, TargetType
        )
        from python.phase13_handoff.handoff_context import HandoffContext
        from python.phase13_handoff.readiness_engine import determine_human_presence

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

        result = determine_human_presence(ReadinessState.REVIEW_REQUIRED, context)
        assert result == HumanPresence.REQUIRED

    def test_ready_critical_required(self):
        """READY + CRITICAL → REQUIRED."""
        from python.phase12_evidence.evidence_types import ConfidenceLevel, EvidenceState
        from python.phase13_handoff.handoff_types import (
            ReadinessState, HumanPresence, BugSeverity, TargetType
        )
        from python.phase13_handoff.handoff_context import HandoffContext
        from python.phase13_handoff.readiness_engine import determine_human_presence

        context = HandoffContext(
            bug_id="BUG-001",
            confidence=ConfidenceLevel.HIGH,
            consistency_state=EvidenceState.CONSISTENT,
            human_review_completed=True,
            severity=BugSeverity.CRITICAL,
            target_type=TargetType.STAGING,
            has_active_blockers=False,
            human_confirmed=True
        )

        result = determine_human_presence(ReadinessState.READY_FOR_BROWSER, context)
        assert result == HumanPresence.REQUIRED

    def test_ready_high_production_required(self):
        """READY + HIGH + PRODUCTION → REQUIRED."""
        from python.phase12_evidence.evidence_types import ConfidenceLevel, EvidenceState
        from python.phase13_handoff.handoff_types import (
            ReadinessState, HumanPresence, BugSeverity, TargetType
        )
        from python.phase13_handoff.handoff_context import HandoffContext
        from python.phase13_handoff.readiness_engine import determine_human_presence

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

        result = determine_human_presence(ReadinessState.READY_FOR_BROWSER, context)
        assert result == HumanPresence.REQUIRED

    def test_ready_high_staging_optional(self):
        """READY + HIGH + STAGING → OPTIONAL."""
        from python.phase12_evidence.evidence_types import ConfidenceLevel, EvidenceState
        from python.phase13_handoff.handoff_types import (
            ReadinessState, HumanPresence, BugSeverity, TargetType
        )
        from python.phase13_handoff.handoff_context import HandoffContext
        from python.phase13_handoff.readiness_engine import determine_human_presence

        context = HandoffContext(
            bug_id="BUG-001",
            confidence=ConfidenceLevel.HIGH,
            consistency_state=EvidenceState.CONSISTENT,
            human_review_completed=True,
            severity=BugSeverity.HIGH,
            target_type=TargetType.STAGING,
            has_active_blockers=False,
            human_confirmed=True
        )

        result = determine_human_presence(ReadinessState.READY_FOR_BROWSER, context)
        assert result == HumanPresence.OPTIONAL

    def test_ready_medium_optional(self):
        """READY + MEDIUM → OPTIONAL."""
        from python.phase12_evidence.evidence_types import ConfidenceLevel, EvidenceState
        from python.phase13_handoff.handoff_types import (
            ReadinessState, HumanPresence, BugSeverity, TargetType
        )
        from python.phase13_handoff.handoff_context import HandoffContext
        from python.phase13_handoff.readiness_engine import determine_human_presence

        context = HandoffContext(
            bug_id="BUG-001",
            confidence=ConfidenceLevel.HIGH,
            consistency_state=EvidenceState.CONSISTENT,
            human_review_completed=True,
            severity=BugSeverity.MEDIUM,
            target_type=TargetType.PRODUCTION,
            has_active_blockers=False,
            human_confirmed=True
        )

        result = determine_human_presence(ReadinessState.READY_FOR_BROWSER, context)
        assert result == HumanPresence.OPTIONAL

    def test_ready_low_optional(self):
        """READY + LOW → OPTIONAL."""
        from python.phase12_evidence.evidence_types import ConfidenceLevel, EvidenceState
        from python.phase13_handoff.handoff_types import (
            ReadinessState, HumanPresence, BugSeverity, TargetType
        )
        from python.phase13_handoff.handoff_context import HandoffContext
        from python.phase13_handoff.readiness_engine import determine_human_presence

        context = HandoffContext(
            bug_id="BUG-001",
            confidence=ConfidenceLevel.HIGH,
            consistency_state=EvidenceState.CONSISTENT,
            human_review_completed=True,
            severity=BugSeverity.LOW,
            target_type=TargetType.PRODUCTION,
            has_active_blockers=False,
            human_confirmed=True
        )

        result = determine_human_presence(ReadinessState.READY_FOR_BROWSER, context)
        assert result == HumanPresence.OPTIONAL
