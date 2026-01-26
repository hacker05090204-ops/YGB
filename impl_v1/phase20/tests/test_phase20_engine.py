"""Phase-20 Engine Tests."""
import pytest
from impl_v1.phase20.phase20_types import (
    SystemLayer,
    BoundaryViolation,
    BoundaryDecision,
)
from impl_v1.phase20.phase20_context import (
    SystemBoundary,
    BoundaryEvaluationContext,
    BoundaryEvaluationResult,
)
from impl_v1.phase20.phase20_engine import (
    validate_boundary_id,
    validate_system_boundary,
    validate_layer_transition,
    detect_boundary_violation,
    evaluate_system_boundary,
    get_boundary_decision,
)


def _make_valid_boundary(
    boundary_id: str = "BOUNDARY-12345678",
    layer: SystemLayer = SystemLayer.GOVERNANCE,
    description: str = "Test boundary",
    immutable: bool = False,
    enforced: bool = False
) -> SystemBoundary:
    return SystemBoundary(
        boundary_id=boundary_id,
        layer=layer,
        description=description,
        immutable=immutable,
        enforced=enforced
    )


def _make_root_boundary(
    boundary_id: str = "BOUNDARY-12345678",
    immutable: bool = True,
    enforced: bool = True
) -> SystemBoundary:
    return SystemBoundary(
        boundary_id=boundary_id,
        layer=SystemLayer.ROOT,
        description="Root boundary",
        immutable=immutable,
        enforced=enforced
    )


def _make_valid_context(
    current_layer: SystemLayer = SystemLayer.GOVERNANCE,
    requested_layer: SystemLayer = SystemLayer.EXECUTION,
    prior_decisions: tuple = ("decision1",)
) -> BoundaryEvaluationContext:
    return BoundaryEvaluationContext(
        current_layer=current_layer,
        requested_layer=requested_layer,
        prior_decisions=prior_decisions
    )


class TestValidateBoundaryIdDenyByDefault:
    def test_none_returns_false(self) -> None:
        assert validate_boundary_id(None) is False

    def test_non_string_returns_false(self) -> None:
        assert validate_boundary_id(123) is False  # type: ignore

    def test_empty_returns_false(self) -> None:
        assert validate_boundary_id("") is False

    def test_whitespace_returns_false(self) -> None:
        assert validate_boundary_id("   ") is False

    def test_invalid_format_returns_false(self) -> None:
        assert validate_boundary_id("INVALID-123") is False


class TestValidateBoundaryIdPositive:
    def test_valid_format_returns_true(self) -> None:
        assert validate_boundary_id("BOUNDARY-12345678") is True


class TestValidateSystemBoundaryDenyByDefault:
    def test_none_returns_false(self) -> None:
        is_valid, reasons = validate_system_boundary(None)
        assert is_valid is False
        assert "Missing system boundary" in reasons

    def test_invalid_boundary_id_returns_false(self) -> None:
        boundary = _make_valid_boundary(boundary_id="INVALID")
        is_valid, reasons = validate_system_boundary(boundary)
        assert is_valid is False
        assert "Invalid boundary ID" in reasons

    def test_invalid_layer_type_returns_false(self) -> None:
        boundary = SystemBoundary(
            boundary_id="BOUNDARY-12345678",
            layer="ROOT",  # type: ignore
            description="Test",
            immutable=True,
            enforced=True
        )
        is_valid, reasons = validate_system_boundary(boundary)
        assert is_valid is False
        assert "Invalid system layer" in reasons

    def test_empty_description_returns_false(self) -> None:
        boundary = _make_valid_boundary(description="")
        is_valid, reasons = validate_system_boundary(boundary)
        assert is_valid is False

    def test_whitespace_description_returns_false(self) -> None:
        boundary = _make_valid_boundary(description="   ")
        is_valid, reasons = validate_system_boundary(boundary)
        assert is_valid is False
        assert "Empty description" in reasons

    def test_root_not_immutable_returns_false(self) -> None:
        boundary = _make_root_boundary(immutable=False)
        is_valid, reasons = validate_system_boundary(boundary)
        assert is_valid is False
        assert "ROOT layer must be immutable" in reasons


