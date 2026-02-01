"""Phase-20 Context Tests."""
import pytest
from dataclasses import FrozenInstanceError
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


class TestSystemBoundaryFrozen:
    def test_has_5_fields(self) -> None:
        from dataclasses import fields
        assert len(fields(SystemBoundary)) == 5

    def test_can_be_created(self) -> None:
        boundary = SystemBoundary(
            boundary_id="BOUNDARY-12345678",
            layer=SystemLayer.ROOT,
            description="Root boundary",
            immutable=True,
            enforced=True
        )
        assert boundary.boundary_id == "BOUNDARY-12345678"

    def test_is_immutable_boundary_id(self) -> None:
        boundary = SystemBoundary(
            boundary_id="BOUNDARY-12345678",
            layer=SystemLayer.ROOT,
            description="Root",
            immutable=True,
            enforced=True
        )
        with pytest.raises(FrozenInstanceError):
            boundary.boundary_id = "TAMPERED"  # type: ignore

    def test_is_immutable_immutable_field(self) -> None:
        boundary = SystemBoundary(
            boundary_id="BOUNDARY-12345678",
            layer=SystemLayer.ROOT,
            description="Root",
            immutable=True,
            enforced=True
        )
        with pytest.raises(FrozenInstanceError):
            boundary.immutable = False  # type: ignore


class TestBoundaryEvaluationContextFrozen:
    def test_has_3_fields(self) -> None:
        from dataclasses import fields
        assert len(fields(BoundaryEvaluationContext)) == 3

    def test_can_be_created(self) -> None:
        ctx = BoundaryEvaluationContext(
            current_layer=SystemLayer.GOVERNANCE,
            requested_layer=SystemLayer.EXECUTION,
            prior_decisions=("decision1",)
        )
        assert ctx.current_layer == SystemLayer.GOVERNANCE

    def test_is_immutable_requested_layer(self) -> None:
        ctx = BoundaryEvaluationContext(
            current_layer=SystemLayer.GOVERNANCE,
            requested_layer=SystemLayer.EXECUTION,
            prior_decisions=()
        )
        with pytest.raises(FrozenInstanceError):
            ctx.requested_layer = SystemLayer.ROOT  # type: ignore


class TestBoundaryEvaluationResultFrozen:
    def test_has_3_fields(self) -> None:
        from dataclasses import fields
        assert len(fields(BoundaryEvaluationResult)) == 3

    def test_can_be_created(self) -> None:
        result = BoundaryEvaluationResult(
            decision=BoundaryDecision.ALLOW,
            violations=(),
            reasons=()
        )
        assert result.decision == BoundaryDecision.ALLOW

    def test_is_immutable_decision(self) -> None:
        result = BoundaryEvaluationResult(
            decision=BoundaryDecision.ALLOW,
            violations=(),
            reasons=()
        )
        with pytest.raises(FrozenInstanceError):
            result.decision = BoundaryDecision.DENY  # type: ignore

    def test_is_immutable_violations(self) -> None:
        result = BoundaryEvaluationResult(
            decision=BoundaryDecision.DENY,
            violations=(BoundaryViolation.BYPASS_ATTEMPT,),
            reasons=()
        )
        with pytest.raises(FrozenInstanceError):
            result.violations = ()  # type: ignore
