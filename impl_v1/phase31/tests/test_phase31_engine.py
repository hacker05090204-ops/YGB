"""
Phase-31 Engine Tests.

Tests for VALIDATION-ONLY functions:
- validate_evidence_record
- validate_observation_context
- validate_chain_integrity
- is_stop_condition_met
- get_observation_state

Tests enforce:
- Deny-by-default (None, empty, malformed)
- Negative paths > positive paths
- Pure validation (no side effects)
"""
import pytest

from impl_v1.phase31.phase31_types import (
    ObservationPoint,
    EvidenceType,
    StopCondition,
)
from impl_v1.phase31.phase31_context import (
    EvidenceRecord,
    ObservationContext,
    EvidenceChain,
)
from impl_v1.phase31.phase31_engine import (
    validate_evidence_record,
    validate_observation_context,
    validate_chain_integrity,
    is_stop_condition_met,
    get_observation_state,
    _compute_evidence_hash,
)


# --- Helpers ---

def _make_valid_record(
    record_id: str = "EVIDENCE-12345678",
    observation_point: ObservationPoint = ObservationPoint.PRE_DISPATCH,
    evidence_type: EvidenceType = EvidenceType.STATE_TRANSITION,
    timestamp: str = "2026-01-26T12:00:00Z",
    raw_data: bytes = b"test data",
    prior_hash: str = "",
    self_hash: str = "placeholder"
) -> EvidenceRecord:
    # Compute actual self_hash
    actual_hash = _compute_evidence_hash(
        record_id,
        observation_point.name,
        evidence_type.name,
        timestamp,
        raw_data,
        prior_hash
    )
    return EvidenceRecord(
        record_id=record_id,
        observation_point=observation_point,
        evidence_type=evidence_type,
        timestamp=timestamp,
        raw_data=raw_data,
        prior_hash=prior_hash,
        self_hash=actual_hash if self_hash == "placeholder" else self_hash
    )


def _make_valid_context(
    session_id: str = "SESSION-12345678",
    loop_id: str = "LOOP-ABCD1234",
    executor_id: str = "EXECUTOR-001",
    envelope_hash: str = "env_hash_123",
    created_at: str = "2026-01-26T12:00:00Z"
) -> ObservationContext:
    return ObservationContext(
        session_id=session_id,
        loop_id=loop_id,
        executor_id=executor_id,
        envelope_hash=envelope_hash,
        created_at=created_at
    )


# ============================================================================
# validate_evidence_record TESTS
# ============================================================================

