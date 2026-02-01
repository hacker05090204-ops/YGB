"""Phase-21 Engine Tests."""
import pytest
from impl_v1.phase21.phase21_types import (
    InvariantScope,
    InvariantViolation,
    InvariantDecision,
)
from impl_v1.phase21.phase21_context import (
    SystemInvariant,
    InvariantEvaluationContext,
    InvariantEvaluationResult,
)
from impl_v1.phase21.phase21_engine import (
    validate_invariant_id,
    validate_system_invariant,
    evaluate_invariant_scope,
    detect_invariant_violation,
    evaluate_invariants,
    get_invariant_decision,
)


def _make_valid_invariant(
    invariant_id: str = "INVARIANT-12345678",
    scope: InvariantScope = InvariantScope.GLOBAL,
    description: str = "Test invariant",
    enforced: bool = False,
    severity: int = 5
) -> SystemInvariant:
    return SystemInvariant(
        invariant_id=invariant_id,
        scope=scope,
        description=description,
        enforced=enforced,
        severity=severity
    )


def _make_valid_context(
    scope: InvariantScope = InvariantScope.EXECUTION,
    observed_state: tuple = ("state1",),
    prior_results: tuple = ("result1",)
) -> InvariantEvaluationContext:
    return InvariantEvaluationContext(
        scope=scope,
        observed_state=observed_state,
        prior_results=prior_results
    )


class TestValidateInvariantIdDenyByDefault:
    def test_none_returns_false(self) -> None:
        assert validate_invariant_id(None) is False

    def test_non_string_returns_false(self) -> None:
        assert validate_invariant_id(123) is False  # type: ignore

    def test_empty_returns_false(self) -> None:
        assert validate_invariant_id("") is False

    def test_whitespace_returns_false(self) -> None:
        assert validate_invariant_id("   ") is False

    def test_invalid_format_returns_false(self) -> None:
        assert validate_invariant_id("INVALID-123") is False


class TestValidateInvariantIdPositive:
    def test_valid_format_returns_true(self) -> None:
        assert validate_invariant_id("INVARIANT-12345678") is True


class TestValidateSystemInvariantDenyByDefault:
    def test_none_returns_false(self) -> None:
        is_valid, reasons = validate_system_invariant(None)
        assert is_valid is False
        assert "Missing system invariant" in reasons

    def test_invalid_invariant_id_returns_false(self) -> None:
        inv = _make_valid_invariant(invariant_id="INVALID")
        is_valid, reasons = validate_system_invariant(inv)
        assert is_valid is False
        assert "Invalid invariant ID" in reasons

    def test_invalid_scope_type_returns_false(self) -> None:
        inv = SystemInvariant(
            invariant_id="INVARIANT-12345678",
            scope="GLOBAL",  # type: ignore
            description="Test",
            enforced=True,
            severity=5
        )
        is_valid, reasons = validate_system_invariant(inv)
        assert is_valid is False
        assert "Invalid invariant scope" in reasons

    def test_empty_description_returns_false(self) -> None:
        inv = _make_valid_invariant(description="")
        is_valid, reasons = validate_system_invariant(inv)
        assert is_valid is False

    def test_whitespace_description_returns_false(self) -> None:
        inv = _make_valid_invariant(description="   ")
        is_valid, reasons = validate_system_invariant(inv)
        assert is_valid is False
        assert "Empty description" in reasons

    def test_invalid_severity_type_returns_false(self) -> None:
        inv = SystemInvariant(
            invariant_id="INVARIANT-12345678",
            scope=InvariantScope.GLOBAL,
            description="Test",
            enforced=True,
            severity="5"  # type: ignore
        )
        is_valid, reasons = validate_system_invariant(inv)
        assert is_valid is False
        assert "Invalid severity type" in reasons

    def test_severity_below_1_returns_false(self) -> None:
        inv = _make_valid_invariant(severity=0)
        is_valid, reasons = validate_system_invariant(inv)
        assert is_valid is False
        assert "Severity must be 1-10" in reasons

    def test_severity_above_10_returns_false(self) -> None:
        inv = _make_valid_invariant(severity=11)
        is_valid, reasons = validate_system_invariant(inv)
        assert is_valid is False


class TestValidateSystemInvariantPositive:
    def test_valid_invariant_returns_true(self) -> None:
        inv = _make_valid_invariant()
        is_valid, reasons = validate_system_invariant(inv)
        assert is_valid is True
        assert reasons == ()


class TestEvaluateInvariantScopeDenyByDefault:
    def test_none_context_returns_false(self) -> None:
        inv = _make_valid_invariant()
        assert evaluate_invariant_scope(None, inv) is False

    def test_none_invariant_returns_false(self) -> None:
        ctx = _make_valid_context()
        assert evaluate_invariant_scope(ctx, None) is False

    def test_invalid_context_scope_returns_false(self) -> None:
        ctx = InvariantEvaluationContext(
            scope="EXECUTION",  # type: ignore
            observed_state=(),
            prior_results=()
        )
        inv = _make_valid_invariant()
        assert evaluate_invariant_scope(ctx, inv) is False

    def test_invalid_invariant_scope_returns_false(self) -> None:
        ctx = _make_valid_context()
        inv = SystemInvariant(
            invariant_id="INVARIANT-12345678",
            scope="GLOBAL",  # type: ignore
            description="Test",
            enforced=True,
            severity=5
        )
        assert evaluate_invariant_scope(ctx, inv) is False

    def test_scope_mismatch_returns_false(self) -> None:
        ctx = _make_valid_context(scope=InvariantScope.EVIDENCE)
        inv = _make_valid_invariant(scope=InvariantScope.EXECUTION)
        assert evaluate_invariant_scope(ctx, inv) is False


