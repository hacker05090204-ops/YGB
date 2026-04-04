"""
Phase-32 Engine Tests.

Tests for VALIDATION-ONLY functions:
- validate_decision_id
- validate_decision_record
- validate_evidence_visibility
- validate_audit_chain
- get_decision_outcome
- is_decision_final

Tests enforce:
- Deny-by-default (None, empty, malformed)
- Negative paths > positive paths
- Pure validation (no side effects)
"""
import pytest
import hashlib

from impl_v1.phase32.phase32_types import (
    HumanDecision,
    DecisionOutcome,
    EvidenceVisibility,
)
from impl_v1.phase32.phase32_context import (
    DecisionRecord,
    DecisionAudit,
)
from impl_v1.phase32.phase32_engine import (
    validate_decision_id,
    validate_decision_record,
    validate_evidence_visibility,
    validate_audit_chain,
    get_decision_outcome,
    is_decision_final,
    _compute_record_hash,
)


# --- Helper to create valid records ---

def _make_valid_record(
    decision_id: str = "DECISION-12345678",
    request_id: str = "DECISION-REQ-12345678",
    human_id: str = "human@example.com",
    decision: HumanDecision = HumanDecision.CONTINUE,
    reason: str | None = None,
    escalation_target: str | None = None,
    timestamp: str = "2026-01-26T12:00:00Z",
    evidence_chain_hash: str = "abc123def456"
) -> DecisionRecord:
    return DecisionRecord(
        decision_id=decision_id,
        request_id=request_id,
        human_id=human_id,
        decision=decision,
        reason=reason,
        escalation_target=escalation_target,
        timestamp=timestamp,
        evidence_chain_hash=evidence_chain_hash
    )


# ============================================================================
# validate_decision_id TESTS
# ============================================================================

class TestValidateDecisionIdDenyByDefault:
    """Deny-by-default tests for validate_decision_id."""

    def test_none_returns_false(self) -> None:
        """None → False."""
        assert validate_decision_id(None) is False

    def test_empty_string_returns_false(self) -> None:
        """Empty string → False."""
        assert validate_decision_id("") is False

    def test_whitespace_string_returns_false(self) -> None:
        """Whitespace string → False."""
        assert validate_decision_id("   ") is False

    def test_non_string_returns_false(self) -> None:
        """Non-string → False."""
        assert validate_decision_id(12345) is False  # type: ignore
        assert validate_decision_id([]) is False  # type: ignore
        assert validate_decision_id({}) is False  # type: ignore

    def test_wrong_prefix_returns_false(self) -> None:
        """Wrong prefix → False."""
        assert validate_decision_id("INTENT-12345678") is False
        assert validate_decision_id("decision-12345678") is False
        assert validate_decision_id("ID-12345678") is False

    def test_short_hex_returns_false(self) -> None:
        """Too short hex → False."""
        assert validate_decision_id("DECISION-1234567") is False
        assert validate_decision_id("DECISION-123") is False

    def test_invalid_hex_characters_returns_false(self) -> None:
        """Non-hex characters → False."""
        assert validate_decision_id("DECISION-1234567g") is False
        assert validate_decision_id("DECISION-zzzzzzzz") is False


class TestValidateDecisionIdPositive:
    """Positive tests for validate_decision_id."""

    def test_valid_8_char_hex_returns_true(self) -> None:
        """Valid 8-char hex → True."""
        assert validate_decision_id("DECISION-12345678") is True
        assert validate_decision_id("DECISION-abcdef12") is True
        assert validate_decision_id("DECISION-ABCDEF12") is True

    def test_valid_longer_hex_returns_true(self) -> None:
        """Longer hex → True."""
        assert validate_decision_id("DECISION-1234567890abcdef") is True
        assert validate_decision_id("DECISION-123456789012345678901234") is True


# ============================================================================
# validate_decision_record TESTS
# ============================================================================

