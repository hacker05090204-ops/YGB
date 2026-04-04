"""
Phase-31 Types Tests.

Tests for CLOSED enums:
- ObservationPoint: 5 members
- EvidenceType: 5 members
- StopCondition: 10 members

Tests enforce:
- Exact member counts (closedness)
- No additional members
- Correct member names/values
"""
import pytest

from impl_v1.phase31.phase31_types import (
    ObservationPoint,
    EvidenceType,
    StopCondition,
)


class TestObservationPointEnum:
    """Tests for ObservationPoint enum closedness."""

    def test_observation_point_has_exactly_5_members(self) -> None:
        """ObservationPoint must have exactly 5 members."""
        assert len(ObservationPoint) == 5

    def test_observation_point_has_pre_dispatch(self) -> None:
        """ObservationPoint must have PRE_DISPATCH."""
        assert ObservationPoint.PRE_DISPATCH is not None
        assert ObservationPoint.PRE_DISPATCH.name == "PRE_DISPATCH"

    def test_observation_point_has_post_dispatch(self) -> None:
        """ObservationPoint must have POST_DISPATCH."""
        assert ObservationPoint.POST_DISPATCH is not None
        assert ObservationPoint.POST_DISPATCH.name == "POST_DISPATCH"

    def test_observation_point_has_pre_evaluate(self) -> None:
        """ObservationPoint must have PRE_EVALUATE."""
        assert ObservationPoint.PRE_EVALUATE is not None
        assert ObservationPoint.PRE_EVALUATE.name == "PRE_EVALUATE"

    def test_observation_point_has_post_evaluate(self) -> None:
        """ObservationPoint must have POST_EVALUATE."""
        assert ObservationPoint.POST_EVALUATE is not None
        assert ObservationPoint.POST_EVALUATE.name == "POST_EVALUATE"

    def test_observation_point_has_halt_entry(self) -> None:
        """ObservationPoint must have HALT_ENTRY."""
        assert ObservationPoint.HALT_ENTRY is not None
        assert ObservationPoint.HALT_ENTRY.name == "HALT_ENTRY"

    def test_observation_point_all_members_listed(self) -> None:
        """All ObservationPoint members must be exactly as expected."""
        expected = {"PRE_DISPATCH", "POST_DISPATCH", "PRE_EVALUATE", "POST_EVALUATE", "HALT_ENTRY"}
        actual = {m.name for m in ObservationPoint}
        assert actual == expected

    def test_observation_point_members_are_distinct(self) -> None:
        """All ObservationPoint members must have distinct values."""
        values = [m.value for m in ObservationPoint]
        assert len(values) == len(set(values))


class TestEvidenceTypeEnum:
    """Tests for EvidenceType enum closedness."""

    def test_evidence_type_has_exactly_5_members(self) -> None:
        """EvidenceType must have exactly 5 members."""
        assert len(EvidenceType) == 5

    def test_evidence_type_has_state_transition(self) -> None:
        """EvidenceType must have STATE_TRANSITION."""
        assert EvidenceType.STATE_TRANSITION is not None
        assert EvidenceType.STATE_TRANSITION.name == "STATE_TRANSITION"

    def test_evidence_type_has_executor_output(self) -> None:
        """EvidenceType must have EXECUTOR_OUTPUT."""
        assert EvidenceType.EXECUTOR_OUTPUT is not None
        assert EvidenceType.EXECUTOR_OUTPUT.name == "EXECUTOR_OUTPUT"

    def test_evidence_type_has_timestamp_event(self) -> None:
        """EvidenceType must have TIMESTAMP_EVENT."""
        assert EvidenceType.TIMESTAMP_EVENT is not None
        assert EvidenceType.TIMESTAMP_EVENT.name == "TIMESTAMP_EVENT"

    def test_evidence_type_has_resource_snapshot(self) -> None:
        """EvidenceType must have RESOURCE_SNAPSHOT."""
        assert EvidenceType.RESOURCE_SNAPSHOT is not None
        assert EvidenceType.RESOURCE_SNAPSHOT.name == "RESOURCE_SNAPSHOT"

    def test_evidence_type_has_stop_condition(self) -> None:
        """EvidenceType must have STOP_CONDITION."""
        assert EvidenceType.STOP_CONDITION is not None
        assert EvidenceType.STOP_CONDITION.name == "STOP_CONDITION"

    def test_evidence_type_all_members_listed(self) -> None:
        """All EvidenceType members must be exactly as expected."""
        expected = {"STATE_TRANSITION", "EXECUTOR_OUTPUT", "TIMESTAMP_EVENT", "RESOURCE_SNAPSHOT", "STOP_CONDITION"}
        actual = {m.name for m in EvidenceType}
        assert actual == expected

    def test_evidence_type_members_are_distinct(self) -> None:
        """All EvidenceType members must have distinct values."""
        values = [m.value for m in EvidenceType]
        assert len(values) == len(set(values))


