"""Phase-35 Context Tests."""
import pytest
from dataclasses import FrozenInstanceError
from impl_v1.phase35.phase35_types import (
    ExecutorClass,
    CapabilityType,
    InterfaceDecision,
)
from impl_v1.phase35.phase35_context import (
    ExecutorInterface,
    ExecutionIntent,
    InterfaceEvaluationResult,
)


class TestExecutorInterfaceFrozen:
    def test_has_4_fields(self) -> None:
        from dataclasses import fields
        assert len(fields(ExecutorInterface)) == 4

    def test_can_be_created(self) -> None:
        iface = ExecutorInterface(
            executor_id="EXECUTOR-12345678",
            executor_class=ExecutorClass.NATIVE,
            declared_capabilities=(CapabilityType.COMPUTE,),
            version="1.0.0"
        )
        assert iface.executor_id == "EXECUTOR-12345678"

    def test_is_immutable_executor_id(self) -> None:
        iface = ExecutorInterface(
            executor_id="EXECUTOR-12345678",
            executor_class=ExecutorClass.NATIVE,
            declared_capabilities=(),
            version="1.0.0"
        )
        with pytest.raises(FrozenInstanceError):
            iface.executor_id = "TAMPERED"  # type: ignore

    def test_is_immutable_version(self) -> None:
        iface = ExecutorInterface(
            executor_id="EXECUTOR-12345678",
            executor_class=ExecutorClass.NATIVE,
            declared_capabilities=(),
            version="1.0.0"
        )
        with pytest.raises(FrozenInstanceError):
            iface.version = "2.0.0"  # type: ignore


class TestExecutionIntentFrozen:
    def test_has_3_fields(self) -> None:
        from dataclasses import fields
        assert len(fields(ExecutionIntent)) == 3

    def test_can_be_created(self) -> None:
        intent = ExecutionIntent(
            intent_id="INTENT-12345678",
            description="Test intent",
            required_capabilities=(CapabilityType.COMPUTE,)
        )
        assert intent.intent_id == "INTENT-12345678"

    def test_is_immutable_description(self) -> None:
        intent = ExecutionIntent(
            intent_id="INTENT-12345678",
            description="Test",
            required_capabilities=()
        )
        with pytest.raises(FrozenInstanceError):
            intent.description = "TAMPERED"  # type: ignore


class TestInterfaceEvaluationResultFrozen:
    def test_has_3_fields(self) -> None:
        from dataclasses import fields
        assert len(fields(InterfaceEvaluationResult)) == 3

    def test_can_be_created(self) -> None:
        result = InterfaceEvaluationResult(
            decision=InterfaceDecision.ALLOW,
            missing_capabilities=(),
            reasons=()
        )
        assert result.decision == InterfaceDecision.ALLOW

    def test_is_immutable_decision(self) -> None:
        result = InterfaceEvaluationResult(
            decision=InterfaceDecision.ALLOW,
            missing_capabilities=(),
            reasons=()
        )
        with pytest.raises(FrozenInstanceError):
            result.decision = InterfaceDecision.DENY  # type: ignore

    def test_is_immutable_reasons(self) -> None:
        result = InterfaceEvaluationResult(
            decision=InterfaceDecision.DENY,
            missing_capabilities=(),
            reasons=("reason",)
        )
        with pytest.raises(FrozenInstanceError):
            result.reasons = ()  # type: ignore