class TestValidateDecisionRecordDenyByDefault:
    """Deny-by-default tests for validate_decision_record."""

    def test_none_returns_false(self) -> None:
        """None → False."""
        assert validate_decision_record(None) is False

    def test_invalid_decision_id_returns_false(self) -> None:
        """Invalid decision_id → False."""
        record = _make_valid_record(decision_id="INVALID-ID")
        assert validate_decision_record(record) is False

    def test_empty_decision_id_returns_false(self) -> None:
        """Empty decision_id → False."""
        record = _make_valid_record(decision_id="")
        assert validate_decision_record(record) is False

    def test_invalid_request_id_returns_false(self) -> None:
        """Invalid request_id → False."""
        record = _make_valid_record(request_id="INVALID-REQ")
        assert validate_decision_record(record) is False

    def test_empty_request_id_returns_false(self) -> None:
        """Empty request_id → False."""
        record = _make_valid_record(request_id="")
        assert validate_decision_record(record) is False

    def test_empty_human_id_returns_false(self) -> None:
        """Empty human_id → False."""
        record = _make_valid_record(human_id="")
        assert validate_decision_record(record) is False

    def test_whitespace_human_id_returns_false(self) -> None:
        """Whitespace human_id → False."""
        record = _make_valid_record(human_id="   ")
        assert validate_decision_record(record) is False

    def test_retry_without_reason_returns_false(self) -> None:
        """RETRY without reason → False."""
        record = _make_valid_record(
            decision=HumanDecision.RETRY,
            reason=None
        )
        assert validate_decision_record(record) is False

    def test_retry_with_empty_reason_returns_false(self) -> None:
        """RETRY with empty reason → False."""
        record = _make_valid_record(
            decision=HumanDecision.RETRY,
            reason=""
        )
        assert validate_decision_record(record) is False

    def test_retry_with_whitespace_reason_returns_false(self) -> None:
        """RETRY with whitespace reason → False."""
        record = _make_valid_record(
            decision=HumanDecision.RETRY,
            reason="   "
        )
        assert validate_decision_record(record) is False

    def test_escalate_without_reason_returns_false(self) -> None:
        """ESCALATE without reason → False."""
        record = _make_valid_record(
            decision=HumanDecision.ESCALATE,
            reason=None,
            escalation_target="manager@example.com"
        )
        assert validate_decision_record(record) is False

    def test_escalate_without_target_returns_false(self) -> None:
        """ESCALATE without target → False."""
        record = _make_valid_record(
            decision=HumanDecision.ESCALATE,
            reason="Need approval",
            escalation_target=None
        )
        assert validate_decision_record(record) is False

    def test_escalate_with_empty_target_returns_false(self) -> None:
        """ESCALATE with empty target → False."""
        record = _make_valid_record(
            decision=HumanDecision.ESCALATE,
            reason="Need approval",
            escalation_target=""
        )
        assert validate_decision_record(record) is False

    def test_empty_timestamp_returns_false(self) -> None:
        """Empty timestamp → False."""
        record = _make_valid_record(timestamp="")
        assert validate_decision_record(record) is False

    def test_empty_evidence_chain_hash_returns_false(self) -> None:
        """Empty evidence_chain_hash → False."""
        record = _make_valid_record(evidence_chain_hash="")
        assert validate_decision_record(record) is False

    def test_whitespace_timestamp_returns_false(self) -> None:
        """Whitespace-only timestamp → False."""
        record = _make_valid_record(timestamp="   ")
        assert validate_decision_record(record) is False

    def test_whitespace_evidence_chain_hash_returns_false(self) -> None:
        """Whitespace-only evidence_chain_hash → False."""
        record = _make_valid_record(evidence_chain_hash="   ")
        assert validate_decision_record(record) is False

    def test_non_human_decision_type_returns_false(self) -> None:
        """Non-HumanDecision type in decision field → False."""
        # Create a record with an invalid decision type (string instead of HumanDecision)
        invalid_record = DecisionRecord(
            decision_id="DECISION-12345678",
            request_id="DECISION-REQ-12345678",
            human_id="human@example.com",
            decision="CONTINUE",  # type: ignore - intentionally wrong type
            reason=None,
            escalation_target=None,
            timestamp="2026-01-26T12:00:00Z",
            evidence_chain_hash="abc123def456"
        )
        assert validate_decision_record(invalid_record) is False


