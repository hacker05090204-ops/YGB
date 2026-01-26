"""Phase-22 Engine Tests."""
import pytest
from impl_v1.phase22.phase22_types import PolicyScope, PolicyViolation, PolicyDecision
from impl_v1.phase22.phase22_context import (
    PolicyRule,
    PolicyEvaluationContext,
    PolicyEvaluationResult,
)
from impl_v1.phase22.phase22_engine import (
    validate_policy_id,
    validate_policy_rule,
    evaluate_policy_scope,
    detect_policy_violation,
    evaluate_policy,
    get_policy_decision,
)


def _make_valid_rule(
    policy_id: str = "POLICY-12345678",
    scope: PolicyScope = PolicyScope.EXECUTION,
    description: str = "Test policy",
    enforced: bool = False,
    severity: int = 5
) -> PolicyRule:
    return PolicyRule(
        policy_id=policy_id,
        scope=scope,
        description=description,
        enforced=enforced,
        severity=severity
    )


def _make_valid_context(
    scope: PolicyScope = PolicyScope.EXECUTION,
    requested_action: str = "test_action",
    conditions: tuple = ("cond1",)
) -> PolicyEvaluationContext:
    return PolicyEvaluationContext(
        scope=scope,
        requested_action=requested_action,
        conditions=conditions
    )


class TestValidatePolicyIdDenyByDefault:
    def test_none_returns_false(self) -> None:
        assert validate_policy_id(None) is False

    def test_non_string_returns_false(self) -> None:
        assert validate_policy_id(123) is False  # type: ignore

    def test_empty_returns_false(self) -> None:
        assert validate_policy_id("") is False

    def test_whitespace_returns_false(self) -> None:
        assert validate_policy_id("   ") is False

    def test_invalid_format_returns_false(self) -> None:
        assert validate_policy_id("INVALID-123") is False


class TestValidatePolicyIdPositive:
    def test_valid_format_returns_true(self) -> None:
        assert validate_policy_id("POLICY-12345678") is True


class TestValidatePolicyRuleDenyByDefault:
    def test_none_returns_false(self) -> None:
        is_valid, reasons = validate_policy_rule(None)
        assert is_valid is False
        assert "Missing policy rule" in reasons

    def test_invalid_policy_id_returns_false(self) -> None:
        rule = _make_valid_rule(policy_id="INVALID")
        is_valid, reasons = validate_policy_rule(rule)
        assert is_valid is False
        assert "Invalid policy ID" in reasons

    def test_invalid_scope_type_returns_false(self) -> None:
        rule = PolicyRule(
            policy_id="POLICY-12345678",
            scope="EXECUTION",  # type: ignore
            description="Test",
            enforced=True,
            severity=5
        )
        is_valid, reasons = validate_policy_rule(rule)
        assert is_valid is False
        assert "Invalid policy scope" in reasons

    def test_empty_description_returns_false(self) -> None:
        rule = _make_valid_rule(description="")
        is_valid, reasons = validate_policy_rule(rule)
        assert is_valid is False

    def test_whitespace_description_returns_false(self) -> None:
        rule = _make_valid_rule(description="   ")
        is_valid, reasons = validate_policy_rule(rule)
        assert is_valid is False
        assert "Empty description" in reasons

    def test_invalid_severity_type_returns_false(self) -> None:
        rule = PolicyRule(
            policy_id="POLICY-12345678",
            scope=PolicyScope.EXECUTION,
            description="Test",
            enforced=True,
            severity="5"  # type: ignore
        )
        is_valid, reasons = validate_policy_rule(rule)
        assert is_valid is False
        assert "Invalid severity type" in reasons

    def test_severity_below_1_returns_false(self) -> None:
        rule = _make_valid_rule(severity=0)
        is_valid, reasons = validate_policy_rule(rule)
        assert is_valid is False
        assert "Severity must be 1-10" in reasons

    def test_severity_above_10_returns_false(self) -> None:
        rule = _make_valid_rule(severity=11)
        is_valid, reasons = validate_policy_rule(rule)
        assert is_valid is False


class TestValidatePolicyRulePositive:
    def test_valid_rule_returns_true(self) -> None:
        rule = _make_valid_rule()
        is_valid, reasons = validate_policy_rule(rule)
        assert is_valid is True
        assert reasons == ()


class TestEvaluatePolicyScopeDenyByDefault:
    def test_none_context_returns_false(self) -> None:
        rule = _make_valid_rule()
        assert evaluate_policy_scope(None, rule) is False

    def test_none_rule_returns_false(self) -> None:
        ctx = _make_valid_context()
        assert evaluate_policy_scope(ctx, None) is False

    def test_invalid_context_scope_returns_false(self) -> None:
        ctx = PolicyEvaluationContext(
            scope="EXECUTION",  # type: ignore
            requested_action="test",
            conditions=()
        )
        rule = _make_valid_rule()
        assert evaluate_policy_scope(ctx, rule) is False

    def test_invalid_rule_scope_returns_false(self) -> None:
        ctx = _make_valid_context()
        rule = PolicyRule(
            policy_id="POLICY-12345678",
            scope="EXECUTION",  # type: ignore
            description="Test",
            enforced=True,
            severity=5
        )
        assert evaluate_policy_scope(ctx, rule) is False

    def test_scope_mismatch_returns_false(self) -> None:
        ctx = _make_valid_context(scope=PolicyScope.EVIDENCE)
        rule = _make_valid_rule(scope=PolicyScope.EXECUTION)
        assert evaluate_policy_scope(ctx, rule) is False


