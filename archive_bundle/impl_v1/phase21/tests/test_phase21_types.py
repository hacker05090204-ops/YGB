"""Phase-21 Types Tests."""
import pytest
from impl_v1.phase21.phase21_types import (
    InvariantScope,
    InvariantViolation,
    InvariantDecision,
)


class TestInvariantScopeEnum:
    def test_has_exactly_5_members(self) -> None:
        assert len(InvariantScope) == 5

    def test_has_global(self) -> None:
        assert InvariantScope.GLOBAL.name == "GLOBAL"

    def test_has_execution(self) -> None:
        assert InvariantScope.EXECUTION.name == "EXECUTION"

    def test_has_evidence(self) -> None:
        assert InvariantScope.EVIDENCE.name == "EVIDENCE"

    def test_has_authorization(self) -> None:
        assert InvariantScope.AUTHORIZATION.name == "AUTHORIZATION"

    def test_has_human(self) -> None:
        assert InvariantScope.HUMAN.name == "HUMAN"

    def test_all_members_listed(self) -> None:
        expected = {"GLOBAL", "EXECUTION", "EVIDENCE", "AUTHORIZATION", "HUMAN"}
        actual = {m.name for m in InvariantScope}
        assert actual == expected

    def test_members_are_distinct(self) -> None:
        values = [m.value for m in InvariantScope]
        assert len(values) == len(set(values))


class TestInvariantViolationEnum:
    def test_has_exactly_4_members(self) -> None:
        assert len(InvariantViolation) == 4

    def test_has_broken_chain(self) -> None:
        assert InvariantViolation.BROKEN_CHAIN.name == "BROKEN_CHAIN"

    def test_has_state_inconsistent(self) -> None:
        assert InvariantViolation.STATE_INCONSISTENT.name == "STATE_INCONSISTENT"

    def test_has_missing_precondition(self) -> None:
        assert InvariantViolation.MISSING_PRECONDITION.name == "MISSING_PRECONDITION"

    def test_has_unknown_invariant(self) -> None:
        assert InvariantViolation.UNKNOWN_INVARIANT.name == "UNKNOWN_INVARIANT"

    def test_all_members_listed(self) -> None:
        expected = {"BROKEN_CHAIN", "STATE_INCONSISTENT", "MISSING_PRECONDITION", "UNKNOWN_INVARIANT"}
        actual = {m.name for m in InvariantViolation}
        assert actual == expected

    def test_members_are_distinct(self) -> None:
        values = [m.value for m in InvariantViolation]
        assert len(values) == len(set(values))


class TestInvariantDecisionEnum:
    def test_has_exactly_3_members(self) -> None:
        assert len(InvariantDecision) == 3

    def test_has_pass(self) -> None:
        assert InvariantDecision.PASS.name == "PASS"

    def test_has_fail(self) -> None:
        assert InvariantDecision.FAIL.name == "FAIL"

    def test_has_escalate(self) -> None:
        assert InvariantDecision.ESCALATE.name == "ESCALATE"

    def test_all_members_listed(self) -> None:
        expected = {"PASS", "FAIL", "ESCALATE"}
        actual = {m.name for m in InvariantDecision}
        assert actual == expected

    def test_members_are_distinct(self) -> None:
        values = [m.value for m in InvariantDecision]
        assert len(values) == len(set(values))
