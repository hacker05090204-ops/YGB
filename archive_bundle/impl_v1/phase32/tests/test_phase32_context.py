"""
Phase-32 Context Tests.

Tests for FROZEN dataclasses:
- EvidenceSummary: 6 fields
- DecisionRequest: 7 fields
- DecisionRecord: 8 fields
- DecisionAudit: 5 fields

Tests enforce:
- Immutability (FrozenInstanceError on mutation)
- Correct field counts
- Valid construction
"""
import pytest
from dataclasses import FrozenInstanceError

from impl_v1.phase32.phase32_types import HumanDecision
from impl_v1.phase32.phase32_context import (
    EvidenceSummary,
    DecisionRequest,
    DecisionRecord,
    DecisionAudit,
)


class TestEvidenceSummaryFrozen:
    """Tests for EvidenceSummary frozen dataclass."""

    def test_evidence_summary_has_6_fields(self) -> None:
        """EvidenceSummary must have exactly 6 fields."""
        from dataclasses import fields
        assert len(fields(EvidenceSummary)) == 6

    def test_evidence_summary_can_be_created(self) -> None:
        """EvidenceSummary can be created with valid data."""
        summary = EvidenceSummary(
            observation_point="PRE_DISPATCH",
            evidence_type="STATE_TRANSITION",
            timestamp="2026-01-26T12:00:00Z",
            chain_length=5,
            execution_state="DISPATCHED",
            confidence_score=0.85
        )
        assert summary.observation_point == "PRE_DISPATCH"
        assert summary.evidence_type == "STATE_TRANSITION"
        assert summary.chain_length == 5
        assert summary.confidence_score == 0.85

    def test_evidence_summary_is_immutable_observation_point(self) -> None:
        """EvidenceSummary.observation_point cannot be mutated."""
        summary = EvidenceSummary(
            observation_point="PRE_DISPATCH",
            evidence_type="STATE_TRANSITION",
            timestamp="2026-01-26T12:00:00Z",
            chain_length=5,
            execution_state="DISPATCHED",
            confidence_score=0.85
        )
        with pytest.raises(FrozenInstanceError):
            summary.observation_point = "POST_DISPATCH"  # type: ignore

    def test_evidence_summary_is_immutable_chain_length(self) -> None:
        """EvidenceSummary.chain_length cannot be mutated."""
        summary = EvidenceSummary(
            observation_point="PRE_DISPATCH",
            evidence_type="STATE_TRANSITION",
            timestamp="2026-01-26T12:00:00Z",
            chain_length=5,
            execution_state="DISPATCHED",
            confidence_score=0.85
        )
        with pytest.raises(FrozenInstanceError):
            summary.chain_length = 10  # type: ignore


class TestDecisionRequestFrozen:
    """Tests for DecisionRequest frozen dataclass."""

    def test_decision_request_has_7_fields(self) -> None:
        """DecisionRequest must have exactly 7 fields."""
        from dataclasses import fields
        assert len(fields(DecisionRequest)) == 7

    def test_decision_request_can_be_created(self) -> None:
        """DecisionRequest can be created with valid data."""
        summary = EvidenceSummary(
            observation_point="PRE_DISPATCH",
            evidence_type="STATE_TRANSITION",
            timestamp="2026-01-26T12:00:00Z",
            chain_length=5,
            execution_state="DISPATCHED",
            confidence_score=0.85
        )
        request = DecisionRequest(
            request_id="DECISION-REQ-12345678",
            session_id="SESSION-ABCD1234",
            evidence_summary=summary,
            allowed_decisions=(HumanDecision.CONTINUE, HumanDecision.ABORT),
            created_at="2026-01-26T12:00:00Z",
            timeout_at="2026-01-26T12:05:00Z",
            timeout_decision=HumanDecision.ABORT
        )
        assert request.request_id == "DECISION-REQ-12345678"
        assert request.timeout_decision == HumanDecision.ABORT

    def test_decision_request_is_immutable_request_id(self) -> None:
        """DecisionRequest.request_id cannot be mutated."""
        summary = EvidenceSummary(
            observation_point="PRE_DISPATCH",
            evidence_type="STATE_TRANSITION",
            timestamp="2026-01-26T12:00:00Z",
            chain_length=5,
            execution_state="DISPATCHED",
            confidence_score=0.85
        )
        request = DecisionRequest(
            request_id="DECISION-REQ-12345678",
            session_id="SESSION-ABCD1234",
            evidence_summary=summary,
            allowed_decisions=(HumanDecision.CONTINUE, HumanDecision.ABORT),
            created_at="2026-01-26T12:00:00Z",
            timeout_at="2026-01-26T12:05:00Z",
            timeout_decision=HumanDecision.ABORT
        )
        with pytest.raises(FrozenInstanceError):
            request.request_id = "NEW-ID"  # type: ignore

    def test_decision_request_is_immutable_timeout_decision(self) -> None:
        """DecisionRequest.timeout_decision cannot be mutated."""
        summary = EvidenceSummary(
            observation_point="PRE_DISPATCH",
            evidence_type="STATE_TRANSITION",
            timestamp="2026-01-26T12:00:00Z",
            chain_length=5,
            execution_state="DISPATCHED",
            confidence_score=0.85
        )
        request = DecisionRequest(
            request_id="DECISION-REQ-12345678",
            session_id="SESSION-ABCD1234",
            evidence_summary=summary,
            allowed_decisions=(HumanDecision.CONTINUE, HumanDecision.ABORT),
            created_at="2026-01-26T12:00:00Z",
            timeout_at="2026-01-26T12:05:00Z",
            timeout_decision=HumanDecision.ABORT
        )
        with pytest.raises(FrozenInstanceError):
            request.timeout_decision = HumanDecision.CONTINUE  # type: ignore