class TestValidateEvidenceRecordDenyByDefault:
    """Deny-by-default tests for validate_evidence_record."""

    def test_none_returns_false(self) -> None:
        """None → False."""
        assert validate_evidence_record(None) is False

    def test_empty_record_id_returns_false(self) -> None:
        """Empty record_id → False."""
        record = EvidenceRecord(
            record_id="",
            observation_point=ObservationPoint.PRE_DISPATCH,
            evidence_type=EvidenceType.STATE_TRANSITION,
            timestamp="2026-01-26T12:00:00Z",
            raw_data=b"test",
            prior_hash="",
            self_hash="abc"
        )
        assert validate_evidence_record(record) is False

    def test_invalid_record_id_format_returns_false(self) -> None:
        """Invalid record_id format → False."""
        record = EvidenceRecord(
            record_id="INVALID-12345678",
            observation_point=ObservationPoint.PRE_DISPATCH,
            evidence_type=EvidenceType.STATE_TRANSITION,
            timestamp="2026-01-26T12:00:00Z",
            raw_data=b"test",
            prior_hash="",
            self_hash="abc"
        )
        assert validate_evidence_record(record) is False

    def test_non_observation_point_type_returns_false(self) -> None:
        """Non-ObservationPoint type → False."""
        record = EvidenceRecord(
            record_id="EVIDENCE-12345678",
            observation_point="PRE_DISPATCH",  # type: ignore
            evidence_type=EvidenceType.STATE_TRANSITION,
            timestamp="2026-01-26T12:00:00Z",
            raw_data=b"test",
            prior_hash="",
            self_hash="abc"
        )
        assert validate_evidence_record(record) is False

    def test_non_evidence_type_returns_false(self) -> None:
        """Non-EvidenceType → False."""
        record = EvidenceRecord(
            record_id="EVIDENCE-12345678",
            observation_point=ObservationPoint.PRE_DISPATCH,
            evidence_type="STATE_TRANSITION",  # type: ignore
            timestamp="2026-01-26T12:00:00Z",
            raw_data=b"test",
            prior_hash="",
            self_hash="abc"
        )
        assert validate_evidence_record(record) is False

    def test_empty_timestamp_returns_false(self) -> None:
        """Empty timestamp → False."""
        record = EvidenceRecord(
            record_id="EVIDENCE-12345678",
            observation_point=ObservationPoint.PRE_DISPATCH,
            evidence_type=EvidenceType.STATE_TRANSITION,
            timestamp="",
            raw_data=b"test",
            prior_hash="",
            self_hash="abc"
        )
        assert validate_evidence_record(record) is False

    def test_whitespace_timestamp_returns_false(self) -> None:
        """Whitespace timestamp → False."""
        record = EvidenceRecord(
            record_id="EVIDENCE-12345678",
            observation_point=ObservationPoint.PRE_DISPATCH,
            evidence_type=EvidenceType.STATE_TRANSITION,
            timestamp="   ",
            raw_data=b"test",
            prior_hash="",
            self_hash="abc"
        )
        assert validate_evidence_record(record) is False

    def test_non_bytes_raw_data_returns_false(self) -> None:
        """Non-bytes raw_data → False."""
        record = EvidenceRecord(
            record_id="EVIDENCE-12345678",
            observation_point=ObservationPoint.PRE_DISPATCH,
            evidence_type=EvidenceType.STATE_TRANSITION,
            timestamp="2026-01-26T12:00:00Z",
            raw_data="not bytes",  # type: ignore
            prior_hash="",
            self_hash="abc"
        )
        assert validate_evidence_record(record) is False

    def test_empty_self_hash_returns_false(self) -> None:
        """Empty self_hash → False."""
        record = EvidenceRecord(
            record_id="EVIDENCE-12345678",
            observation_point=ObservationPoint.PRE_DISPATCH,
            evidence_type=EvidenceType.STATE_TRANSITION,
            timestamp="2026-01-26T12:00:00Z",
            raw_data=b"test",
            prior_hash="",
            self_hash=""
        )
        assert validate_evidence_record(record) is False

    def test_whitespace_self_hash_returns_false(self) -> None:
        """Whitespace self_hash → False."""
        record = EvidenceRecord(
            record_id="EVIDENCE-12345678",
            observation_point=ObservationPoint.PRE_DISPATCH,
            evidence_type=EvidenceType.STATE_TRANSITION,
            timestamp="2026-01-26T12:00:00Z",
            raw_data=b"test",
            prior_hash="",
            self_hash="   "
        )
        assert validate_evidence_record(record) is False

    def test_non_string_prior_hash_returns_false(self) -> None:
        """Non-string prior_hash → False."""
        record = EvidenceRecord(
            record_id="EVIDENCE-12345678",
            observation_point=ObservationPoint.PRE_DISPATCH,
            evidence_type=EvidenceType.STATE_TRANSITION,
            timestamp="2026-01-26T12:00:00Z",
            raw_data=b"test",
            prior_hash=123,  # type: ignore
            self_hash="abc"
        )
        assert validate_evidence_record(record) is False


class TestValidateEvidenceRecordPositive:
    """Positive tests for validate_evidence_record."""

    def test_valid_record_returns_true(self) -> None:
        """Valid record → True."""
        record = _make_valid_record()
        assert validate_evidence_record(record) is True

    def test_valid_record_with_prior_hash_returns_true(self) -> None:
        """Valid record with prior_hash → True."""
        record = _make_valid_record(prior_hash="previous_hash_abc123")
        assert validate_evidence_record(record) is True


