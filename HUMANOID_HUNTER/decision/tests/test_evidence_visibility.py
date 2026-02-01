"""
Phase-32 Evidence Visibility Tests.

Tests for evidence visibility rules.
"""
import pytest

from HUMANOID_HUNTER.decision import (
    EvidenceVisibility,
    EvidenceSummary,
    get_visibility,
    create_request,
    present_evidence
)


class TestEvidenceVisibilityRules:
    """Test evidence visibility rules."""
    
    def test_observation_point_is_visible(self) -> None:
        """observation_point field is VISIBLE."""
        assert get_visibility("observation_point") == EvidenceVisibility.VISIBLE
    
    def test_evidence_type_is_visible(self) -> None:
        """evidence_type field is VISIBLE."""
        assert get_visibility("evidence_type") == EvidenceVisibility.VISIBLE
    
    def test_timestamp_is_visible(self) -> None:
        """timestamp field is VISIBLE."""
        assert get_visibility("timestamp") == EvidenceVisibility.VISIBLE
    
    def test_chain_length_is_visible(self) -> None:
        """chain_length field is VISIBLE."""
        assert get_visibility("chain_length") == EvidenceVisibility.VISIBLE
    
    def test_execution_state_is_visible(self) -> None:
        """execution_state field is VISIBLE."""
        assert get_visibility("execution_state") == EvidenceVisibility.VISIBLE
    
    def test_confidence_score_is_visible(self) -> None:
        """confidence_score field is VISIBLE."""
        assert get_visibility("confidence_score") == EvidenceVisibility.VISIBLE
    
    def test_chain_hash_is_visible(self) -> None:
        """chain_hash field is VISIBLE."""
        assert get_visibility("chain_hash") == EvidenceVisibility.VISIBLE
    
    def test_raw_data_is_hidden(self) -> None:
        """raw_data field is HIDDEN."""
        assert get_visibility("raw_data") == EvidenceVisibility.HIDDEN
    
    def test_executor_output_is_hidden(self) -> None:
        """executor_output field is HIDDEN."""
        assert get_visibility("executor_output") == EvidenceVisibility.HIDDEN
    
    def test_unknown_field_defaults_to_hidden(self) -> None:
        """Unknown fields default to HIDDEN."""
        assert get_visibility("unknown_field") == EvidenceVisibility.HIDDEN
        assert get_visibility("malicious_payload") == EvidenceVisibility.HIDDEN


class TestEvidenceSummaryNoRawData:
    """Test that EvidenceSummary never contains raw data."""
    
    def test_evidence_summary_has_no_raw_data_field(self) -> None:
        """EvidenceSummary has no raw_data attribute."""
        summary = EvidenceSummary(
            observation_point="PRE_DISPATCH",
            evidence_type="STATE_TRANSITION",
            timestamp="2026-01-25T19:00:00-05:00",
            chain_length=5,
            execution_state="DISPATCHED",
            confidence_score=0.9,
            chain_hash="abc123"
        )
        assert not hasattr(summary, "raw_data")
    
    def test_evidence_summary_has_no_executor_output_field(self) -> None:
        """EvidenceSummary has no executor_output attribute."""
        summary = EvidenceSummary(
            observation_point="PRE_DISPATCH",
            evidence_type="STATE_TRANSITION",
            timestamp="2026-01-25T19:00:00-05:00",
            chain_length=5,
            execution_state="DISPATCHED",
            confidence_score=0.9,
            chain_hash="abc123"
        )
        assert not hasattr(summary, "executor_output")
    
    def test_evidence_summary_fields_are_safe(self) -> None:
        """All EvidenceSummary fields are VISIBLE per visibility rules."""
        fields = ["observation_point", "evidence_type", "timestamp", 
                  "chain_length", "execution_state", "confidence_score", "chain_hash"]
        for field in fields:
            assert get_visibility(field) == EvidenceVisibility.VISIBLE


class TestPresentEvidence:
    """Test present_evidence function."""
    
    def test_present_evidence_returns_summary(self) -> None:
        """present_evidence returns the evidence summary."""
        request = create_request(
            session_id="OBS-test",
            observation_point="PRE_DISPATCH",
            evidence_type="STATE_TRANSITION",
            evidence_timestamp="2026-01-25T19:00:00-05:00",
            chain_length=3,
            execution_state="DISPATCHED",
            confidence_score=0.85,
            chain_hash="abc123",
            timeout_seconds=300,
            current_timestamp="2026-01-25T19:01:00-05:00"
        )
        
        summary = present_evidence(request)
        
        assert summary.observation_point == "PRE_DISPATCH"
        assert summary.evidence_type == "STATE_TRANSITION"
        assert summary.chain_length == 3
        assert summary.confidence_score == 0.85
    
    def test_present_evidence_is_idempotent(self) -> None:
        """present_evidence returns same summary on multiple calls."""
        request = create_request(
            session_id="OBS-test",
            observation_point="PRE_DISPATCH",
            evidence_type="STATE_TRANSITION",
            evidence_timestamp="2026-01-25T19:00:00-05:00",
            chain_length=3,
            execution_state="DISPATCHED",
            confidence_score=0.85,
            chain_hash="abc123",
            timeout_seconds=300,
            current_timestamp="2026-01-25T19:01:00-05:00"
        )
        
        summary1 = present_evidence(request)
        summary2 = present_evidence(request)
        
        assert summary1 == summary2
