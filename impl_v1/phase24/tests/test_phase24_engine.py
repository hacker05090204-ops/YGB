"""Phase-24 Engine Tests."""
import pytest
from impl_v1.phase24.phase24_types import OrchestrationState, OrchestrationViolation
from impl_v1.phase24.phase24_context import OrchestrationContext, OrchestrationResult
from impl_v1.phase24.phase24_engine import (
    validate_execution_id,
    validate_stage_order,
    validate_dependencies,
    evaluate_orchestration,
    is_orchestration_valid,
)


def _make_valid_context(
    execution_id: str = "EXECUTION-12345678",
    stages: tuple = ("stage1", "stage2"),
    completed_stages: tuple = ("stage1",),
    expected_order: tuple = ("stage1", "stage2", "stage3"),
    created_at: str = "2026-01-26T12:00:00Z"
) -> OrchestrationContext:
    return OrchestrationContext(
        execution_id=execution_id,
        stages=stages,
        completed_stages=completed_stages,
        expected_order=expected_order,
        created_at=created_at
    )


class TestValidateExecutionIdDenyByDefault:
    def test_none_returns_false(self) -> None:
        assert validate_execution_id(None) is False

    def test_non_string_returns_false(self) -> None:
        assert validate_execution_id(123) is False  # type: ignore

    def test_empty_returns_false(self) -> None:
        assert validate_execution_id("") is False

    def test_whitespace_returns_false(self) -> None:
        assert validate_execution_id("   ") is False

    def test_invalid_format_returns_false(self) -> None:
        assert validate_execution_id("INVALID-123") is False


class TestValidateExecutionIdPositive:
    def test_valid_format_returns_true(self) -> None:
        assert validate_execution_id("EXECUTION-12345678") is True


class TestValidateStageOrderDenyByDefault:
    def test_none_stages_returns_out_of_order(self) -> None:
        is_valid, violations = validate_stage_order(None, ("a", "b"))
        assert is_valid is False
        assert OrchestrationViolation.OUT_OF_ORDER in violations

    def test_none_expected_returns_out_of_order(self) -> None:
        is_valid, violations = validate_stage_order(("a",), None)
        assert is_valid is False
        assert OrchestrationViolation.OUT_OF_ORDER in violations

    def test_non_tuple_stages_returns_out_of_order(self) -> None:
        is_valid, violations = validate_stage_order(["a"], ("a",))  # type: ignore
        assert is_valid is False
        assert OrchestrationViolation.OUT_OF_ORDER in violations

    def test_non_tuple_expected_returns_out_of_order(self) -> None:
        is_valid, violations = validate_stage_order(("a",), ["a"])  # type: ignore
        assert is_valid is False
        assert OrchestrationViolation.OUT_OF_ORDER in violations

    def test_unknown_stage_returns_unknown_stage(self) -> None:
        is_valid, violations = validate_stage_order(("unknown",), ("a", "b"))
        assert is_valid is False
        assert OrchestrationViolation.UNKNOWN_STAGE in violations

    def test_duplicate_stage_returns_duplicate_step(self) -> None:
        is_valid, violations = validate_stage_order(("a", "a"), ("a", "b"))
        assert is_valid is False
        assert OrchestrationViolation.DUPLICATE_STEP in violations

    def test_out_of_order_returns_out_of_order(self) -> None:
        is_valid, violations = validate_stage_order(("b", "a"), ("a", "b", "c"))
        assert is_valid is False
        assert OrchestrationViolation.OUT_OF_ORDER in violations


class TestValidateStageOrderPositive:
    def test_valid_order_returns_true(self) -> None:
        is_valid, violations = validate_stage_order(("a", "b"), ("a", "b", "c"))
        assert is_valid is True
        assert violations == ()

    def test_empty_stages_returns_true(self) -> None:
        is_valid, violations = validate_stage_order((), ("a", "b"))
        assert is_valid is True

    def test_subset_in_order_returns_true(self) -> None:
        is_valid, violations = validate_stage_order(("a", "c"), ("a", "b", "c"))
        assert is_valid is True


class TestValidateDependenciesDenyByDefault:
    def test_none_completed_returns_missing_dependency(self) -> None:
        is_valid, violations = validate_dependencies(None, ("a",))
        assert is_valid is False
        assert OrchestrationViolation.MISSING_DEPENDENCY in violations

    def test_non_tuple_completed_returns_missing_dependency(self) -> None:
        is_valid, violations = validate_dependencies(["a"], ("a",))  # type: ignore
        assert is_valid is False
        assert OrchestrationViolation.MISSING_DEPENDENCY in violations

    def test_missing_required_returns_missing_dependency(self) -> None:
        is_valid, violations = validate_dependencies(("a",), ("b",))
        assert is_valid is False
        assert OrchestrationViolation.MISSING_DEPENDENCY in violations