class TestValidateDecisionRecordPositive:
    """Positive tests for validate_decision_record."""

    def test_valid_continue_record_returns_true(self) -> None:
        """Valid CONTINUE record → True."""
        record = _make_valid_record(decision=HumanDecision.CONTINUE)
        assert validate_decision_record(record) is True

    def test_valid_abort_record_returns_true(self) -> None:
        """Valid ABORT record → True."""
        record = _make_valid_record(decision=HumanDecision.ABORT)
        assert validate_decision_record(record) is True

    def test_valid_retry_record_with_reason_returns_true(self) -> None:
        """Valid RETRY record with reason → True."""
        record = _make_valid_record(
            decision=HumanDecision.RETRY,
            reason="Transient error"
        )
        assert validate_decision_record(record) is True

    def test_valid_escalate_record_returns_true(self) -> None:
        """Valid ESCALATE record → True."""
        record = _make_valid_record(
            decision=HumanDecision.ESCALATE,
            reason="Need manager approval",
            escalation_target="manager@example.com"
        )
        assert validate_decision_record(record) is True


# ============================================================================
# validate_evidence_visibility TESTS
# ============================================================================

class TestValidateEvidenceVisibilityDenyByDefault:
    """Deny-by-default tests for validate_evidence_visibility."""

    def test_none_returns_hidden(self) -> None:
        """None → HIDDEN."""
        assert validate_evidence_visibility(None) == EvidenceVisibility.HIDDEN

    def test_empty_returns_hidden(self) -> None:
        """Empty string → HIDDEN."""
        assert validate_evidence_visibility("") == EvidenceVisibility.HIDDEN

    def test_whitespace_returns_hidden(self) -> None:
        """Whitespace → HIDDEN."""
        assert validate_evidence_visibility("   ") == EvidenceVisibility.HIDDEN

    def test_non_string_returns_hidden(self) -> None:
        """Non-string → HIDDEN."""
        assert validate_evidence_visibility(123) == EvidenceVisibility.HIDDEN  # type: ignore
        assert validate_evidence_visibility([]) == EvidenceVisibility.HIDDEN  # type: ignore

    def test_unknown_field_returns_hidden(self) -> None:
        """Unknown field → HIDDEN."""
        assert validate_evidence_visibility("unknown_field") == EvidenceVisibility.HIDDEN
        assert validate_evidence_visibility("secret_data") == EvidenceVisibility.HIDDEN


class TestValidateEvidenceVisibilityPositive:
    """Positive tests for validate_evidence_visibility."""

    def test_observation_point_is_visible(self) -> None:
        """observation_point → VISIBLE."""
        assert validate_evidence_visibility("observation_point") == EvidenceVisibility.VISIBLE

    def test_evidence_type_is_visible(self) -> None:
        """evidence_type → VISIBLE."""
        assert validate_evidence_visibility("evidence_type") == EvidenceVisibility.VISIBLE

    def test_timestamp_is_visible(self) -> None:
        """timestamp → VISIBLE."""
        assert validate_evidence_visibility("timestamp") == EvidenceVisibility.VISIBLE

    def test_chain_length_is_visible(self) -> None:
        """chain_length → VISIBLE."""
        assert validate_evidence_visibility("chain_length") == EvidenceVisibility.VISIBLE

    def test_execution_state_is_visible(self) -> None:
        """execution_state → VISIBLE."""
        assert validate_evidence_visibility("execution_state") == EvidenceVisibility.VISIBLE

    def test_confidence_score_is_visible(self) -> None:
        """confidence_score → VISIBLE."""
        assert validate_evidence_visibility("confidence_score") == EvidenceVisibility.VISIBLE

    def test_raw_data_is_hidden(self) -> None:
        """raw_data → HIDDEN."""
        assert validate_evidence_visibility("raw_data") == EvidenceVisibility.HIDDEN

    def test_self_hash_is_visible(self) -> None:
        """self_hash → VISIBLE."""
        assert validate_evidence_visibility("self_hash") == EvidenceVisibility.VISIBLE

    def test_prior_hash_is_visible(self) -> None:
        """prior_hash → VISIBLE."""
        assert validate_evidence_visibility("prior_hash") == EvidenceVisibility.VISIBLE


