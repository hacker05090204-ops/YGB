"""
Tests for Phase-12 Consistency Rules.

Tests:
- Multi-source confirmation
- Consistency decision table
- Source matching
"""
import pytest


class TestConsistencyDecisionTable:
    """Test consistency decision table."""

    def test_zero_sources_unverified(self):
        """Zero sources → UNVERIFIED."""
        from python.phase12_evidence.evidence_types import EvidenceState
        from python.phase12_evidence.evidence_context import EvidenceBundle
        from python.phase12_evidence.consistency_engine import check_consistency

        bundle = EvidenceBundle(
            bundle_id="B-001",
            target_id="T-001",
            sources=frozenset(),
            replay_steps=None
        )

        result = check_consistency(bundle)
        assert result.state == EvidenceState.UNVERIFIED
        assert result.reason_code == "CS-001"

    def test_single_source_raw(self):
        """Single source → RAW."""
        from python.phase12_evidence.evidence_types import EvidenceState
        from python.phase12_evidence.evidence_context import EvidenceBundle, EvidenceSource
        from python.phase12_evidence.consistency_engine import check_consistency

        source = EvidenceSource(
            source_id="S-001",
            finding_hash="abc123",
            target_id="T-001",
            evidence_type="scan",
            timestamp="2026-01-25T00:00:00Z"
        )
        bundle = EvidenceBundle(
            bundle_id="B-001",
            target_id="T-001",
            sources=frozenset({source}),
            replay_steps=None
        )

        result = check_consistency(bundle)
        assert result.state == EvidenceState.RAW
        assert result.reason_code == "CS-002"

    def test_matching_sources_consistent(self):
        """Multiple matching sources → CONSISTENT."""
        from python.phase12_evidence.evidence_types import EvidenceState
        from python.phase12_evidence.evidence_context import EvidenceBundle, EvidenceSource
        from python.phase12_evidence.consistency_engine import check_consistency

        source1 = EvidenceSource(
            source_id="S-001",
            finding_hash="abc123",
            target_id="T-001",
            evidence_type="scan",
            timestamp="2026-01-25T00:00:00Z"
        )
        source2 = EvidenceSource(
            source_id="S-002",
            finding_hash="abc123",  # Same hash = matching
            target_id="T-001",
            evidence_type="scan",
            timestamp="2026-01-25T00:01:00Z"
        )
        bundle = EvidenceBundle(
            bundle_id="B-001",
            target_id="T-001",
            sources=frozenset({source1, source2}),
            replay_steps=None
        )

        result = check_consistency(bundle)
        assert result.state == EvidenceState.CONSISTENT
        assert result.reason_code == "CS-003"
        assert result.conflict_detected is False

    def test_conflicting_sources_inconsistent(self):
        """Conflicting sources → INCONSISTENT."""
        from python.phase12_evidence.evidence_types import EvidenceState
        from python.phase12_evidence.evidence_context import EvidenceBundle, EvidenceSource
        from python.phase12_evidence.consistency_engine import check_consistency

        source1 = EvidenceSource(
            source_id="S-001",
            finding_hash="abc123",
            target_id="T-001",
            evidence_type="scan",
            timestamp="2026-01-25T00:00:00Z"
        )
        source2 = EvidenceSource(
            source_id="S-002",
            finding_hash="xyz789",  # Different hash = conflict
            target_id="T-001",
            evidence_type="scan",
            timestamp="2026-01-25T00:01:00Z"
        )
        bundle = EvidenceBundle(
            bundle_id="B-001",
            target_id="T-001",
            sources=frozenset({source1, source2}),
            replay_steps=None
        )

        result = check_consistency(bundle)
        assert result.state == EvidenceState.INCONSISTENT
        assert result.reason_code == "CS-004"
        assert result.conflict_detected is True


class TestSourceMatching:
    """Test source matching logic."""

    def test_sources_match_true(self):
        """All sources with same hash match."""
        from python.phase12_evidence.evidence_context import EvidenceSource
        from python.phase12_evidence.consistency_engine import sources_match

        s1 = EvidenceSource("S-001", "hash1", "T-001", "scan", "2026-01-25")
        s2 = EvidenceSource("S-002", "hash1", "T-001", "scan", "2026-01-25")
        s3 = EvidenceSource("S-003", "hash1", "T-001", "scan", "2026-01-25")

        assert sources_match(frozenset({s1, s2, s3})) is True

    def test_sources_match_false(self):
        """Different hashes → no match."""
        from python.phase12_evidence.evidence_context import EvidenceSource
        from python.phase12_evidence.consistency_engine import sources_match

        s1 = EvidenceSource("S-001", "hash1", "T-001", "scan", "2026-01-25")
        s2 = EvidenceSource("S-002", "hash2", "T-001", "scan", "2026-01-25")

        assert sources_match(frozenset({s1, s2})) is False

    def test_empty_sources_true(self):
        """Empty sources trivially match."""
        from python.phase12_evidence.consistency_engine import sources_match

        assert sources_match(frozenset()) is True


class TestDataclassFrozen:
    """Test dataclass immutability."""

    def test_evidence_source_is_frozen(self):
        """EvidenceSource is frozen."""
        from python.phase12_evidence.evidence_context import EvidenceSource

        source = EvidenceSource(
            source_id="S-001",
            finding_hash="abc123",
            target_id="T-001",
            evidence_type="scan",
            timestamp="2026-01-25"
        )

        with pytest.raises(Exception):
            source.finding_hash = "MODIFIED"

    def test_evidence_bundle_is_frozen(self):
        """EvidenceBundle is frozen."""
        from python.phase12_evidence.evidence_context import EvidenceBundle

        bundle = EvidenceBundle(
            bundle_id="B-001",
            target_id="T-001",
            sources=frozenset(),
            replay_steps=None
        )

        with pytest.raises(Exception):
            bundle.target_id = "MODIFIED"
