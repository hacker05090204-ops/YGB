"""Phase-22 Context Tests."""
import pytest
from dataclasses import FrozenInstanceError
from impl_v1.phase22.phase22_types import PolicyScope, PolicyViolation, PolicyDecision
from impl_v1.phase22.phase22_context import (
    PolicyRule,
    PolicyEvaluationContext,
    PolicyEvaluationResult,
)


class TestPolicyRuleFrozen:
    def test_has_5_fields(self) -> None:
        from dataclasses import fields
        assert len(fields(PolicyRule)) == 5

    def test_can_be_created(self) -> None:
        rule = PolicyRule(
            policy_id="POLICY-12345678",
            scope=PolicyScope.EXECUTION,
            description="Test policy",
            enforced=True,
            severity=5
        )
        assert rule.policy_id == "POLICY-12345678"

    def test_is_immutable_policy_id(self) -> None:
        rule = PolicyRule(
            policy_id="POLICY-12345678",
            scope=PolicyScope.EXECUTION,
            description="Test",
            enforced=True,
            severity=5
        )
        with pytest.raises(FrozenInstanceError):
            rule.policy_id = "TAMPERED"  # type: ignore

    def test_is_immutable_enforced(self) -> None:
        rule = PolicyRule(
            policy_id="POLICY-12345678",
            scope=PolicyScope.EXECUTION,
            description="Test",
            enforced=True,
            severity=5
        )
        with pytest.raises(FrozenInstanceError):
            rule.enforced = False  # type: ignore


class TestPolicyEvaluationContextFrozen:
    def test_has_3_fields(self) -> None:
        from dataclasses import fields
        assert len(fields(PolicyEvaluationContext)) == 3

    def test_can_be_created(self) -> None:
        ctx = PolicyEvaluationContext(
            scope=PolicyScope.EXECUTION,
            requested_action="test_action",
            conditions=("cond1", "cond2")
        )
        assert ctx.scope == PolicyScope.EXECUTION

    def test_is_immutable_requested_action(self) -> None:
        ctx = PolicyEvaluationContext(
            scope=PolicyScope.EXECUTION,
            requested_action="test_action",
            conditions=()
        )
        with pytest.raises(FrozenInstanceError):
            ctx.requested_action = "TAMPERED"  # type: ignore


class TestPolicyEvaluationResultFrozen:
    def test_has_3_fields(self) -> None:
        from dataclasses import fields
        assert len(fields(PolicyEvaluationResult)) == 3

    def test_can_be_created(self) -> None:
        result = PolicyEvaluationResult(
            decision=PolicyDecision.ALLOW,
            violations=(),
            reasons=()
        )
        assert result.decision == PolicyDecision.ALLOW

    def test_is_immutable_decision(self) -> None:
        result = PolicyEvaluationResult(
            decision=PolicyDecision.ALLOW,
            violations=(),
            reasons=()
        )
        with pytest.raises(FrozenInstanceError):
            result.decision = PolicyDecision.DENY  # type: ignore

    def test_is_immutable_violations(self) -> None:
        result = PolicyEvaluationResult(
            decision=PolicyDecision.DENY,
            violations=(PolicyViolation.FORBIDDEN_ACTION,),
            reasons=()
        )
        with pytest.raises(FrozenInstanceError):
            result.violations = ()  # type: ignore