# ============================================================================
# validate_audit_chain TESTS
# ============================================================================

class TestValidateAuditChainDenyByDefault:
    """Deny-by-default tests for validate_audit_chain."""

    def test_none_returns_false(self) -> None:
        """None → False."""
        assert validate_audit_chain(None) is False

    def test_empty_audit_id_returns_false(self) -> None:
        """Empty audit_id → False."""
        audit = DecisionAudit(
            audit_id="",
            records=(),
            session_id="SESSION-123",
            head_hash="",
            length=0
        )
        assert validate_audit_chain(audit) is False

    def test_whitespace_audit_id_returns_false(self) -> None:
        """Whitespace audit_id → False."""
        audit = DecisionAudit(
            audit_id="   ",
            records=(),
            session_id="SESSION-123",
            head_hash="",
            length=0
        )
        assert validate_audit_chain(audit) is False

    def test_empty_session_id_returns_false(self) -> None:
        """Empty session_id → False."""
        audit = DecisionAudit(
            audit_id="AUDIT-123",
            records=(),
            session_id="",
            head_hash="",
            length=0
        )
        assert validate_audit_chain(audit) is False

    def test_length_mismatch_returns_false(self) -> None:
        """length != len(records) → False."""
        record = _make_valid_record()
        audit = DecisionAudit(
            audit_id="AUDIT-123",
            records=(record,),
            session_id="SESSION-123",
            head_hash="somehash",
            length=5  # Wrong!
        )
        assert validate_audit_chain(audit) is False

    def test_wrong_head_hash_returns_false(self) -> None:
        """Wrong head_hash → False."""
        record = _make_valid_record()
        # Compute correct hash
        correct_hash = _compute_record_hash(
            record.decision_id,
            record.request_id,
            record.human_id,
            record.decision.name,
            record.timestamp,
            ""
        )
        audit = DecisionAudit(
            audit_id="AUDIT-123",
            records=(record,),
            session_id="SESSION-123",
            head_hash="WRONGHASH",  # Wrong!
            length=1
        )
        assert validate_audit_chain(audit) is False

    def test_whitespace_session_id_returns_false(self) -> None:
        """Whitespace session_id → False."""
        audit = DecisionAudit(
            audit_id="AUDIT-123",
            records=(),
            session_id="   ",  # Whitespace only
            head_hash="",
            length=0
        )
        assert validate_audit_chain(audit) is False

    def test_invalid_record_in_audit_returns_false(self) -> None:
        """Invalid record in audit → False."""
        # Create an invalid record (empty decision_id)
        invalid_record = DecisionRecord(
            decision_id="",  # Invalid!
            request_id="DECISION-REQ-12345678",
            human_id="human@example.com",
            decision=HumanDecision.CONTINUE,
            reason=None,
            escalation_target=None,
            timestamp="2026-01-26T12:00:00Z",
            evidence_chain_hash="abc123"
        )
        audit = DecisionAudit(
            audit_id="AUDIT-123",
            records=(invalid_record,),
            session_id="SESSION-123",
            head_hash="somehash",
            length=1
        )
        assert validate_audit_chain(audit) is False


class TestValidateAuditChainPositive:
    """Positive tests for validate_audit_chain."""

    def test_empty_audit_with_empty_hash_and_zero_length_returns_true(self) -> None:
        """Empty audit with head_hash='' and length=0 → True."""
        audit = DecisionAudit(
            audit_id="AUDIT-123",
            records=(),
            session_id="SESSION-123",
            head_hash="",
            length=0
        )
        assert validate_audit_chain(audit) is True

    def test_single_record_with_correct_hash_returns_true(self) -> None:
        """Single record with correct hash → True."""
        record = _make_valid_record()
        # Compute correct hash
        correct_hash = _compute_record_hash(
            record.decision_id,
            record.request_id,
            record.human_id,
            record.decision.name,
            record.timestamp,
            ""
        )
        audit = DecisionAudit(
            audit_id="AUDIT-123",
            records=(record,),
            session_id="SESSION-123",
            head_hash=correct_hash,
            length=1
        )
        assert validate_audit_chain(audit) is True


