"""Phase-21 Context Tests."""
import pytest
from dataclasses import FrozenInstanceError
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


class TestSystemInvariantFrozen:
    def test_has_5_fields(self) -> None:
        from dataclasses import fields
        assert len(fields(SystemInvariant)) == 5

    def test_can_be_created(self) -> None:
        inv = SystemInvariant(
            invariant_id="INVARIANT-12345678",
            scope=InvariantScope.GLOBAL,
            description="Test invariant",
            enforced=True,
            severity=5
        )
        assert inv.invariant_id == "INVARIANT-12345678"

    def test_is_immutable_invariant_id(self) -> None:
        inv = SystemInvariant(
            invariant_id="INVARIANT-12345678",
            scope=InvariantScope.GLOBAL,
            description="Test",
            enforced=True,
            severity=5
        )
        with pytest.raises(FrozenInstanceError):
            inv.invariant_id = "TAMPERED"  # type: ignore

    def test_is_immutable_enforced(self) -> None:
        inv = SystemInvariant(
            invariant_id="INVARIANT-12345678",
            scope=InvariantScope.GLOBAL,
            description="Test",
            enforced=True,
            severity=5
        )
        with pytest.raises(FrozenInstanceError):
            inv.enforced = False  # type: ignore


class TestInvariantEvaluationContextFrozen:
    def test_has_3_fields(self) -> None:
        from dataclasses import fields
        assert len(fields(InvariantEvaluationContext)) == 3

    def test_can_be_created(self) -> None:
        ctx = InvariantEvaluationContext(
            scope=InvariantScope.EXECUTION,
            observed_state=("state1",),
            prior_results=("result1",)
        )
        assert ctx.scope == InvariantScope.EXECUTION

    def test_is_immutable_observed_state(self) -> None:
        ctx = InvariantEvaluationContext(
            scope=InvariantScope.EXECUTION,
            observed_state=("state1",),
            prior_results=()
        )
        with pytest.raises(FrozenInstanceError):
            ctx.observed_state = ()  # type: ignore


class TestInvariantEvaluationResultFrozen:
    def test_has_3_fields(self) -> None:
        from dataclasses import fields
        assert len(fields(InvariantEvaluationResult)) == 3

    def test_can_be_created(self) -> None:
        result = InvariantEvaluationResult(
            decision=InvariantDecision.PASS,
            violations=(),
            reasons=()
        )
        assert result.decision == InvariantDecision.PASS

    def test_is_immutable_decision(self) -> None:
        result = InvariantEvaluationResult(
            decision=InvariantDecision.PASS,
            violations=(),
            reasons=()
        )
        with pytest.raises(FrozenInstanceError):
            result.decision = InvariantDecision.FAIL  # type: ignore

    def test_is_immutable_violations(self) -> None:
        result = InvariantEvaluationResult(
            decision=InvariantDecision.FAIL,
            violations=(InvariantViolation.BROKEN_CHAIN,),
            reasons=()
        )
        with pytest.raises(FrozenInstanceError):
            result.violations = ()  # type: ignore