class TestValidateDependenciesPositive:
    def test_none_required_returns_true(self) -> None:
        is_valid, violations = validate_dependencies(("a",), None)
        assert is_valid is True

    def test_non_tuple_required_returns_true(self) -> None:
        is_valid, violations = validate_dependencies(("a",), ["a"])  # type: ignore
        assert is_valid is True

    def test_all_required_completed_returns_true(self) -> None:
        is_valid, violations = validate_dependencies(("a", "b"), ("a", "b"))
        assert is_valid is True


class TestEvaluateOrchestrationDenyByDefault:
    def test_none_returns_blocked(self) -> None:
        result = evaluate_orchestration(None)
        assert result.state == OrchestrationState.BLOCKED

    def test_invalid_execution_id_returns_blocked(self) -> None:
        ctx = _make_valid_context(execution_id="INVALID")
        result = evaluate_orchestration(ctx)
        assert result.state == OrchestrationState.BLOCKED

    def test_empty_created_at_returns_blocked(self) -> None:
        ctx = _make_valid_context(created_at="")
        result = evaluate_orchestration(ctx)
        assert result.state == OrchestrationState.BLOCKED

    def test_whitespace_created_at_returns_blocked(self) -> None:
        ctx = _make_valid_context(created_at="   ")
        result = evaluate_orchestration(ctx)
        assert result.state == OrchestrationState.BLOCKED

    def test_missing_dependency_returns_blocked(self) -> None:
        ctx = _make_valid_context(completed_stages=())
        result = evaluate_orchestration(ctx, required_stages=("stage1",))
        assert result.state == OrchestrationState.BLOCKED
        assert OrchestrationViolation.MISSING_DEPENDENCY in result.violations

    def test_invalid_execution_id_with_out_of_order_stages_deduplicates(self) -> None:
        # This tests violation deduplication - OUT_OF_ORDER from execution_id
        # should prevent duplicate when stage order also produces OUT_OF_ORDER
        ctx = _make_valid_context(
            execution_id="INVALID",
            stages=("stage2", "stage1"),  # reverse order
            expected_order=("stage1", "stage2", "stage3")
        )
        result = evaluate_orchestration(ctx)
        assert result.state == OrchestrationState.BLOCKED
        # Should deduplicate OUT_OF_ORDER
        out_of_order_count = sum(
            1 for v in result.violations if v == OrchestrationViolation.OUT_OF_ORDER
        )
        assert out_of_order_count == 1

    def test_stage_order_violation_returns_blocked(self) -> None:
        # Valid execution_id and created_at, but invalid stage order
        ctx = _make_valid_context(
            stages=("stage2", "stage1"),  # reverse order
            expected_order=("stage1", "stage2", "stage3")
        )
        result = evaluate_orchestration(ctx)
        assert result.state == OrchestrationState.BLOCKED
        assert OrchestrationViolation.OUT_OF_ORDER in result.violations


class TestEvaluateOrchestrationPositive:
    def test_valid_context_returns_validated(self) -> None:
        ctx = _make_valid_context()
        result = evaluate_orchestration(ctx, timestamp="2026-01-26T12:00:00Z")
        assert result.state == OrchestrationState.VALIDATED
        assert result.violations == ()


class TestIsOrchestrationValidDenyByDefault:
    def test_none_returns_false(self) -> None:
        assert is_orchestration_valid(None) is False

    def test_invalid_state_type_returns_false(self) -> None:
        result = OrchestrationResult(
            state="VALIDATED",  # type: ignore
            violations=(),
            evaluated_at=""
        )
        assert is_orchestration_valid(result) is False

    def test_blocked_returns_false(self) -> None:
        result = OrchestrationResult(
            state=OrchestrationState.BLOCKED,
            violations=(OrchestrationViolation.OUT_OF_ORDER,),
            evaluated_at=""
        )
        assert is_orchestration_valid(result) is False

    def test_initialized_returns_false(self) -> None:
        result = OrchestrationResult(
            state=OrchestrationState.INITIALIZED,
            violations=(),
            evaluated_at=""
        )
        assert is_orchestration_valid(result) is False

    def test_sequenced_returns_false(self) -> None:
        result = OrchestrationResult(
            state=OrchestrationState.SEQUENCED,
            violations=(),
            evaluated_at=""
        )
        assert is_orchestration_valid(result) is False


class TestIsOrchestrationValidPositive:
    def test_validated_returns_true(self) -> None:
        result = OrchestrationResult(
            state=OrchestrationState.VALIDATED,
            violations=(),
            evaluated_at=""
        )
        assert is_orchestration_valid(result) is True
