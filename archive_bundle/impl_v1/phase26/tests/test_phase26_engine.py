"""
Phase-26 Engine Tests.

Tests for VALIDATION-ONLY functions:
- validate_readiness_context
- evaluate_readiness
- get_readiness_status
- get_blockers
- is_execution_ready

Tests enforce:
- Deny-by-default (None, invalid)
- Negative paths > positive paths
- BLOCKED as default
"""
import pytest

from impl_v1.phase26.phase26_types import (
    ReadinessStatus,
    ReadinessBlocker,
)
from impl_v1.phase26.phase26_context import (
    ExecutionReadinessContext,
    ReadinessResult,
)
from impl_v1.phase26.phase26_engine import (
    validate_readiness_context,
    evaluate_readiness,
    get_readiness_status,
    get_blockers,
    is_execution_ready,
)


# --- Helpers ---

def _make_valid_context(
    authorization_ok: bool = True,
    intent_bound: bool = True,
    handshake_valid: bool = True,
    observation_valid: bool = True,
    human_decision_final: bool = True
) -> ExecutionReadinessContext:
    return ExecutionReadinessContext(
        authorization_ok=authorization_ok,
        intent_bound=intent_bound,
        handshake_valid=handshake_valid,
        observation_valid=observation_valid,
        human_decision_final=human_decision_final
    )


# ============================================================================
# validate_readiness_context TESTS
# ============================================================================

class TestValidateReadinessContextDenyByDefault:
    """Deny-by-default tests for validate_readiness_context."""

    def test_none_returns_false(self) -> None:
        """None → False."""
        assert validate_readiness_context(None) is False

    def test_non_bool_authorization_returns_false(self) -> None:
        """Non-bool authorization_ok → False."""
        context = ExecutionReadinessContext(
            authorization_ok="True",  # type: ignore
            intent_bound=True,
            handshake_valid=True,
            observation_valid=True,
            human_decision_final=True
        )
        assert validate_readiness_context(context) is False

    def test_non_bool_intent_returns_false(self) -> None:
        """Non-bool intent_bound → False."""
        context = ExecutionReadinessContext(
            authorization_ok=True,
            intent_bound="True",  # type: ignore
            handshake_valid=True,
            observation_valid=True,
            human_decision_final=True
        )
        assert validate_readiness_context(context) is False

    def test_non_bool_handshake_returns_false(self) -> None:
        """Non-bool handshake_valid → False."""
        context = ExecutionReadinessContext(
            authorization_ok=True,
            intent_bound=True,
            handshake_valid=1,  # type: ignore
            observation_valid=True,
            human_decision_final=True
        )
        assert validate_readiness_context(context) is False

    def test_non_bool_observation_returns_false(self) -> None:
        """Non-bool observation_valid → False."""
        context = ExecutionReadinessContext(
            authorization_ok=True,
            intent_bound=True,
            handshake_valid=True,
            observation_valid=None,  # type: ignore
            human_decision_final=True
        )
        assert validate_readiness_context(context) is False

    def test_non_bool_human_decision_returns_false(self) -> None:
        """Non-bool human_decision_final → False."""
        context = ExecutionReadinessContext(
            authorization_ok=True,
            intent_bound=True,
            handshake_valid=True,
            observation_valid=True,
            human_decision_final=0  # type: ignore
        )
        assert validate_readiness_context(context) is False


class TestValidateReadinessContextPositive:
    """Positive tests for validate_readiness_context."""

    def test_all_true_returns_true(self) -> None:
        """All True → True."""
        context = _make_valid_context()
        assert validate_readiness_context(context) is True

    def test_all_false_returns_true(self) -> None:
        """All False (valid structure) → True."""
        context = _make_valid_context(
            authorization_ok=False,
            intent_bound=False,
            handshake_valid=False,
            observation_valid=False,
            human_decision_final=False
        )
        assert validate_readiness_context(context) is True


# ============================================================================
# evaluate_readiness TESTS
# ============================================================================