class TestValidateSystemBoundaryPositive:
    def test_valid_boundary_returns_true(self) -> None:
        boundary = _make_valid_boundary()
        is_valid, reasons = validate_system_boundary(boundary)
        assert is_valid is True
        assert reasons == ()

    def test_valid_root_boundary_returns_true(self) -> None:
        boundary = _make_root_boundary()
        is_valid, reasons = validate_system_boundary(boundary)
        assert is_valid is True


class TestValidateLayerTransitionDenyByDefault:
    def test_none_current_returns_unknown_layer(self) -> None:
        is_valid, violation = validate_layer_transition(None, SystemLayer.GOVERNANCE)
        assert is_valid is False
        assert violation == BoundaryViolation.UNKNOWN_LAYER

    def test_none_requested_returns_unknown_layer(self) -> None:
        is_valid, violation = validate_layer_transition(SystemLayer.GOVERNANCE, None)
        assert is_valid is False
        assert violation == BoundaryViolation.UNKNOWN_LAYER

    def test_invalid_current_type_returns_unknown_layer(self) -> None:
        is_valid, violation = validate_layer_transition("GOVERNANCE", SystemLayer.EXECUTION)  # type: ignore
        assert is_valid is False
        assert violation == BoundaryViolation.UNKNOWN_LAYER

    def test_invalid_requested_type_returns_unknown_layer(self) -> None:
        is_valid, violation = validate_layer_transition(SystemLayer.GOVERNANCE, "EXECUTION")  # type: ignore
        assert is_valid is False
        assert violation == BoundaryViolation.UNKNOWN_LAYER

    def test_transition_to_root_returns_bypass_attempt(self) -> None:
        is_valid, violation = validate_layer_transition(SystemLayer.GOVERNANCE, SystemLayer.ROOT)
        assert is_valid is False
        assert violation == BoundaryViolation.BYPASS_ATTEMPT

    def test_skip_layers_returns_order_breach(self) -> None:
        # ROOT -> EXECUTION skips GOVERNANCE
        is_valid, violation = validate_layer_transition(SystemLayer.ROOT, SystemLayer.EXECUTION)
        assert is_valid is False
        assert violation == BoundaryViolation.ORDER_BREACH


class TestValidateLayerTransitionPositive:
    def test_adjacent_layers_returns_true(self) -> None:
        is_valid, _ = validate_layer_transition(SystemLayer.GOVERNANCE, SystemLayer.EXECUTION)
        assert is_valid is True

    def test_same_layer_returns_true(self) -> None:
        is_valid, _ = validate_layer_transition(SystemLayer.GOVERNANCE, SystemLayer.GOVERNANCE)
        assert is_valid is True

    def test_root_to_governance_returns_true(self) -> None:
        is_valid, _ = validate_layer_transition(SystemLayer.ROOT, SystemLayer.GOVERNANCE)
        assert is_valid is True

    def test_root_to_root_returns_true(self) -> None:
        is_valid, _ = validate_layer_transition(SystemLayer.ROOT, SystemLayer.ROOT)
        assert is_valid is True


class TestDetectBoundaryViolation:
    def test_none_context_returns_undefined_root(self) -> None:
        boundary = _make_valid_boundary()
        violations = detect_boundary_violation(None, boundary)
        assert BoundaryViolation.UNDEFINED_ROOT in violations

    def test_none_boundary_returns_undefined_root(self) -> None:
        ctx = _make_valid_context()
        violations = detect_boundary_violation(ctx, None)
        assert BoundaryViolation.UNDEFINED_ROOT in violations

    def test_invalid_transition_returns_violation(self) -> None:
        ctx = _make_valid_context(
            current_layer=SystemLayer.GOVERNANCE,
            requested_layer=SystemLayer.ROOT
        )
        boundary = _make_valid_boundary()
        violations = detect_boundary_violation(ctx, boundary)
        assert BoundaryViolation.BYPASS_ATTEMPT in violations

    def test_enforced_root_transition_returns_bypass(self) -> None:
        ctx = _make_valid_context(
            current_layer=SystemLayer.ROOT,
            requested_layer=SystemLayer.GOVERNANCE
        )
        boundary = _make_root_boundary(enforced=True)
        violations = detect_boundary_violation(ctx, boundary)
        assert BoundaryViolation.BYPASS_ATTEMPT in violations


