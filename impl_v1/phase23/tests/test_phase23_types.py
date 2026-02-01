"""Phase-23 Types Tests."""
import pytest
from impl_v1.phase23.phase23_types import (
    EvidenceFormat,
    EvidenceIntegrityStatus,
    VerificationDecision,
)


class TestEvidenceFormatEnum:
    def test_has_exactly_3_members(self) -> None:
        assert len(EvidenceFormat) == 3

    def test_has_json(self) -> None:
        assert EvidenceFormat.JSON.name == "JSON"

    def test_has_binary(self) -> None:
        assert EvidenceFormat.BINARY.name == "BINARY"

    def test_has_text(self) -> None:
        assert EvidenceFormat.TEXT.name == "TEXT"

    def test_all_members_listed(self) -> None:
        expected = {"JSON", "BINARY", "TEXT"}
        actual = {m.name for m in EvidenceFormat}
        assert actual == expected

    def test_members_are_distinct(self) -> None:
        values = [m.value for m in EvidenceFormat]
        assert len(values) == len(set(values))


class TestEvidenceIntegrityStatusEnum:
    def test_has_exactly_4_members(self) -> None:
        assert len(EvidenceIntegrityStatus) == 4

    def test_has_valid(self) -> None:
        assert EvidenceIntegrityStatus.VALID.name == "VALID"

    def test_has_invalid(self) -> None:
        assert EvidenceIntegrityStatus.INVALID.name == "INVALID"

    def test_has_tampered(self) -> None:
        assert EvidenceIntegrityStatus.TAMPERED.name == "TAMPERED"

    def test_has_replayed(self) -> None:
        assert EvidenceIntegrityStatus.REPLAYED.name == "REPLAYED"

    def test_all_members_listed(self) -> None:
        expected = {"VALID", "INVALID", "TAMPERED", "REPLAYED"}
        actual = {m.name for m in EvidenceIntegrityStatus}
        assert actual == expected

    def test_members_are_distinct(self) -> None:
        values = [m.value for m in EvidenceIntegrityStatus]
        assert len(values) == len(set(values))


class TestVerificationDecisionEnum:
    def test_has_exactly_3_members(self) -> None:
        assert len(VerificationDecision) == 3

    def test_has_accept(self) -> None:
        assert VerificationDecision.ACCEPT.name == "ACCEPT"

    def test_has_reject(self) -> None:
        assert VerificationDecision.REJECT.name == "REJECT"

    def test_has_escalate(self) -> None:
        assert VerificationDecision.ESCALATE.name == "ESCALATE"

    def test_all_members_listed(self) -> None:
        expected = {"ACCEPT", "REJECT", "ESCALATE"}
        actual = {m.name for m in VerificationDecision}
        assert actual == expected

    def test_members_are_distinct(self) -> None:
        values = [m.value for m in VerificationDecision]
        assert len(values) == len(set(values))
