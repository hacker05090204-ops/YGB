"""Phase-35 Engine Tests."""
import pytest
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
from impl_v1.phase35.phase35_engine import (
    validate_executor_id,
    validate_executor_interface,
    validate_execution_intent,
    validate_capabilities,
    evaluate_execution_interface,
    get_interface_decision,
)


def _make_valid_interface(
    executor_id: str = "EXECUTOR-12345678",
    executor_class: ExecutorClass = ExecutorClass.NATIVE,
    declared_capabilities: tuple = (CapabilityType.COMPUTE,),
    version: str = "1.0.0"
) -> ExecutorInterface:
    return ExecutorInterface(
        executor_id=executor_id,
        executor_class=executor_class,
        declared_capabilities=declared_capabilities,
        version=version
    )


def _make_valid_intent(
    intent_id: str = "INTENT-12345678",
    description: str = "Test intent",
    required_capabilities: tuple = (CapabilityType.COMPUTE,)
) -> ExecutionIntent:
    return ExecutionIntent(
        intent_id=intent_id,
        description=description,
        required_capabilities=required_capabilities
    )


class TestValidateExecutorIdDenyByDefault:
    def test_none_returns_false(self) -> None:
        assert validate_executor_id(None) is False

    def test_non_string_returns_false(self) -> None:
        assert validate_executor_id(123) is False  # type: ignore

    def test_empty_returns_false(self) -> None:
        assert validate_executor_id("") is False

    def test_whitespace_returns_false(self) -> None:
        assert validate_executor_id("   ") is False

    def test_invalid_format_returns_false(self) -> None:
        assert validate_executor_id("INVALID-123") is False


class TestValidateExecutorIdPositive:
    def test_valid_format_returns_true(self) -> None:
        assert validate_executor_id("EXECUTOR-12345678") is True


class TestValidateExecutorInterfaceDenyByDefault:
    def test_none_returns_false(self) -> None:
        is_valid, reasons = validate_executor_interface(None)
        assert is_valid is False
        assert "Missing executor interface" in reasons

    def test_invalid_executor_id_returns_false(self) -> None:
        iface = _make_valid_interface(executor_id="INVALID")
        is_valid, reasons = validate_executor_interface(iface)
        assert is_valid is False
        assert "Invalid executor ID" in reasons

    def test_invalid_class_returns_false(self) -> None:
        iface = ExecutorInterface(
            executor_id="EXECUTOR-12345678",
            executor_class="NATIVE",  # type: ignore
            declared_capabilities=(),
            version="1.0.0"
        )
        is_valid, reasons = validate_executor_interface(iface)
        assert is_valid is False
        assert "Invalid executor class" in reasons

    def test_unknown_class_returns_false(self) -> None:
        iface = _make_valid_interface(executor_class=ExecutorClass.UNKNOWN)
        is_valid, reasons = validate_executor_interface(iface)
        assert is_valid is False
        assert "UNKNOWN executor class not permitted" in reasons

    def test_empty_version_returns_false(self) -> None:
        iface = _make_valid_interface(version="")
        is_valid, reasons = validate_executor_interface(iface)
        assert is_valid is False

    def test_whitespace_version_returns_false(self) -> None:
        iface = _make_valid_interface(version="   ")
        is_valid, reasons = validate_executor_interface(iface)
        assert is_valid is False
        assert "Empty version" in reasons

    def test_invalid_capabilities_type_returns_false(self) -> None:
        iface = ExecutorInterface(
            executor_id="EXECUTOR-12345678",
            executor_class=ExecutorClass.NATIVE,
            declared_capabilities=["COMPUTE"],  # type: ignore
            version="1.0.0"
        )
        is_valid, reasons = validate_executor_interface(iface)
        assert is_valid is False
        assert "Capabilities must be a tuple" in reasons

    def test_invalid_capability_in_tuple_returns_false(self) -> None:
        iface = ExecutorInterface(
            executor_id="EXECUTOR-12345678",
            executor_class=ExecutorClass.NATIVE,
            declared_capabilities=("COMPUTE",),  # type: ignore
            version="1.0.0"
        )
        is_valid, reasons = validate_executor_interface(iface)
        assert is_valid is False
        assert "Invalid capability in declared_capabilities" in reasons


class TestValidateExecutorInterfacePositive:
    def test_valid_interface_returns_true(self) -> None:
        iface = _make_valid_interface()
        is_valid, reasons = validate_executor_interface(iface)
        assert is_valid is True
        assert reasons == ()


class TestValidateExecutionIntentDenyByDefault:
    def test_none_returns_false(self) -> None:
        is_valid, reasons = validate_execution_intent(None)
        assert is_valid is False
        assert "Missing execution intent" in reasons

    def test_empty_intent_id_returns_false(self) -> None:
        intent = _make_valid_intent(intent_id="")
        is_valid, reasons = validate_execution_intent(intent)
        assert is_valid is False
        assert "Missing intent ID" in reasons

    def test_whitespace_intent_id_returns_false(self) -> None:
        intent = _make_valid_intent(intent_id="   ")
        is_valid, reasons = validate_execution_intent(intent)
        assert is_valid is False
        assert "Empty intent ID" in reasons

    def test_invalid_intent_id_format_returns_false(self) -> None:
        intent = _make_valid_intent(intent_id="INVALID")
        is_valid, reasons = validate_execution_intent(intent)
        assert is_valid is False
        assert "Invalid intent ID format" in reasons

    def test_empty_description_returns_false(self) -> None:
        intent = _make_valid_intent(description="")
        is_valid, reasons = validate_execution_intent(intent)
        assert is_valid is False

    def test_whitespace_description_returns_false(self) -> None:
        intent = _make_valid_intent(description="   ")
        is_valid, reasons = validate_execution_intent(intent)
        assert is_valid is False
        assert "Empty description" in reasons

    def test_invalid_capabilities_type_returns_false(self) -> None:
        intent = ExecutionIntent(
            intent_id="INTENT-12345678",
            description="Test",
            required_capabilities=["COMPUTE"]  # type: ignore
        )
        is_valid, reasons = validate_execution_intent(intent)
        assert is_valid is False
        assert "Required capabilities must be a tuple" in reasons

    def test_invalid_capability_in_tuple_returns_false(self) -> None:
        intent = ExecutionIntent(
            intent_id="INTENT-12345678",
            description="Test",
            required_capabilities=("COMPUTE",)  # type: ignore
        )
        is_valid, reasons = validate_execution_intent(intent)
        assert is_valid is False
        assert "Invalid capability in required_capabilities" in reasons