class TestEvaluatePolicyScopePositive:
    def test_matching_scopes_returns_true(self) -> None:
        ctx = _make_valid_context(scope=PolicyScope.EXECUTION)
        rule = _make_valid_rule(scope=PolicyScope.EXECUTION)
        assert evaluate_policy_scope(ctx, rule) is True


class TestDetectPolicyViolation:
    def test_none_context_returns_unknown_policy(self) -> None:
        rule = _make_valid_rule()
        violations = detect_policy_violation(None, rule)
        assert PolicyViolation.UNKNOWN_POLICY in violations

    def test_none_rule_returns_unknown_policy(self) -> None:
        ctx = _make_valid_context()
        violations = detect_policy_violation(ctx, None)
        assert PolicyViolation.UNKNOWN_POLICY in violations

    def test_scope_mismatch_returns_out_of_scope(self) -> None:
        ctx = _make_valid_context(scope=PolicyScope.EVIDENCE)
        rule = _make_valid_rule(scope=PolicyScope.EXECUTION)
        violations = detect_policy_violation(ctx, rule)
        assert PolicyViolation.OUT_OF_SCOPE in violations

    def test_enforced_no_conditions_returns_condition_unmet(self) -> None:
        ctx = _make_valid_context(conditions=())
        rule = _make_valid_rule(enforced=True)
        violations = detect_policy_violation(ctx, rule)
        assert PolicyViolation.CONDITION_UNMET in violations

    def test_empty_action_returns_forbidden_action(self) -> None:
        ctx = _make_valid_context(requested_action="")
        rule = _make_valid_rule()
        violations = detect_policy_violation(ctx, rule)
        assert PolicyViolation.FORBIDDEN_ACTION in violations

    def test_whitespace_action_returns_forbidden_action(self) -> None:
        ctx = _make_valid_context(requested_action="   ")
        rule = _make_valid_rule()
        violations = detect_policy_violation(ctx, rule)
        assert PolicyViolation.FORBIDDEN_ACTION in violations


class TestDetectPolicyViolationPositive:
    def test_valid_context_and_rule_returns_empty(self) -> None:
        ctx = _make_valid_context()
        rule = _make_valid_rule()
        violations = detect_policy_violation(ctx, rule)
        assert violations == ()


class TestEvaluatePolicyDenyByDefault:
    def test_none_context_returns_deny(self) -> None:
        rule = _make_valid_rule()
        result = evaluate_policy(None, rule)
        assert result.decision == PolicyDecision.DENY
        assert PolicyViolation.UNKNOWN_POLICY in result.violations

    def test_none_rule_returns_deny(self) -> None:
        ctx = _make_valid_context()
        result = evaluate_policy(ctx, None)
        assert result.decision == PolicyDecision.DENY
        assert PolicyViolation.UNKNOWN_POLICY in result.violations

    def test_invalid_rule_returns_deny(self) -> None:
        ctx = _make_valid_context()
        rule = _make_valid_rule(policy_id="INVALID")
        result = evaluate_policy(ctx, rule)
        assert result.decision == PolicyDecision.DENY

    def test_single_violation_returns_deny(self) -> None:
        ctx = _make_valid_context(requested_action="")
        rule = _make_valid_rule()
        result = evaluate_policy(ctx, rule)
        assert result.decision == PolicyDecision.DENY

    def test_multiple_violations_returns_escalate(self) -> None:
        # Scope mismatch + forbidden action = 2 violations
        ctx = _make_valid_context(
            scope=PolicyScope.EVIDENCE,
            requested_action=""
        )
        rule = _make_valid_rule(scope=PolicyScope.EXECUTION)
        result = evaluate_policy(ctx, rule)
        assert result.decision == PolicyDecision.ESCALATE


class TestEvaluatePolicyPositive:
    def test_valid_returns_allow(self) -> None:
        ctx = _make_valid_context()
        rule = _make_valid_rule()
        result = evaluate_policy(ctx, rule)
        assert result.decision == PolicyDecision.ALLOW
        assert result.violations == ()


class TestGetPolicyDecisionDenyByDefault:
    def test_none_returns_deny(self) -> None:
        assert get_policy_decision(None) == PolicyDecision.DENY

    def test_invalid_decision_type_returns_deny(self) -> None:
        result = PolicyEvaluationResult(
            decision="ALLOW",  # type: ignore
            violations=(),
            reasons=()
        )
        assert get_policy_decision(result) == PolicyDecision.DENY


class TestGetPolicyDecisionPositive:
    def test_returns_allow(self) -> None:
        result = PolicyEvaluationResult(
            decision=PolicyDecision.ALLOW,
            violations=(),
            reasons=()
        )
        assert get_policy_decision(result) == PolicyDecision.ALLOW

    def test_returns_deny(self) -> None:
        result = PolicyEvaluationResult(
            decision=PolicyDecision.DENY,
            violations=(PolicyViolation.FORBIDDEN_ACTION,),
            reasons=()
        )
        assert get_policy_decision(result) == PolicyDecision.DENY

    def test_returns_escalate(self) -> None:
        result = PolicyEvaluationResult(
            decision=PolicyDecision.ESCALATE,
            violations=(),
            reasons=()
        )
        assert get_policy_decision(result) == PolicyDecision.ESCALATE
