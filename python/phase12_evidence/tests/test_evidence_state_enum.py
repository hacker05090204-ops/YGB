"""
Tests for Phase-12 Evidence State Enum.

Tests:
- EvidenceState enum members
- ConfidenceLevel enum members
- Enum closure (no new members)
"""
import pytest


class TestEvidenceStateEnum:
    """Test EvidenceState enum."""

    def test_has_raw(self):
        """Has RAW member."""
        from python.phase12_evidence.evidence_types import EvidenceState
        assert hasattr(EvidenceState, 'RAW')

    def test_has_consistent(self):
        """Has CONSISTENT member."""
        from python.phase12_evidence.evidence_types import EvidenceState
        assert hasattr(EvidenceState, 'CONSISTENT')

    def test_has_inconsistent(self):
        """Has INCONSISTENT member."""
        from python.phase12_evidence.evidence_types import EvidenceState
        assert hasattr(EvidenceState, 'INCONSISTENT')

    def test_has_replayable(self):
        """Has REPLAYABLE member."""
        from python.phase12_evidence.evidence_types import EvidenceState
        assert hasattr(EvidenceState, 'REPLAYABLE')

    def test_has_unverified(self):
        """Has UNVERIFIED member."""
        from python.phase12_evidence.evidence_types import EvidenceState
        assert hasattr(EvidenceState, 'UNVERIFIED')

    def test_exactly_five_members(self):
        """EvidenceState has exactly 5 members."""
        from python.phase12_evidence.evidence_types import EvidenceState
        assert len(EvidenceState) == 5


class TestConfidenceLevelEnum:
    """Test ConfidenceLevel enum."""

    def test_has_low(self):
        """Has LOW member."""
        from python.phase12_evidence.evidence_types import ConfidenceLevel
        assert hasattr(ConfidenceLevel, 'LOW')

    def test_has_medium(self):
        """Has MEDIUM member."""
        from python.phase12_evidence.evidence_types import ConfidenceLevel
        assert hasattr(ConfidenceLevel, 'MEDIUM')

    def test_has_high(self):
        """Has HIGH member."""
        from python.phase12_evidence.evidence_types import ConfidenceLevel
        assert hasattr(ConfidenceLevel, 'HIGH')

    def test_exactly_three_members(self):
        """ConfidenceLevel has exactly 3 members (no CERTAIN)."""
        from python.phase12_evidence.evidence_types import ConfidenceLevel
        assert len(ConfidenceLevel) == 3

    def test_no_certain_member(self):
        """No CERTAIN or 100% member exists."""
        from python.phase12_evidence.evidence_types import ConfidenceLevel
        assert not hasattr(ConfidenceLevel, 'CERTAIN')
        assert not hasattr(ConfidenceLevel, 'ABSOLUTE')
        assert not hasattr(ConfidenceLevel, 'GUARANTEED')


class TestEnumImmutability:
    """Test enum behavior."""

    def test_evidence_state_is_enum(self):
        """EvidenceState is an Enum."""
        from python.phase12_evidence.evidence_types import EvidenceState
        from enum import Enum
        assert issubclass(EvidenceState, Enum)

    def test_confidence_level_is_enum(self):
        """ConfidenceLevel is an Enum."""
        from python.phase12_evidence.evidence_types import ConfidenceLevel
        from enum import Enum
        assert issubclass(ConfidenceLevel, Enum)