class TestEvaluateReadinessDenyByDefault:
    """Deny-by-default tests for evaluate_readiness."""

    def test_none_returns_blocked(self) -> None:
        """None → BLOCKED with all blockers."""
        result = evaluate_readiness(None)
        assert result.status == ReadinessStatus.BLOCKED
        assert len(result.blockers) == 5

    def test_invalid_context_returns_blocked(self) -> None:
        """Invalid context → BLOCKED with all blockers."""
        context = ExecutionReadinessContext(
            authorization_ok="True",  # type: ignore
            intent_bound=True,
            handshake_valid=True,
            observation_valid=True,
            human_decision_final=True
        )
        result = evaluate_readiness(context)
        assert result.status == ReadinessStatus.BLOCKED
        assert len(result.blockers) == 5


class TestEvaluateReadinessNotReady:
    """NOT_READY tests for evaluate_readiness."""

    def test_missing_authorization_returns_not_ready(self) -> None:
        """Missing authorization → NOT_READY."""
        context = _make_valid_context(authorization_ok=False)
        result = evaluate_readiness(context)
        assert result.status == ReadinessStatus.NOT_READY
        assert ReadinessBlocker.MISSING_AUTHORIZATION in result.blockers

    def test_missing_intent_returns_not_ready(self) -> None:
        """Missing intent → NOT_READY."""
        context = _make_valid_context(intent_bound=False)
        result = evaluate_readiness(context)
        assert result.status == ReadinessStatus.NOT_READY
        assert ReadinessBlocker.MISSING_INTENT in result.blockers

    def test_handshake_failed_returns_not_ready(self) -> None:
        """Handshake failed → NOT_READY."""
        context = _make_valid_context(handshake_valid=False)
        result = evaluate_readiness(context)
        assert result.status == ReadinessStatus.NOT_READY
        assert ReadinessBlocker.HANDSHAKE_FAILED in result.blockers

    def test_observation_invalid_returns_not_ready(self) -> None:
        """Observation invalid → NOT_READY."""
        context = _make_valid_context(observation_valid=False)
        result = evaluate_readiness(context)
        assert result.status == ReadinessStatus.NOT_READY
        assert ReadinessBlocker.OBSERVATION_INVALID in result.blockers

    def test_human_decision_pending_returns_not_ready(self) -> None:
        """Human decision pending → NOT_READY."""
        context = _make_valid_context(human_decision_final=False)
        result = evaluate_readiness(context)
        assert result.status == ReadinessStatus.NOT_READY
        assert ReadinessBlocker.HUMAN_DECISION_PENDING in result.blockers

    def test_multiple_blockers_returns_not_ready(self) -> None:
        """Multiple blockers → NOT_READY with all blockers."""
        context = _make_valid_context(
            authorization_ok=False,
            intent_bound=False
        )
        result = evaluate_readiness(context)
        assert result.status == ReadinessStatus.NOT_READY
        assert len(result.blockers) == 2
        assert ReadinessBlocker.MISSING_AUTHORIZATION in result.blockers
        assert ReadinessBlocker.MISSING_INTENT in result.blockers

    def test_all_false_returns_not_ready(self) -> None:
        """All False → NOT_READY with all blockers."""
        context = _make_valid_context(
            authorization_ok=False,
            intent_bound=False,
            handshake_valid=False,
            observation_valid=False,
            human_decision_final=False
        )
        result = evaluate_readiness(context)
        assert result.status == ReadinessStatus.NOT_READY
        assert len(result.blockers) == 5


class TestEvaluateReadinessPositive:
    """Positive tests for evaluate_readiness."""

    def test_all_true_returns_ready(self) -> None:
        """All True → READY."""
        context = _make_valid_context()
        result = evaluate_readiness(context, timestamp="2026-01-26T12:00:00Z")
        assert result.status == ReadinessStatus.READY
        assert result.blockers == ()
        assert result.evaluated_at == "2026-01-26T12:00:00Z"


# ============================================================================
# get_readiness_status TESTS
# ============================================================================

class TestGetReadinessStatusDenyByDefault:
    """Deny-by-default tests for get_readiness_status."""

    def test_none_returns_blocked(self) -> None:
        """None → BLOCKED."""
        assert get_readiness_status(None) == ReadinessStatus.BLOCKED

    def test_invalid_status_type_returns_blocked(self) -> None:
        """Invalid status type → BLOCKED."""
        result = ReadinessResult(
            status="READY",  # type: ignore
            blockers=(),
            evaluated_at="2026-01-26T12:00:00Z"
        )
        assert get_readiness_status(result) == ReadinessStatus.BLOCKED