class TestValidateExecutionIntentPositive:
    def test_valid_intent_returns_true(self) -> None:
        intent = _make_valid_intent()
        is_valid, reasons = validate_execution_intent(intent)
        assert is_valid is True
        assert reasons == ()


class TestValidateCapabilities:
    def test_none_interface_returns_false(self) -> None:
        intent = _make_valid_intent()
        matches, missing = validate_capabilities(None, intent)
        assert matches is False

    def test_none_intent_returns_false(self) -> None:
        iface = _make_valid_interface()
        matches, missing = validate_capabilities(iface, None)
        assert matches is False

    def test_missing_capability_returns_false(self) -> None:
        iface = _make_valid_interface(declared_capabilities=(CapabilityType.FILE_READ,))
        intent = _make_valid_intent(required_capabilities=(CapabilityType.COMPUTE,))
        matches, missing = validate_capabilities(iface, intent)
        assert matches is False
        assert CapabilityType.COMPUTE in missing


class TestValidateCapabilitiesPositive:
    def test_all_capabilities_present_returns_true(self) -> None:
        iface = _make_valid_interface(
            declared_capabilities=(CapabilityType.COMPUTE, CapabilityType.FILE_READ)
        )
        intent = _make_valid_intent(required_capabilities=(CapabilityType.COMPUTE,))
        matches, missing = validate_capabilities(iface, intent)
        assert matches is True
        assert missing == ()


class TestEvaluateExecutionInterfaceDenyByDefault:
    def test_none_interface_returns_deny(self) -> None:
        intent = _make_valid_intent()
        result = evaluate_execution_interface(None, intent)
        assert result.decision == InterfaceDecision.DENY

    def test_none_intent_returns_deny(self) -> None:
        iface = _make_valid_interface()
        result = evaluate_execution_interface(iface, None)
        assert result.decision == InterfaceDecision.DENY

    def test_invalid_interface_returns_deny(self) -> None:
        iface = _make_valid_interface(executor_id="INVALID")
        intent = _make_valid_intent()
        result = evaluate_execution_interface(iface, intent)
        assert result.decision == InterfaceDecision.DENY

    def test_invalid_intent_returns_deny(self) -> None:
        iface = _make_valid_interface()
        intent = _make_valid_intent(intent_id="INVALID")
        result = evaluate_execution_interface(iface, intent)
        assert result.decision == InterfaceDecision.DENY

    def test_missing_capability_returns_deny(self) -> None:
        iface = _make_valid_interface(declared_capabilities=(CapabilityType.FILE_READ,))
        intent = _make_valid_intent(required_capabilities=(CapabilityType.COMPUTE,))
        result = evaluate_execution_interface(iface, intent)
        assert result.decision == InterfaceDecision.DENY
        assert CapabilityType.COMPUTE in result.missing_capabilities


class TestEvaluateExecutionInterfaceEscalate:
    def test_network_capability_returns_escalate(self) -> None:
        iface = _make_valid_interface(
            declared_capabilities=(CapabilityType.NETWORK,)
        )
        intent = _make_valid_intent(required_capabilities=(CapabilityType.NETWORK,))
        result = evaluate_execution_interface(iface, intent)
        assert result.decision == InterfaceDecision.ESCALATE
        assert "NETWORK capability requires human approval" in result.reasons


class TestEvaluateExecutionInterfacePositive:
    def test_valid_returns_allow(self) -> None:
        iface = _make_valid_interface()
        intent = _make_valid_intent()
        result = evaluate_execution_interface(iface, intent)
        assert result.decision == InterfaceDecision.ALLOW
        assert result.missing_capabilities == ()


class TestGetInterfaceDecisionDenyByDefault:
    def test_none_returns_deny(self) -> None:
        assert get_interface_decision(None) == InterfaceDecision.DENY

    def test_invalid_decision_type_returns_deny(self) -> None:
        result = InterfaceEvaluationResult(
            decision="ALLOW",  # type: ignore
            missing_capabilities=(),
            reasons=()
        )
        assert get_interface_decision(result) == InterfaceDecision.DENY


class TestGetInterfaceDecisionPositive:
    def test_returns_allow(self) -> None:
        result = InterfaceEvaluationResult(
            decision=InterfaceDecision.ALLOW,
            missing_capabilities=(),
            reasons=()
        )
        assert get_interface_decision(result) == InterfaceDecision.ALLOW

    def test_returns_deny(self) -> None:
        result = InterfaceEvaluationResult(
            decision=InterfaceDecision.DENY,
            missing_capabilities=(CapabilityType.COMPUTE,),
            reasons=()
        )
        assert get_interface_decision(result) == InterfaceDecision.DENY

    def test_returns_escalate(self) -> None:
        result = InterfaceEvaluationResult(
            decision=InterfaceDecision.ESCALATE,
            missing_capabilities=(),
            reasons=()
        )
        assert get_interface_decision(result) == InterfaceDecision.ESCALATE
