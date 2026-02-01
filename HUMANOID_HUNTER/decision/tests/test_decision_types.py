"""
Phase-32 Decision Types Tests.

Tests for all decision type enums.
"""
import pytest

from HUMANOID_HUNTER.decision import (
    HumanDecision,
    DecisionOutcome,
    EvidenceVisibility
)


class TestHumanDecisionEnum:
    """Test HumanDecision enum."""
    
    def test_continue_exists(self) -> None:
        """CONTINUE decision exists."""
        assert HumanDecision.CONTINUE is not None
        assert HumanDecision.CONTINUE.name == "CONTINUE"
    
    def test_retry_exists(self) -> None:
        """RETRY decision exists."""
        assert HumanDecision.RETRY is not None
        assert HumanDecision.RETRY.name == "RETRY"
    
    def test_abort_exists(self) -> None:
        """ABORT decision exists."""
        assert HumanDecision.ABORT is not None
        assert HumanDecision.ABORT.name == "ABORT"
    
    def test_escalate_exists(self) -> None:
        """ESCALATE decision exists."""
        assert HumanDecision.ESCALATE is not None
        assert HumanDecision.ESCALATE.name == "ESCALATE"
    
    def test_exactly_four_decisions(self) -> None:
        """Verify exactly 4 decision types (closed enum)."""
        assert len(HumanDecision) == 4
    
    def test_all_members_defined(self) -> None:
        """All HumanDecision members are defined."""
        expected = {"CONTINUE", "RETRY", "ABORT", "ESCALATE"}
        actual = {m.name for m in HumanDecision}
        assert actual == expected


class TestDecisionOutcomeEnum:
    """Test DecisionOutcome enum."""
    
    def test_applied_exists(self) -> None:
        """APPLIED outcome exists."""
        assert DecisionOutcome.APPLIED is not None
    
    def test_rejected_exists(self) -> None:
        """REJECTED outcome exists."""
        assert DecisionOutcome.REJECTED is not None
    
    def test_pending_exists(self) -> None:
        """PENDING outcome exists."""
        assert DecisionOutcome.PENDING is not None
    
    def test_timeout_exists(self) -> None:
        """TIMEOUT outcome exists."""
        assert DecisionOutcome.TIMEOUT is not None
    
    def test_exactly_four_outcomes(self) -> None:
        """Verify exactly 4 outcome types (closed enum)."""
        assert len(DecisionOutcome) == 4
    
    def test_all_members_defined(self) -> None:
        """All DecisionOutcome members are defined."""
        expected = {"APPLIED", "REJECTED", "PENDING", "TIMEOUT"}
        actual = {m.name for m in DecisionOutcome}
        assert actual == expected


class TestEvidenceVisibilityEnum:
    """Test EvidenceVisibility enum."""
    
    def test_visible_exists(self) -> None:
        """VISIBLE level exists."""
        assert EvidenceVisibility.VISIBLE is not None
    
    def test_hidden_exists(self) -> None:
        """HIDDEN level exists."""
        assert EvidenceVisibility.HIDDEN is not None
    
    def test_override_required_exists(self) -> None:
        """OVERRIDE_REQUIRED level exists."""
        assert EvidenceVisibility.OVERRIDE_REQUIRED is not None
    
    def test_exactly_three_levels(self) -> None:
        """Verify exactly 3 visibility levels (closed enum)."""
        assert len(EvidenceVisibility) == 3
    
    def test_all_members_defined(self) -> None:
        """All EvidenceVisibility members are defined."""
        expected = {"VISIBLE", "HIDDEN", "OVERRIDE_REQUIRED"}
        actual = {m.name for m in EvidenceVisibility}
        assert actual == expected