class TestGetReadinessStatusPositive:
    """Positive tests for get_readiness_status."""

    def test_returns_ready(self) -> None:
        """Returns READY."""
        result = ReadinessResult(
            status=ReadinessStatus.READY,
            blockers=(),
            evaluated_at="2026-01-26T12:00:00Z"
        )
        assert get_readiness_status(result) == ReadinessStatus.READY

    def test_returns_not_ready(self) -> None:
        """Returns NOT_READY."""
        result = ReadinessResult(
            status=ReadinessStatus.NOT_READY,
            blockers=(ReadinessBlocker.MISSING_AUTHORIZATION,),
            evaluated_at="2026-01-26T12:00:00Z"
        )
        assert get_readiness_status(result) == ReadinessStatus.NOT_READY


# ============================================================================
# get_blockers TESTS
# ============================================================================

class TestGetBlockersDenyByDefault:
    """Deny-by-default tests for get_blockers."""

    def test_none_returns_all_blockers(self) -> None:
        """None → all blockers."""
        blockers = get_blockers(None)
        assert len(blockers) == 5

    def test_invalid_blockers_type_returns_all(self) -> None:
        """Invalid blockers type → all blockers."""
        result = ReadinessResult(
            status=ReadinessStatus.NOT_READY,
            blockers="invalid",  # type: ignore
            evaluated_at="2026-01-26T12:00:00Z"
        )
        blockers = get_blockers(result)
        assert len(blockers) == 5

    def test_invalid_blocker_in_tuple_returns_all(self) -> None:
        """Invalid blocker in tuple → all blockers."""
        result = ReadinessResult(
            status=ReadinessStatus.NOT_READY,
            blockers=("MISSING_AUTHORIZATION",),  # type: ignore
            evaluated_at="2026-01-26T12:00:00Z"
        )
        blockers = get_blockers(result)
        assert len(blockers) == 5


class TestGetBlockersPositive:
    """Positive tests for get_blockers."""

    def test_returns_empty_for_ready(self) -> None:
        """Returns empty for READY."""
        result = ReadinessResult(
            status=ReadinessStatus.READY,
            blockers=(),
            evaluated_at="2026-01-26T12:00:00Z"
        )
        assert get_blockers(result) == ()

    def test_returns_blockers(self) -> None:
        """Returns blockers."""
        result = ReadinessResult(
            status=ReadinessStatus.NOT_READY,
            blockers=(ReadinessBlocker.MISSING_AUTHORIZATION,),
            evaluated_at="2026-01-26T12:00:00Z"
        )
        assert get_blockers(result) == (ReadinessBlocker.MISSING_AUTHORIZATION,)


# ============================================================================
# is_execution_ready TESTS
# ============================================================================

class TestIsExecutionReadyDenyByDefault:
    """Deny-by-default tests for is_execution_ready."""

    def test_none_returns_false(self) -> None:
        """None → False."""
        assert is_execution_ready(None) is False

    def test_invalid_status_type_returns_false(self) -> None:
        """Invalid status type → False."""
        result = ReadinessResult(
            status="READY",  # type: ignore
            blockers=(),
            evaluated_at="2026-01-26T12:00:00Z"
        )
        assert is_execution_ready(result) is False

    def test_not_ready_returns_false(self) -> None:
        """NOT_READY → False."""
        result = ReadinessResult(
            status=ReadinessStatus.NOT_READY,
            blockers=(ReadinessBlocker.MISSING_AUTHORIZATION,),
            evaluated_at="2026-01-26T12:00:00Z"
        )
        assert is_execution_ready(result) is False

    def test_blocked_returns_false(self) -> None:
        """BLOCKED → False."""
        result = ReadinessResult(
            status=ReadinessStatus.BLOCKED,
            blockers=(ReadinessBlocker.MISSING_AUTHORIZATION,),
            evaluated_at="2026-01-26T12:00:00Z"
        )
        assert is_execution_ready(result) is False


class TestIsExecutionReadyPositive:
    """Positive tests for is_execution_ready."""

    def test_ready_returns_true(self) -> None:
        """READY → True."""
        result = ReadinessResult(
            status=ReadinessStatus.READY,
            blockers=(),
            evaluated_at="2026-01-26T12:00:00Z"
        )
        assert is_execution_ready(result) is True