# ============================================================================
# get_decision_outcome TESTS
# ============================================================================

class TestGetDecisionOutcomeDenyByDefault:
    """Deny-by-default tests for get_decision_outcome."""

    def test_none_record_returns_rejected(self) -> None:
        """None record → REJECTED."""
        assert get_decision_outcome(None, "DISPATCHED") == DecisionOutcome.REJECTED

    def test_invalid_record_returns_rejected(self) -> None:
        """Invalid record → REJECTED."""
        record = _make_valid_record(decision_id="INVALID")
        assert get_decision_outcome(record, "DISPATCHED") == DecisionOutcome.REJECTED

    def test_none_state_returns_rejected(self) -> None:
        """None state → REJECTED."""
        record = _make_valid_record()
        assert get_decision_outcome(record, None) == DecisionOutcome.REJECTED

    def test_empty_state_returns_rejected(self) -> None:
        """Empty state → REJECTED."""
        record = _make_valid_record()
        assert get_decision_outcome(record, "") == DecisionOutcome.REJECTED

    def test_whitespace_state_returns_rejected(self) -> None:
        """Whitespace state → REJECTED."""
        record = _make_valid_record()
        assert get_decision_outcome(record, "   ") == DecisionOutcome.REJECTED


class TestGetDecisionOutcomePositive:
    """Positive tests for get_decision_outcome."""

    def test_abort_always_returns_applied(self) -> None:
        """ABORT decision → APPLIED (always allowed)."""
        record = _make_valid_record(decision=HumanDecision.ABORT)
        assert get_decision_outcome(record, "DISPATCHED") == DecisionOutcome.APPLIED

    def test_continue_returns_pending(self) -> None:
        """CONTINUE decision → PENDING (safe default)."""
        record = _make_valid_record(decision=HumanDecision.CONTINUE)
        assert get_decision_outcome(record, "DISPATCHED") == DecisionOutcome.PENDING

    def test_retry_returns_pending(self) -> None:
        """RETRY decision → PENDING (safe default)."""
        record = _make_valid_record(
            decision=HumanDecision.RETRY,
            reason="Transient error"
        )
        assert get_decision_outcome(record, "DISPATCHED") == DecisionOutcome.PENDING

    def test_escalate_returns_pending(self) -> None:
        """ESCALATE decision → PENDING (safe default)."""
        record = _make_valid_record(
            decision=HumanDecision.ESCALATE,
            reason="Need approval",
            escalation_target="manager@example.com"
        )
        assert get_decision_outcome(record, "DISPATCHED") == DecisionOutcome.PENDING


# ============================================================================
# is_decision_final TESTS
# ============================================================================

class TestIsDecisionFinalDenyByDefault:
    """Deny-by-default tests for is_decision_final."""

    def test_none_returns_false(self) -> None:
        """None → False."""
        assert is_decision_final(None) is False

    def test_non_human_decision_returns_false(self) -> None:
        """Non-HumanDecision → False."""
        assert is_decision_final("ABORT") is False  # type: ignore
        assert is_decision_final(123) is False  # type: ignore
        assert is_decision_final(DecisionOutcome.APPLIED) is False  # type: ignore


class TestIsDecisionFinalPositive:
    """Positive tests for is_decision_final."""

    def test_abort_is_final(self) -> None:
        """ABORT → True (final)."""
        assert is_decision_final(HumanDecision.ABORT) is True

    def test_continue_is_final(self) -> None:
        """CONTINUE → True (final, moves to next step)."""
        assert is_decision_final(HumanDecision.CONTINUE) is True

    def test_retry_is_not_final(self) -> None:
        """RETRY → False (can be retried again)."""
        assert is_decision_final(HumanDecision.RETRY) is False

    def test_escalate_is_not_final(self) -> None:
        """ESCALATE → False (awaiting higher authority)."""
        assert is_decision_final(HumanDecision.ESCALATE) is False
