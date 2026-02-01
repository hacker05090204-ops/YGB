"""
Phase-30 Types Tests.

Tests for CLOSED enums:
- ExecutorResponseType: 5 members
- ResponseDecision: 3 members

Tests enforce:
- Exact member counts (closedness)
- No additional members
- Correct member names/values
"""
import pytest

from impl_v1.phase30.phase30_types import (
    ExecutorResponseType,
    ResponseDecision,
)


class TestExecutorResponseTypeEnum:
    """Tests for ExecutorResponseType enum closedness."""

    def test_executor_response_type_has_exactly_5_members(self) -> None:
        """ExecutorResponseType must have exactly 5 members."""
        assert len(ExecutorResponseType) == 5

    def test_executor_response_type_has_success(self) -> None:
        """ExecutorResponseType must have SUCCESS."""
        assert ExecutorResponseType.SUCCESS is not None
        assert ExecutorResponseType.SUCCESS.name == "SUCCESS"

    def test_executor_response_type_has_failure(self) -> None:
        """ExecutorResponseType must have FAILURE."""
        assert ExecutorResponseType.FAILURE is not None
        assert ExecutorResponseType.FAILURE.name == "FAILURE"

    def test_executor_response_type_has_timeout(self) -> None:
        """ExecutorResponseType must have TIMEOUT."""
        assert ExecutorResponseType.TIMEOUT is not None
        assert ExecutorResponseType.TIMEOUT.name == "TIMEOUT"

    def test_executor_response_type_has_partial(self) -> None:
        """ExecutorResponseType must have PARTIAL."""
        assert ExecutorResponseType.PARTIAL is not None
        assert ExecutorResponseType.PARTIAL.name == "PARTIAL"

    def test_executor_response_type_has_malformed(self) -> None:
        """ExecutorResponseType must have MALFORMED."""
        assert ExecutorResponseType.MALFORMED is not None
        assert ExecutorResponseType.MALFORMED.name == "MALFORMED"

    def test_executor_response_type_all_members_listed(self) -> None:
        """All ExecutorResponseType members must be exactly as expected."""
        expected = {"SUCCESS", "FAILURE", "TIMEOUT", "PARTIAL", "MALFORMED"}
        actual = {m.name for m in ExecutorResponseType}
        assert actual == expected

    def test_executor_response_type_members_are_distinct(self) -> None:
        """All ExecutorResponseType members must have distinct values."""
        values = [m.value for m in ExecutorResponseType]
        assert len(values) == len(set(values))


class TestResponseDecisionEnum:
    """Tests for ResponseDecision enum closedness."""

    def test_response_decision_has_exactly_3_members(self) -> None:
        """ResponseDecision must have exactly 3 members."""
        assert len(ResponseDecision) == 3

    def test_response_decision_has_accept(self) -> None:
        """ResponseDecision must have ACCEPT."""
        assert ResponseDecision.ACCEPT is not None
        assert ResponseDecision.ACCEPT.name == "ACCEPT"

    def test_response_decision_has_reject(self) -> None:
        """ResponseDecision must have REJECT."""
        assert ResponseDecision.REJECT is not None
        assert ResponseDecision.REJECT.name == "REJECT"

    def test_response_decision_has_escalate(self) -> None:
        """ResponseDecision must have ESCALATE."""
        assert ResponseDecision.ESCALATE is not None
        assert ResponseDecision.ESCALATE.name == "ESCALATE"

    def test_response_decision_all_members_listed(self) -> None:
        """All ResponseDecision members must be exactly as expected."""
        expected = {"ACCEPT", "REJECT", "ESCALATE"}
        actual = {m.name for m in ResponseDecision}
        assert actual == expected

    def test_response_decision_members_are_distinct(self) -> None:
        """All ResponseDecision members must have distinct values."""
        values = [m.value for m in ResponseDecision]
        assert len(values) == len(set(values))