class TestEvaluateInvariantScopePositive:
    def test_matching_scopes_returns_true(self) -> None:
        ctx = _make_valid_context(scope=InvariantScope.EXECUTION)
        inv = _make_valid_invariant(scope=InvariantScope.EXECUTION)
        assert evaluate_invariant_scope(ctx, inv) is True

    def test_global_scope_matches_all(self) -> None:
        ctx = _make_valid_context(scope=InvariantScope.EXECUTION)
        inv = _make_valid_invariant(scope=InvariantScope.GLOBAL)
        assert evaluate_invariant_scope(ctx, inv) is True


class TestDetectInvariantViolation:
    def test_none_context_returns_unknown_invariant(self) -> None:
        inv = _make_valid_invariant()
        violations = detect_invariant_violation(None, inv)
        assert InvariantViolation.UNKNOWN_INVARIANT in violations

    def test_none_invariant_returns_unknown_invariant(self) -> None:
        ctx = _make_valid_context()
        violations = detect_invariant_violation(ctx, None)
        assert InvariantViolation.UNKNOWN_INVARIANT in violations

    def test_scope_mismatch_returns_state_inconsistent(self) -> None:
        ctx = _make_valid_context(scope=InvariantScope.EVIDENCE)
        inv = _make_valid_invariant(scope=InvariantScope.EXECUTION)
        violations = detect_invariant_violation(ctx, inv)
        assert InvariantViolation.STATE_INCONSISTENT in violations

    def test_enforced_no_state_returns_missing_precondition(self) -> None:
        ctx = _make_valid_context(observed_state=())
        inv = _make_valid_invariant(enforced=True)
        violations = detect_invariant_violation(ctx, inv)
        assert InvariantViolation.MISSING_PRECONDITION in violations

    def test_enforced_no_prior_returns_broken_chain(self) -> None:
        ctx = _make_valid_context(prior_results=())
        inv = _make_valid_invariant(enforced=True)
        violations = detect_invariant_violation(ctx, inv)
        assert InvariantViolation.BROKEN_CHAIN in violations


class TestDetectInvariantViolationPositive:
    def test_valid_context_and_invariant_returns_empty(self) -> None:
        ctx = _make_valid_context()
        inv = _make_valid_invariant()
        violations = detect_invariant_violation(ctx, inv)
        assert violations == ()


class TestEvaluateInvariantsDenyByDefault:
    def test_none_context_returns_fail(self) -> None:
        inv = _make_valid_invariant()
        result = evaluate_invariants(None, inv)
        assert result.decision == InvariantDecision.FAIL
        assert InvariantViolation.UNKNOWN_INVARIANT in result.violations

    def test_none_invariant_returns_fail(self) -> None:
        ctx = _make_valid_context()
        result = evaluate_invariants(ctx, None)
        assert result.decision == InvariantDecision.FAIL
        assert InvariantViolation.UNKNOWN_INVARIANT in result.violations

    def test_invalid_invariant_returns_fail(self) -> None:
        ctx = _make_valid_context()
        inv = _make_valid_invariant(invariant_id="INVALID")
        result = evaluate_invariants(ctx, inv)
        assert result.decision == InvariantDecision.FAIL

    def test_single_violation_returns_fail(self) -> None:
        ctx = _make_valid_context(scope=InvariantScope.EVIDENCE)
        inv = _make_valid_invariant(scope=InvariantScope.EXECUTION)
        result = evaluate_invariants(ctx, inv)
        assert result.decision == InvariantDecision.FAIL

    def test_multiple_violations_returns_escalate(self) -> None:
        # Enforced + no state + no prior = 2 violations
        ctx = _make_valid_context(observed_state=(), prior_results=())
        inv = _make_valid_invariant(enforced=True)
        result = evaluate_invariants(ctx, inv)
        assert result.decision == InvariantDecision.ESCALATE


class TestEvaluateInvariantsPositive:
    def test_valid_returns_pass(self) -> None:
        ctx = _make_valid_context()
        inv = _make_valid_invariant()
        result = evaluate_invariants(ctx, inv)
        assert result.decision == InvariantDecision.PASS
        assert result.violations == ()


class TestGetInvariantDecisionDenyByDefault:
    def test_none_returns_fail(self) -> None:
        assert get_invariant_decision(None) == InvariantDecision.FAIL

    def test_invalid_decision_type_returns_fail(self) -> None:
        result = InvariantEvaluationResult(
            decision="PASS",  # type: ignore
            violations=(),
            reasons=()
        )
        assert get_invariant_decision(result) == InvariantDecision.FAIL


class TestGetInvariantDecisionPositive:
    def test_returns_pass(self) -> None:
        result = InvariantEvaluationResult(
            decision=InvariantDecision.PASS,
            violations=(),
            reasons=()
        )
        assert get_invariant_decision(result) == InvariantDecision.PASS

    def test_returns_fail(self) -> None:
        result = InvariantEvaluationResult(
            decision=InvariantDecision.FAIL,
            violations=(InvariantViolation.BROKEN_CHAIN,),
            reasons=()
        )
        assert get_invariant_decision(result) == InvariantDecision.FAIL

    def test_returns_escalate(self) -> None:
        result = InvariantEvaluationResult(
            decision=InvariantDecision.ESCALATE,
            violations=(),
            reasons=()
        )
        assert get_invariant_decision(result) == InvariantDecision.ESCALATE