class TestStopConditionEnum:
    """Tests for StopCondition enum closedness."""

    def test_stop_condition_has_exactly_10_members(self) -> None:
        """StopCondition must have exactly 10 members."""
        assert len(StopCondition) == 10

    def test_stop_condition_has_missing_authorization(self) -> None:
        """StopCondition must have MISSING_AUTHORIZATION."""
        assert StopCondition.MISSING_AUTHORIZATION is not None

    def test_stop_condition_has_executor_not_registered(self) -> None:
        """StopCondition must have EXECUTOR_NOT_REGISTERED."""
        assert StopCondition.EXECUTOR_NOT_REGISTERED is not None

    def test_stop_condition_has_envelope_hash_mismatch(self) -> None:
        """StopCondition must have ENVELOPE_HASH_MISMATCH."""
        assert StopCondition.ENVELOPE_HASH_MISMATCH is not None

    def test_stop_condition_has_context_uninitialized(self) -> None:
        """StopCondition must have CONTEXT_UNINITIALIZED."""
        assert StopCondition.CONTEXT_UNINITIALIZED is not None

    def test_stop_condition_has_evidence_chain_broken(self) -> None:
        """StopCondition must have EVIDENCE_CHAIN_BROKEN."""
        assert StopCondition.EVIDENCE_CHAIN_BROKEN is not None

    def test_stop_condition_has_resource_limit_exceeded(self) -> None:
        """StopCondition must have RESOURCE_LIMIT_EXCEEDED."""
        assert StopCondition.RESOURCE_LIMIT_EXCEEDED is not None

    def test_stop_condition_has_timestamp_invalid(self) -> None:
        """StopCondition must have TIMESTAMP_INVALID."""
        assert StopCondition.TIMESTAMP_INVALID is not None

    def test_stop_condition_has_prior_execution_pending(self) -> None:
        """StopCondition must have PRIOR_EXECUTION_PENDING."""
        assert StopCondition.PRIOR_EXECUTION_PENDING is not None

    def test_stop_condition_has_ambiguous_intent(self) -> None:
        """StopCondition must have AMBIGUOUS_INTENT."""
        assert StopCondition.AMBIGUOUS_INTENT is not None

    def test_stop_condition_has_human_abort(self) -> None:
        """StopCondition must have HUMAN_ABORT."""
        assert StopCondition.HUMAN_ABORT is not None

    def test_stop_condition_all_members_listed(self) -> None:
        """All StopCondition members must be exactly as expected."""
        expected = {
            "MISSING_AUTHORIZATION", "EXECUTOR_NOT_REGISTERED", "ENVELOPE_HASH_MISMATCH",
            "CONTEXT_UNINITIALIZED", "EVIDENCE_CHAIN_BROKEN", "RESOURCE_LIMIT_EXCEEDED",
            "TIMESTAMP_INVALID", "PRIOR_EXECUTION_PENDING", "AMBIGUOUS_INTENT", "HUMAN_ABORT"
        }
        actual = {m.name for m in StopCondition}
        assert actual == expected

    def test_stop_condition_members_are_distinct(self) -> None:
        """All StopCondition members must have distinct values."""
        values = [m.value for m in StopCondition]
        assert len(values) == len(set(values))
