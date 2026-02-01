"""
Phase-32 Types Tests.

Tests for CLOSED enums:
- HumanDecision: 4 members
- DecisionOutcome: 4 members
- EvidenceVisibility: 3 members

Tests enforce:
- Exact member counts (closedness)
- No additional members
- Correct member names/values
"""
import pytest

from impl_v1.phase32.phase32_types import (
    HumanDecision,
    DecisionOutcome,
    EvidenceVisibility,
)


class TestHumanDecisionEnum:
    """Tests for HumanDecision enum closedness."""

    def test_human_decision_has_exactly_4_members(self) -> None:
        """HumanDecision must have exactly 4 members."""
        assert len(HumanDecision) == 4

    def test_human_decision_has_continue(self) -> None:
        """HumanDecision must have CONTINUE."""
        assert HumanDecision.CONTINUE is not None
        assert HumanDecision.CONTINUE.name == "CONTINUE"

    def test_human_decision_has_retry(self) -> None:
        """HumanDecision must have RETRY."""
        assert HumanDecision.RETRY is not None
        assert HumanDecision.RETRY.name == "RETRY"

    def test_human_decision_has_abort(self) -> None:
        """HumanDecision must have ABORT."""
        assert HumanDecision.ABORT is not None
        assert HumanDecision.ABORT.name == "ABORT"

    def test_human_decision_has_escalate(self) -> None:
        """HumanDecision must have ESCALATE."""
        assert HumanDecision.ESCALATE is not None
        assert HumanDecision.ESCALATE.name == "ESCALATE"

    def test_human_decision_all_members_listed(self) -> None:
        """All HumanDecision members must be exactly as expected."""
        expected = {"CONTINUE", "RETRY", "ABORT", "ESCALATE"}
        actual = {m.name for m in HumanDecision}
        assert actual == expected

    def test_human_decision_members_are_distinct(self) -> None:
        """All HumanDecision members must have distinct values."""
        values = [m.value for m in HumanDecision]
        assert len(values) == len(set(values))


class TestDecisionOutcomeEnum:
    """Tests for DecisionOutcome enum closedness."""

    def test_decision_outcome_has_exactly_4_members(self) -> None:
        """DecisionOutcome must have exactly 4 members."""
        assert len(DecisionOutcome) == 4

    def test_decision_outcome_has_applied(self) -> None:
        """DecisionOutcome must have APPLIED."""
        assert DecisionOutcome.APPLIED is not None
        assert DecisionOutcome.APPLIED.name == "APPLIED"

    def test_decision_outcome_has_rejected(self) -> None:
        """DecisionOutcome must have REJECTED."""
        assert DecisionOutcome.REJECTED is not None
        assert DecisionOutcome.REJECTED.name == "REJECTED"

    def test_decision_outcome_has_pending(self) -> None:
        """DecisionOutcome must have PENDING."""
        assert DecisionOutcome.PENDING is not None
        assert DecisionOutcome.PENDING.name == "PENDING"

    def test_decision_outcome_has_timeout(self) -> None:
        """DecisionOutcome must have TIMEOUT."""
        assert DecisionOutcome.TIMEOUT is not None
        assert DecisionOutcome.TIMEOUT.name == "TIMEOUT"

    def test_decision_outcome_all_members_listed(self) -> None:
        """All DecisionOutcome members must be exactly as expected."""
        expected = {"APPLIED", "REJECTED", "PENDING", "TIMEOUT"}
        actual = {m.name for m in DecisionOutcome}
        assert actual == expected

    def test_decision_outcome_members_are_distinct(self) -> None:
        """All DecisionOutcome members must have distinct values."""
        values = [m.value for m in DecisionOutcome]
        assert len(values) == len(set(values))


class TestEvidenceVisibilityEnum:
    """Tests for EvidenceVisibility enum closedness."""

    def test_evidence_visibility_has_exactly_3_members(self) -> None:
        """EvidenceVisibility must have exactly 3 members."""
        assert len(EvidenceVisibility) == 3

    def test_evidence_visibility_has_visible(self) -> None:
        """EvidenceVisibility must have VISIBLE."""
        assert EvidenceVisibility.VISIBLE is not None
        assert EvidenceVisibility.VISIBLE.name == "VISIBLE"

    def test_evidence_visibility_has_hidden(self) -> None:
        """EvidenceVisibility must have HIDDEN."""
        assert EvidenceVisibility.HIDDEN is not None
        assert EvidenceVisibility.HIDDEN.name == "HIDDEN"

    def test_evidence_visibility_has_override_required(self) -> None:
        """EvidenceVisibility must have OVERRIDE_REQUIRED."""
        assert EvidenceVisibility.OVERRIDE_REQUIRED is not None
        assert EvidenceVisibility.OVERRIDE_REQUIRED.name == "OVERRIDE_REQUIRED"

    def test_evidence_visibility_all_members_listed(self) -> None:
        """All EvidenceVisibility members must be exactly as expected."""
        expected = {"VISIBLE", "HIDDEN", "OVERRIDE_REQUIRED"}
        actual = {m.name for m in EvidenceVisibility}
        assert actual == expected

    def test_evidence_visibility_members_are_distinct(self) -> None:
        """All EvidenceVisibility members must have distinct values."""
        values = [m.value for m in EvidenceVisibility]
        assert len(values) == len(set(values))