# ============================================================================
# validate_observation_context TESTS
# ============================================================================

class TestValidateObservationContextDenyByDefault:
    """Deny-by-default tests for validate_observation_context."""

    def test_none_returns_false(self) -> None:
        """None → False."""
        assert validate_observation_context(None) is False

    def test_empty_session_id_returns_false(self) -> None:
        """Empty session_id → False."""
        context = _make_valid_context(session_id="")
        assert validate_observation_context(context) is False

    def test_invalid_session_id_format_returns_false(self) -> None:
        """Invalid session_id format → False."""
        context = _make_valid_context(session_id="INVALID-123")
        assert validate_observation_context(context) is False

    def test_empty_loop_id_returns_false(self) -> None:
        """Empty loop_id → False."""
        context = _make_valid_context(loop_id="")
        assert validate_observation_context(context) is False

    def test_whitespace_loop_id_returns_false(self) -> None:
        """Whitespace loop_id → False."""
        context = _make_valid_context(loop_id="   ")
        assert validate_observation_context(context) is False

    def test_empty_executor_id_returns_false(self) -> None:
        """Empty executor_id → False."""
        context = _make_valid_context(executor_id="")
        assert validate_observation_context(context) is False

    def test_whitespace_executor_id_returns_false(self) -> None:
        """Whitespace executor_id → False."""
        context = _make_valid_context(executor_id="   ")
        assert validate_observation_context(context) is False

    def test_empty_envelope_hash_returns_false(self) -> None:
        """Empty envelope_hash → False."""
        context = _make_valid_context(envelope_hash="")
        assert validate_observation_context(context) is False

    def test_whitespace_envelope_hash_returns_false(self) -> None:
        """Whitespace envelope_hash → False."""
        context = _make_valid_context(envelope_hash="   ")
        assert validate_observation_context(context) is False

    def test_empty_created_at_returns_false(self) -> None:
        """Empty created_at → False."""
        context = _make_valid_context(created_at="")
        assert validate_observation_context(context) is False

    def test_whitespace_created_at_returns_false(self) -> None:
        """Whitespace created_at → False."""
        context = _make_valid_context(created_at="   ")
        assert validate_observation_context(context) is False


class TestValidateObservationContextPositive:
    """Positive tests for validate_observation_context."""

    def test_valid_context_returns_true(self) -> None:
        """Valid context → True."""
        context = _make_valid_context()
        assert validate_observation_context(context) is True


# ============================================================================
# validate_chain_integrity TESTS
# ============================================================================