class TestDetectBoundaryViolationPositive:
    def test_valid_transition_returns_empty(self) -> None:
        ctx = _make_valid_context(
            current_layer=SystemLayer.GOVERNANCE,
            requested_layer=SystemLayer.EXECUTION
        )
        boundary = _make_valid_boundary()
        violations = detect_boundary_violation(ctx, boundary)
        assert violations == ()


class TestEvaluateSystemBoundaryDenyByDefault:
    def test_none_context_returns_deny(self) -> None:
        boundary = _make_valid_boundary()
        result = evaluate_system_boundary(None, boundary)
        assert result.decision == BoundaryDecision.DENY
        assert BoundaryViolation.UNDEFINED_ROOT in result.violations

    def test_none_boundary_returns_deny(self) -> None:
        ctx = _make_valid_context()
        result = evaluate_system_boundary(ctx, None)
        assert result.decision == BoundaryDecision.DENY
        assert BoundaryViolation.UNDEFINED_ROOT in result.violations

    def test_invalid_boundary_returns_deny(self) -> None:
        ctx = _make_valid_context()
        boundary = _make_valid_boundary(boundary_id="INVALID")
        result = evaluate_system_boundary(ctx, boundary)
        assert result.decision == BoundaryDecision.DENY

    def test_single_violation_returns_deny(self) -> None:
        ctx = _make_valid_context(
            current_layer=SystemLayer.GOVERNANCE,
            requested_layer=SystemLayer.ROOT
        )
        boundary = _make_valid_boundary()
        result = evaluate_system_boundary(ctx, boundary)
        assert result.decision == BoundaryDecision.DENY

    def test_multiple_violations_returns_escalate(self) -> None:
        # Enforced ROOT + transition away = 2 violations (ORDER_BREACH + BYPASS_ATTEMPT)
        ctx = _make_valid_context(
            current_layer=SystemLayer.ROOT,
            requested_layer=SystemLayer.EXECUTION  # Skips GOVERNANCE
        )
        boundary = _make_root_boundary(enforced=True)
        result = evaluate_system_boundary(ctx, boundary)
        assert result.decision == BoundaryDecision.ESCALATE


class TestEvaluateSystemBoundaryPositive:
    def test_valid_returns_allow(self) -> None:
        ctx = _make_valid_context(
            current_layer=SystemLayer.GOVERNANCE,
            requested_layer=SystemLayer.EXECUTION
        )
        boundary = _make_valid_boundary()
        result = evaluate_system_boundary(ctx, boundary)
        assert result.decision == BoundaryDecision.ALLOW
        assert result.violations == ()


class TestGetBoundaryDecisionDenyByDefault:
    def test_none_returns_deny(self) -> None:
        assert get_boundary_decision(None) == BoundaryDecision.DENY

    def test_invalid_decision_type_returns_deny(self) -> None:
        result = BoundaryEvaluationResult(
            decision="ALLOW",  # type: ignore
            violations=(),
            reasons=()
        )
        assert get_boundary_decision(result) == BoundaryDecision.DENY


class TestGetBoundaryDecisionPositive:
    def test_returns_allow(self) -> None:
        result = BoundaryEvaluationResult(
            decision=BoundaryDecision.ALLOW,
            violations=(),
            reasons=()
        )
        assert get_boundary_decision(result) == BoundaryDecision.ALLOW

    def test_returns_deny(self) -> None:
        result = BoundaryEvaluationResult(
            decision=BoundaryDecision.DENY,
            violations=(BoundaryViolation.BYPASS_ATTEMPT,),
            reasons=()
        )
        assert get_boundary_decision(result) == BoundaryDecision.DENY

    def test_returns_escalate(self) -> None:
        result = BoundaryEvaluationResult(
            decision=BoundaryDecision.ESCALATE,
            violations=(),
            reasons=()
        )
        assert get_boundary_decision(result) == BoundaryDecision.ESCALATE
