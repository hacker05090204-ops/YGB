"""
Tests for Phase-12 Replay Readiness.

Tests:
- Replay decision table
- Determinism verification
- External dependency detection
"""
import pytest


class TestReplayDecisionTable:
    """Test replay readiness decision table."""

    def test_no_steps_not_replayable(self):
        """No replay steps → not replayable."""
        from python.phase12_evidence.evidence_context import EvidenceBundle
        from python.phase12_evidence.consistency_engine import check_replay_readiness

        bundle = EvidenceBundle(
            bundle_id="B-001",
            target_id="T-001",
            sources=frozenset(),
            replay_steps=None
        )

        result = check_replay_readiness(bundle)
        assert result.is_replayable is False
        assert result.reason_code == "RP-001"

    def test_empty_steps_not_replayable(self):
        """Empty replay steps → not replayable."""
        from python.phase12_evidence.evidence_context import EvidenceBundle
        from python.phase12_evidence.consistency_engine import check_replay_readiness

        bundle = EvidenceBundle(
            bundle_id="B-001",
            target_id="T-001",
            sources=frozenset(),
            replay_steps=()
        )

        result = check_replay_readiness(bundle)
        assert result.is_replayable is False
        assert result.reason_code == "RP-001"

    def test_with_steps_replayable(self):
        """Valid steps without external deps → replayable."""
        from python.phase12_evidence.evidence_context import EvidenceBundle
        from python.phase12_evidence.consistency_engine import check_replay_readiness

        bundle = EvidenceBundle(
            bundle_id="B-001",
            target_id="T-001",
            sources=frozenset(),
            replay_steps=("step1: navigate", "step2: click", "step3: verify")
        )

        result = check_replay_readiness(bundle)
        assert result.is_replayable is True
        assert result.steps_complete is True
        assert result.reason_code == "RP-004"

    def test_non_deterministic_not_replayable(self):
        """Steps with non-deterministic markers → not replayable."""
        from python.phase12_evidence.evidence_context import EvidenceBundle
        from python.phase12_evidence.consistency_engine import check_replay_readiness

        bundle = EvidenceBundle(
            bundle_id="B-001",
            target_id="T-001",
            sources=frozenset(),
            replay_steps=("step1: get RANDOM value", "step2: verify")
        )

        result = check_replay_readiness(bundle)
        assert result.is_replayable is False
        assert result.all_deterministic is False
        assert result.reason_code == "RP-002"

    def test_external_deps_not_replayable(self):
        """Steps with external dependency markers → not replayable."""
        from python.phase12_evidence.evidence_context import EvidenceBundle
        from python.phase12_evidence.consistency_engine import check_replay_readiness

        bundle = EvidenceBundle(
            bundle_id="B-001",
            target_id="T-001",
            sources=frozenset(),
            replay_steps=("step1: fetch from EXTERNAL_API", "step2: verify")
        )

        result = check_replay_readiness(bundle)
        assert result.is_replayable is False
        assert result.has_external_deps is True
        assert result.reason_code == "RP-003"


class TestReplayReadinessResult:
    """Test ReplayReadiness dataclass."""

    def test_replay_readiness_is_frozen(self):
        """ReplayReadiness is frozen."""
        from python.phase12_evidence.consistency_engine import ReplayReadiness

        result = ReplayReadiness(
            bundle_id="B-001",
            is_replayable=True,
            steps_complete=True,
            all_deterministic=True,
            has_external_deps=False,
            reason_code="RP-004",
            reason_description="Replay ready"
        )

        with pytest.raises(Exception):
            result.is_replayable = False
