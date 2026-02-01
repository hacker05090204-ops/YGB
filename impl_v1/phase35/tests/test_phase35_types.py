"""Phase-35 Types Tests."""
import pytest
from impl_v1.phase35.phase35_types import (
    ExecutorClass,
    CapabilityType,
    InterfaceDecision,
)


class TestExecutorClassEnum:
    def test_has_exactly_4_members(self) -> None:
        assert len(ExecutorClass) == 4

    def test_has_native(self) -> None:
        assert ExecutorClass.NATIVE.name == "NATIVE"

    def test_has_browser(self) -> None:
        assert ExecutorClass.BROWSER.name == "BROWSER"

    def test_has_api(self) -> None:
        assert ExecutorClass.API.name == "API"

    def test_has_unknown(self) -> None:
        assert ExecutorClass.UNKNOWN.name == "UNKNOWN"

    def test_all_members_listed(self) -> None:
        expected = {"NATIVE", "BROWSER", "API", "UNKNOWN"}
        actual = {m.name for m in ExecutorClass}
        assert actual == expected

    def test_members_are_distinct(self) -> None:
        values = [m.value for m in ExecutorClass]
        assert len(values) == len(set(values))


class TestCapabilityTypeEnum:
    def test_has_exactly_4_members(self) -> None:
        assert len(CapabilityType) == 4

    def test_has_compute(self) -> None:
        assert CapabilityType.COMPUTE.name == "COMPUTE"

    def test_has_file_read(self) -> None:
        assert CapabilityType.FILE_READ.name == "FILE_READ"

    def test_has_file_write(self) -> None:
        assert CapabilityType.FILE_WRITE.name == "FILE_WRITE"

    def test_has_network(self) -> None:
        assert CapabilityType.NETWORK.name == "NETWORK"

    def test_all_members_listed(self) -> None:
        expected = {"COMPUTE", "FILE_READ", "FILE_WRITE", "NETWORK"}
        actual = {m.name for m in CapabilityType}
        assert actual == expected

    def test_members_are_distinct(self) -> None:
        values = [m.value for m in CapabilityType]
        assert len(values) == len(set(values))


class TestInterfaceDecisionEnum:
    def test_has_exactly_3_members(self) -> None:
        assert len(InterfaceDecision) == 3

    def test_has_allow(self) -> None:
        assert InterfaceDecision.ALLOW.name == "ALLOW"

    def test_has_deny(self) -> None:
        assert InterfaceDecision.DENY.name == "DENY"

    def test_has_escalate(self) -> None:
        assert InterfaceDecision.ESCALATE.name == "ESCALATE"

    def test_all_members_listed(self) -> None:
        expected = {"ALLOW", "DENY", "ESCALATE"}
        actual = {m.name for m in InterfaceDecision}
        assert actual == expected

    def test_members_are_distinct(self) -> None:
        values = [m.value for m in InterfaceDecision]
        assert len(values) == len(set(values))
