"""Phase-22 Types Tests."""
import pytest
from impl_v1.phase22.phase22_types import (
    PolicyScope,
    PolicyViolation,
    PolicyDecision,
)


class TestPolicyScopeEnum:
    def test_has_exactly_4_members(self) -> None:
        assert len(PolicyScope) == 4

    def test_has_execution(self) -> None:
        assert PolicyScope.EXECUTION.name == "EXECUTION"

    def test_has_evidence(self) -> None:
        assert PolicyScope.EVIDENCE.name == "EVIDENCE"

    def test_has_authorization(self) -> None:
        assert PolicyScope.AUTHORIZATION.name == "AUTHORIZATION"

    def test_has_human(self) -> None:
        assert PolicyScope.HUMAN.name == "HUMAN"

    def test_all_members_listed(self) -> None:
        expected = {"EXECUTION", "EVIDENCE", "AUTHORIZATION", "HUMAN"}
        actual = {m.name for m in PolicyScope}
        assert actual == expected

    def test_members_are_distinct(self) -> None:
        values = [m.value for m in PolicyScope]
        assert len(values) == len(set(values))


class TestPolicyViolationEnum:
    def test_has_exactly_4_members(self) -> None:
        assert len(PolicyViolation) == 4

    def test_has_forbidden_action(self) -> None:
        assert PolicyViolation.FORBIDDEN_ACTION.name == "FORBIDDEN_ACTION"

    def test_has_out_of_scope(self) -> None:
        assert PolicyViolation.OUT_OF_SCOPE.name == "OUT_OF_SCOPE"

    def test_has_condition_unmet(self) -> None:
        assert PolicyViolation.CONDITION_UNMET.name == "CONDITION_UNMET"

    def test_has_unknown_policy(self) -> None:
        assert PolicyViolation.UNKNOWN_POLICY.name == "UNKNOWN_POLICY"

    def test_all_members_listed(self) -> None:
        expected = {"FORBIDDEN_ACTION", "OUT_OF_SCOPE", "CONDITION_UNMET", "UNKNOWN_POLICY"}
        actual = {m.name for m in PolicyViolation}
        assert actual == expected

    def test_members_are_distinct(self) -> None:
        values = [m.value for m in PolicyViolation]
        assert len(values) == len(set(values))


class TestPolicyDecisionEnum:
    def test_has_exactly_3_members(self) -> None:
        assert len(PolicyDecision) == 3

    def test_has_allow(self) -> None:
        assert PolicyDecision.ALLOW.name == "ALLOW"

    def test_has_deny(self) -> None:
        assert PolicyDecision.DENY.name == "DENY"

    def test_has_escalate(self) -> None:
        assert PolicyDecision.ESCALATE.name == "ESCALATE"

    def test_all_members_listed(self) -> None:
        expected = {"ALLOW", "DENY", "ESCALATE"}
        actual = {m.name for m in PolicyDecision}
        assert actual == expected

    def test_members_are_distinct(self) -> None:
        values = [m.value for m in PolicyDecision]
        assert len(values) == len(set(values))
