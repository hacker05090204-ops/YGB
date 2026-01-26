"""Phase-24 Context Tests."""
import pytest
from dataclasses import FrozenInstanceError
from impl_v1.phase24.phase24_types import OrchestrationState, OrchestrationViolation
from impl_v1.phase24.phase24_context import OrchestrationContext, OrchestrationResult


class TestOrchestrationContextFrozen:
    def test_has_5_fields(self) -> None:
        from dataclasses import fields
        assert len(fields(OrchestrationContext)) == 5

    def test_can_be_created(self) -> None:
        ctx = OrchestrationContext(
            execution_id="EXECUTION-12345678",
            stages=("stage1", "stage2"),
            completed_stages=("stage1",),
            expected_order=("stage1", "stage2"),
            created_at="2026-01-26T12:00:00Z"
        )
        assert ctx.execution_id == "EXECUTION-12345678"

    def test_is_immutable_execution_id(self) -> None:
        ctx = OrchestrationContext(
            execution_id="EXECUTION-12345678",
            stages=("stage1",),
            completed_stages=(),
            expected_order=("stage1",),
            created_at="2026-01-26T12:00:00Z"
        )
        with pytest.raises(FrozenInstanceError):
            ctx.execution_id = "TAMPERED"  # type: ignore

    def test_is_immutable_stages(self) -> None:
        ctx = OrchestrationContext(
            execution_id="EXECUTION-12345678",
            stages=("stage1",),
            completed_stages=(),
            expected_order=("stage1",),
            created_at="2026-01-26T12:00:00Z"
        )
        with pytest.raises(FrozenInstanceError):
            ctx.stages = ()  # type: ignore


class TestOrchestrationResultFrozen:
    def test_has_3_fields(self) -> None:
        from dataclasses import fields
        assert len(fields(OrchestrationResult)) == 3

    def test_can_be_created(self) -> None:
        result = OrchestrationResult(
            state=OrchestrationState.VALIDATED,
            violations=(),
            evaluated_at="2026-01-26T12:00:00Z"
        )
        assert result.state == OrchestrationState.VALIDATED

    def test_is_immutable_state(self) -> None:
        result = OrchestrationResult(
            state=OrchestrationState.VALIDATED,
            violations=(),
            evaluated_at="2026-01-26T12:00:00Z"
        )
        with pytest.raises(FrozenInstanceError):
            result.state = OrchestrationState.BLOCKED  # type: ignore

    def test_is_immutable_violations(self) -> None:
        result = OrchestrationResult(
            state=OrchestrationState.BLOCKED,
            violations=(OrchestrationViolation.OUT_OF_ORDER,),
            evaluated_at="2026-01-26T12:00:00Z"
        )
        with pytest.raises(FrozenInstanceError):
            result.violations = ()  # type: ignore