class TestValidateChainIntegrityDenyByDefault:
    """Deny-by-default tests for validate_chain_integrity."""

    def test_none_returns_false(self) -> None:
        """None → False."""
        assert validate_chain_integrity(None) is False

    def test_empty_chain_id_returns_false(self) -> None:
        """Empty chain_id → False."""
        chain = EvidenceChain(
            chain_id="",
            records=(),
            head_hash="",
            length=0
        )
        assert validate_chain_integrity(chain) is False

    def test_invalid_chain_id_format_returns_false(self) -> None:
        """Invalid chain_id format → False."""
        chain = EvidenceChain(
            chain_id="INVALID-123",
            records=(),
            head_hash="",
            length=0
        )
        assert validate_chain_integrity(chain) is False

    def test_length_mismatch_returns_false(self) -> None:
        """length != len(records) → False."""
        record = _make_valid_record()
        chain = EvidenceChain(
            chain_id="CHAIN-12345678",
            records=(record,),
            head_hash="somehash",
            length=5  # Wrong!
        )
        assert validate_chain_integrity(chain) is False

    def test_wrong_head_hash_returns_false(self) -> None:
        """Wrong head_hash → False."""
        record = _make_valid_record()
        chain = EvidenceChain(
            chain_id="CHAIN-12345678",
            records=(record,),
            head_hash="WRONGHASH",  # Wrong!
            length=1
        )
        assert validate_chain_integrity(chain) is False

    def test_invalid_record_in_chain_returns_false(self) -> None:
        """Invalid record in chain → False."""
        invalid_record = EvidenceRecord(
            record_id="",  # Invalid!
            observation_point=ObservationPoint.PRE_DISPATCH,
            evidence_type=EvidenceType.STATE_TRANSITION,
            timestamp="2026-01-26T12:00:00Z",
            raw_data=b"test",
            prior_hash="",
            self_hash="abc123"
        )
        chain = EvidenceChain(
            chain_id="CHAIN-12345678",
            records=(invalid_record,),
            head_hash="abc123",
            length=1
        )
        assert validate_chain_integrity(chain) is False

    def test_broken_hash_chain_returns_false(self) -> None:
        """Broken hash chain (prior_hash mismatch) → False."""
        record1 = _make_valid_record()
        # Second record with wrong prior_hash
        record2 = _make_valid_record(
            record_id="EVIDENCE-22222222",
            prior_hash="WRONG_PRIOR_HASH"
        )
        chain = EvidenceChain(
            chain_id="CHAIN-12345678",
            records=(record1, record2),
            head_hash=record2.self_hash,
            length=2
        )
        assert validate_chain_integrity(chain) is False

    def test_tampered_self_hash_returns_false(self) -> None:
        """Tampered self_hash → False."""
        record = EvidenceRecord(
            record_id="EVIDENCE-12345678",
            observation_point=ObservationPoint.PRE_DISPATCH,
            evidence_type=EvidenceType.STATE_TRANSITION,
            timestamp="2026-01-26T12:00:00Z",
            raw_data=b"test",
            prior_hash="",
            self_hash="TAMPERED_HASH"
        )
        chain = EvidenceChain(
            chain_id="CHAIN-12345678",
            records=(record,),
            head_hash="TAMPERED_HASH",
            length=1
        )
        assert validate_chain_integrity(chain) is False


class TestValidateChainIntegrityPositive:
    """Positive tests for validate_chain_integrity."""

    def test_empty_chain_valid(self) -> None:
        """Empty chain with head_hash='' and length=0 → True."""
        chain = EvidenceChain(
            chain_id="CHAIN-12345678",
            records=(),
            head_hash="",
            length=0
        )
        assert validate_chain_integrity(chain) is True

    def test_single_record_chain_valid(self) -> None:
        """Single record with correct hash → True."""
        record = _make_valid_record()
        chain = EvidenceChain(
            chain_id="CHAIN-12345678",
            records=(record,),
            head_hash=record.self_hash,
            length=1
        )
        assert validate_chain_integrity(chain) is True

    def test_multi_record_chain_valid(self) -> None:
        """Multiple records with valid hash chain → True."""
        record1 = _make_valid_record()
        record2 = _make_valid_record(
            record_id="EVIDENCE-22222222",
            prior_hash=record1.self_hash
        )
        chain = EvidenceChain(
            chain_id="CHAIN-12345678",
            records=(record1, record2),
            head_hash=record2.self_hash,
            length=2
        )
        assert validate_chain_integrity(chain) is True


# ============================================================================
# is_stop_condition_met TESTS
# ============================================================================

class TestIsStopConditionMetDenyByDefault:
    """Deny-by-default tests for is_stop_condition_met (HALT is default)."""

    def test_none_context_returns_true_halt(self) -> None:
        """None context → True (HALT)."""
        assert is_stop_condition_met(None, StopCondition.HUMAN_ABORT) is True

    def test_invalid_context_returns_true_halt(self) -> None:
        """Invalid context → True (HALT)."""
        invalid_context = _make_valid_context(session_id="INVALID")
        assert is_stop_condition_met(invalid_context, StopCondition.HUMAN_ABORT) is True

    def test_none_condition_returns_true_halt(self) -> None:
        """None condition → True (HALT)."""
        context = _make_valid_context()
        assert is_stop_condition_met(context, None) is True

    def test_non_stop_condition_type_returns_true_halt(self) -> None:
        """Non-StopCondition type → True (HALT)."""
        context = _make_valid_context()
        assert is_stop_condition_met(context, "HUMAN_ABORT") is True  # type: ignore


