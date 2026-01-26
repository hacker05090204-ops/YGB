"""Phase-20 Types Tests."""
import pytest
from impl_v1.phase20.phase20_types import (
    SystemLayer,
    BoundaryViolation,
    BoundaryDecision,
)


class TestSystemLayerEnum:
    def test_has_exactly_5_members(self) -> None:
        assert len(SystemLayer) == 5

    def test_has_root(self) -> None:
        assert SystemLayer.ROOT.name == "ROOT"

    def test_has_governance(self) -> None:
        assert SystemLayer.GOVERNANCE.name == "GOVERNANCE"

    def test_has_execution(self) -> None:
        assert SystemLayer.EXECUTION.name == "EXECUTION"

    def test_has_observation(self) -> None:
        assert SystemLayer.OBSERVATION.name == "OBSERVATION"

    def test_has_human(self) -> None:
        assert SystemLayer.HUMAN.name == "HUMAN"

    def test_all_members_listed(self) -> None:
        expected = {"ROOT", "GOVERNANCE", "EXECUTION", "OBSERVATION", "HUMAN"}
        actual = {m.name for m in SystemLayer}
        assert actual == expected

    def test_members_are_distinct(self) -> None:
        values = [m.value for m in SystemLayer]
        assert len(values) == len(set(values))


class TestBoundaryViolationEnum:
    def test_has_exactly_4_members(self) -> None:
        assert len(BoundaryViolation) == 4

    def test_has_bypass_attempt(self) -> None:
        assert BoundaryViolation.BYPASS_ATTEMPT.name == "BYPASS_ATTEMPT"

    def test_has_unknown_layer(self) -> None:
        assert BoundaryViolation.UNKNOWN_LAYER.name == "UNKNOWN_LAYER"

    def test_has_order_breach(self) -> None:
        assert BoundaryViolation.ORDER_BREACH.name == "ORDER_BREACH"

    def test_has_undefined_root(self) -> None:
        assert BoundaryViolation.UNDEFINED_ROOT.name == "UNDEFINED_ROOT"

    def test_all_members_listed(self) -> None:
        expected = {"BYPASS_ATTEMPT", "UNKNOWN_LAYER", "ORDER_BREACH", "UNDEFINED_ROOT"}
        actual = {m.name for m in BoundaryViolation}
        assert actual == expected

    def test_members_are_distinct(self) -> None:
        values = [m.value for m in BoundaryViolation]
        assert len(values) == len(set(values))


class TestBoundaryDecisionEnum:
    def test_has_exactly_3_members(self) -> None:
        assert len(BoundaryDecision) == 3

    def test_has_allow(self) -> None:
        assert BoundaryDecision.ALLOW.name == "ALLOW"

    def test_has_deny(self) -> None:
        assert BoundaryDecision.DENY.name == "DENY"

    def test_has_escalate(self) -> None:
        assert BoundaryDecision.ESCALATE.name == "ESCALATE"

    def test_all_members_listed(self) -> None:
        expected = {"ALLOW", "DENY", "ESCALATE"}
        actual = {m.name for m in BoundaryDecision}
        assert actual == expected

    def test_members_are_distinct(self) -> None:
        values = [m.value for m in BoundaryDecision]
        assert len(values) == len(set(values))