class TestDecisionRecordFrozen:
    """Tests for DecisionRecord frozen dataclass."""

    def test_decision_record_has_8_fields(self) -> None:
        """DecisionRecord must have exactly 8 fields."""
        from dataclasses import fields
        assert len(fields(DecisionRecord)) == 8

    def test_decision_record_can_be_created(self) -> None:
        """DecisionRecord can be created with valid data."""
        record = DecisionRecord(
            decision_id="DECISION-12345678",
            request_id="DECISION-REQ-12345678",
            human_id="human@example.com",
            decision=HumanDecision.CONTINUE,
            reason=None,
            escalation_target=None,
            timestamp="2026-01-26T12:01:00Z",
            evidence_chain_hash="abc123def456"
        )
        assert record.decision_id == "DECISION-12345678"
        assert record.decision == HumanDecision.CONTINUE

    def test_decision_record_can_be_created_with_reason(self) -> None:
        """DecisionRecord can be created with reason for RETRY."""
        record = DecisionRecord(
            decision_id="DECISION-12345678",
            request_id="DECISION-REQ-12345678",
            human_id="human@example.com",
            decision=HumanDecision.RETRY,
            reason="Transient network error",
            escalation_target=None,
            timestamp="2026-01-26T12:01:00Z",
            evidence_chain_hash="abc123def456"
        )
        assert record.reason == "Transient network error"

    def test_decision_record_can_be_created_with_escalation(self) -> None:
        """DecisionRecord can be created with escalation target."""
        record = DecisionRecord(
            decision_id="DECISION-12345678",
            request_id="DECISION-REQ-12345678",
            human_id="human@example.com",
            decision=HumanDecision.ESCALATE,
            reason="Need manager approval",
            escalation_target="manager@example.com",
            timestamp="2026-01-26T12:01:00Z",
            evidence_chain_hash="abc123def456"
        )
        assert record.escalation_target == "manager@example.com"

    def test_decision_record_is_immutable_decision_id(self) -> None:
        """DecisionRecord.decision_id cannot be mutated."""
        record = DecisionRecord(
            decision_id="DECISION-12345678",
            request_id="DECISION-REQ-12345678",
            human_id="human@example.com",
            decision=HumanDecision.CONTINUE,
            reason=None,
            escalation_target=None,
            timestamp="2026-01-26T12:01:00Z",
            evidence_chain_hash="abc123def456"
        )
        with pytest.raises(FrozenInstanceError):
            record.decision_id = "NEW-ID"  # type: ignore

    def test_decision_record_is_immutable_decision(self) -> None:
        """DecisionRecord.decision cannot be mutated."""
        record = DecisionRecord(
            decision_id="DECISION-12345678",
            request_id="DECISION-REQ-12345678",
            human_id="human@example.com",
            decision=HumanDecision.CONTINUE,
            reason=None,
            escalation_target=None,
            timestamp="2026-01-26T12:01:00Z",
            evidence_chain_hash="abc123def456"
        )
        with pytest.raises(FrozenInstanceError):
            record.decision = HumanDecision.ABORT  # type: ignore


class TestDecisionAuditFrozen:
    """Tests for DecisionAudit frozen dataclass."""

    def test_decision_audit_has_5_fields(self) -> None:
        """DecisionAudit must have exactly 5 fields."""
        from dataclasses import fields
        assert len(fields(DecisionAudit)) == 5

    def test_decision_audit_can_be_created_empty(self) -> None:
        """DecisionAudit can be created with no records."""
        audit = DecisionAudit(
            audit_id="AUDIT-12345678",
            records=(),
            session_id="SESSION-ABCD1234",
            head_hash="",
            length=0
        )
        assert audit.audit_id == "AUDIT-12345678"
        assert len(audit.records) == 0
        assert audit.length == 0

    def test_decision_audit_can_be_created_with_records(self) -> None:
        """DecisionAudit can be created with records."""
        record = DecisionRecord(
            decision_id="DECISION-12345678",
            request_id="DECISION-REQ-12345678",
            human_id="human@example.com",
            decision=HumanDecision.CONTINUE,
            reason=None,
            escalation_target=None,
            timestamp="2026-01-26T12:01:00Z",
            evidence_chain_hash="abc123def456"
        )
        audit = DecisionAudit(
            audit_id="AUDIT-12345678",
            records=(record,),
            session_id="SESSION-ABCD1234",
            head_hash="somehash",
            length=1
        )
        assert len(audit.records) == 1
        assert audit.length == 1

    def test_decision_audit_is_immutable_audit_id(self) -> None:
        """DecisionAudit.audit_id cannot be mutated."""
        audit = DecisionAudit(
            audit_id="AUDIT-12345678",
            records=(),
            session_id="SESSION-ABCD1234",
            head_hash="",
            length=0
        )
        with pytest.raises(FrozenInstanceError):
            audit.audit_id = "NEW-ID"  # type: ignore

    def test_decision_audit_is_immutable_records(self) -> None:
        """DecisionAudit.records cannot be mutated."""
        audit = DecisionAudit(
            audit_id="AUDIT-12345678",
            records=(),
            session_id="SESSION-ABCD1234",
            head_hash="",
            length=0
        )
        with pytest.raises(FrozenInstanceError):
            audit.records = (None,)  # type: ignore

    def test_decision_audit_is_immutable_length(self) -> None:
        """DecisionAudit.length cannot be mutated."""
        audit = DecisionAudit(
            audit_id="AUDIT-12345678",
            records=(),
            session_id="SESSION-ABCD1234",
            head_hash="",
            length=0
        )
        with pytest.raises(FrozenInstanceError):
            audit.length = 99  # type: ignore