class TestIsStopConditionMetPositive:
    """Positive tests for is_stop_condition_met."""

    def test_valid_condition_returns_true_halt(self) -> None:
        """Valid stop condition is met → True (HALT)."""
        context = _make_valid_context()
        assert is_stop_condition_met(context, StopCondition.HUMAN_ABORT) is True

    def test_all_stop_conditions_return_true(self) -> None:
        """All valid stop conditions return True (HALT)."""
        context = _make_valid_context()
        for condition in StopCondition:
            assert is_stop_condition_met(context, condition) is True


# ============================================================================
# get_observation_state TESTS
# ============================================================================

class TestGetObservationStateDenyByDefault:
    """Deny-by-default tests for get_observation_state."""

    def test_none_chain_returns_none(self) -> None:
        """None chain → None."""
        context = _make_valid_context()
        assert get_observation_state(None, context) is None

    def test_invalid_chain_id_returns_none(self) -> None:
        """Invalid chain_id → None."""
        chain = EvidenceChain(
            chain_id="INVALID",
            records=(),
            head_hash="",
            length=0
        )
        context = _make_valid_context()
        assert get_observation_state(chain, context) is None

    def test_empty_chain_id_returns_none(self) -> None:
        """Empty chain_id → None."""
        chain = EvidenceChain(
            chain_id="",
            records=(),
            head_hash="",
            length=0
        )
        context = _make_valid_context()
        assert get_observation_state(chain, context) is None

    def test_none_context_returns_none(self) -> None:
        """None context → None."""
        chain = EvidenceChain(
            chain_id="CHAIN-12345678",
            records=(),
            head_hash="",
            length=0
        )
        assert get_observation_state(chain, None) is None

    def test_empty_chain_returns_none(self) -> None:
        """Empty chain → None."""
        chain = EvidenceChain(
            chain_id="CHAIN-12345678",
            records=(),
            head_hash="",
            length=0
        )
        context = _make_valid_context()
        assert get_observation_state(chain, context) is None

    def test_non_observation_point_in_last_record_returns_none(self) -> None:
        """Non-ObservationPoint in last record → None."""
        # We can't easily create this since the dataclass enforces it,
        # but we test the validation logic
        record = EvidenceRecord(
            record_id="EVIDENCE-12345678",
            observation_point="INVALID",  # type: ignore
            evidence_type=EvidenceType.STATE_TRANSITION,
            timestamp="2026-01-26T12:00:00Z",
            raw_data=b"test",
            prior_hash="",
            self_hash="abc123"
        )
        chain = EvidenceChain(
            chain_id="CHAIN-12345678",
            records=(record,),
            head_hash="abc123",
            length=1
        )
        context = _make_valid_context()
        assert get_observation_state(chain, context) is None


class TestGetObservationStatePositive:
    """Positive tests for get_observation_state."""

    def test_returns_last_record_observation_point(self) -> None:
        """Returns last record's observation_point."""
        record = _make_valid_record(observation_point=ObservationPoint.POST_EVALUATE)
        chain = EvidenceChain(
            chain_id="CHAIN-12345678",
            records=(record,),
            head_hash=record.self_hash,
            length=1
        )
        context = _make_valid_context()
        assert get_observation_state(chain, context) == ObservationPoint.POST_EVALUATE

    def test_returns_last_of_multiple_records(self) -> None:
        """Returns last record's observation_point from multi-record chain."""
        record1 = _make_valid_record(observation_point=ObservationPoint.PRE_DISPATCH)
        record2 = _make_valid_record(
            record_id="EVIDENCE-22222222",
            observation_point=ObservationPoint.HALT_ENTRY,
            prior_hash=record1.self_hash
        )
        chain = EvidenceChain(
            chain_id="CHAIN-12345678",
            records=(record1, record2),
            head_hash=record2.self_hash,
            length=2
        )
        context = _make_valid_context()
        assert get_observation_state(chain, context) == ObservationPoint.HALT_ENTRY
