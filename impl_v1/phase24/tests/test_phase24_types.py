"""Phase-24 Types Tests."""
import pytest
from impl_v1.phase24.phase24_types import OrchestrationState, OrchestrationViolation


class TestOrchestrationStateEnum:
    def test_has_exactly_4_members(self) -> None:
        assert len(OrchestrationState) == 4

    def test_has_initialized(self) -> None:
        assert OrchestrationState.INITIALIZED.name == "INITIALIZED"

    def test_has_sequenced(self) -> None:
        assert OrchestrationState.SEQUENCED.name == "SEQUENCED"

    def test_has_validated(self) -> None:
        assert OrchestrationState.VALIDATED.name == "VALIDATED"

    def test_has_blocked(self) -> None:
        assert OrchestrationState.BLOCKED.name == "BLOCKED"

    def test_all_members_listed(self) -> None:
        expected = {"INITIALIZED", "SEQUENCED", "VALIDATED", "BLOCKED"}
        actual = {m.name for m in OrchestrationState}
        assert actual == expected

    def test_members_are_distinct(self) -> None:
        values = [m.value for m in OrchestrationState]
        assert len(values) == len(set(values))


class TestOrchestrationViolationEnum:
    def test_has_exactly_4_members(self) -> None:
        assert len(OrchestrationViolation) == 4

    def test_has_out_of_order(self) -> None:
        assert OrchestrationViolation.OUT_OF_ORDER.name == "OUT_OF_ORDER"

    def test_has_missing_dependency(self) -> None:
        assert OrchestrationViolation.MISSING_DEPENDENCY.name == "MISSING_DEPENDENCY"

    def test_has_duplicate_step(self) -> None:
        assert OrchestrationViolation.DUPLICATE_STEP.name == "DUPLICATE_STEP"

    def test_has_unknown_stage(self) -> None:
        assert OrchestrationViolation.UNKNOWN_STAGE.name == "UNKNOWN_STAGE"

    def test_all_members_listed(self) -> None:
        expected = {"OUT_OF_ORDER", "MISSING_DEPENDENCY", "DUPLICATE_STEP", "UNKNOWN_STAGE"}
        actual = {m.name for m in OrchestrationViolation}
        assert actual == expected

    def test_members_are_distinct(self) -> None:
        values = [m.value for m in OrchestrationViolation]
        assert len(values) == len(set(values))
