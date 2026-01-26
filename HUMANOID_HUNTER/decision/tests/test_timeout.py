"""
Phase-32 Timeout Tests.

Tests for timeout handling behavior.
"""
import pytest

from HUMANOID_HUNTER.decision import (
    HumanDecision,
    DecisionRequest,
    create_request,
    create_timeout_decision
)


class TestTimeoutBehavior:
    """Test timeout handling."""
    
    @pytest.fixture
    def sample_request(self) -> DecisionRequest:
        """Create a sample decision request."""
        return create_request(
            session_id="OBS-test123",
            observation_point="PRE_DISPATCH",
            evidence_type="STATE_TRANSITION",
            evidence_timestamp="2026-01-25T19:00:00-05:00",
            chain_length=3,
            execution_state="DISPATCHED",
            confidence_score=0.85,
            chain_hash="abc123hash",
            timeout_seconds=300,
            current_timestamp="2026-01-25T19:01:00-05:00"
        )
    
    def test_timeout_decision_is_always_abort(
        self, sample_request: DecisionRequest
    ) -> None:
        """Request timeout_decision is always ABORT."""
        assert sample_request.timeout_decision == HumanDecision.ABORT
    
    def test_create_timeout_decision_is_abort(
        self, sample_request: DecisionRequest
    ) -> None:
        """create_timeout_decision returns ABORT decision."""
        record = create_timeout_decision(
            request=sample_request,
            timeout_timestamp="2026-01-25T19:06:00-05:00"
        )
        assert record.decision == HumanDecision.ABORT
    
    def test_create_timeout_decision_reason_is_timeout(
        self, sample_request: DecisionRequest
    ) -> None:
        """Timeout decision reason is 'TIMEOUT'."""
        record = create_timeout_decision(
            request=sample_request,
            timeout_timestamp="2026-01-25T19:06:00-05:00"
        )
        assert record.reason == "TIMEOUT"
    
    def test_create_timeout_decision_human_id_is_system(
        self, sample_request: DecisionRequest
    ) -> None:
        """Timeout decision human_id is 'SYSTEM_TIMEOUT'."""
        record = create_timeout_decision(
            request=sample_request,
            timeout_timestamp="2026-01-25T19:06:00-05:00"
        )
        assert record.human_id == "SYSTEM_TIMEOUT"
    
    def test_create_timeout_decision_links_to_request(
        self, sample_request: DecisionRequest
    ) -> None:
        """Timeout decision links to original request."""
        record = create_timeout_decision(
            request=sample_request,
            timeout_timestamp="2026-01-25T19:06:00-05:00"
        )
        assert record.request_id == sample_request.request_id
    
    def test_timeout_decision_has_evidence_hash(
        self, sample_request: DecisionRequest
    ) -> None:
        """Timeout decision captures evidence chain hash."""
        record = create_timeout_decision(
            request=sample_request,
            timeout_timestamp="2026-01-25T19:06:00-05:00"
        )
        assert record.evidence_chain_hash == sample_request.evidence_summary.chain_hash


class TestTimeoutInvariant:
    """Test that timeout always means ABORT."""
    
    def test_multiple_timeout_decisions_all_abort(self) -> None:
        """All timeout decisions are ABORT."""
        for i in range(10):
            request = create_request(
                session_id=f"OBS-test{i}",
                observation_point="PRE_DISPATCH",
                evidence_type="STATE_TRANSITION",
                evidence_timestamp="2026-01-25T19:00:00-05:00",
                chain_length=i,
                execution_state="DISPATCHED",
                confidence_score=0.5,
                chain_hash=f"hash{i}",
                timeout_seconds=300,
                current_timestamp="2026-01-25T19:01:00-05:00"
            )
            
            record = create_timeout_decision(request, "2026-01-25T19:06:00-05:00")
            assert record.decision == HumanDecision.ABORT, \
                f"Timeout decision {i} should be ABORT"
