"""
Phase-25 Types Tests.

Tests for CLOSED enums:
- EnvelopeIntegrityStatus: 3 members
- IntegrityViolation: 4 members
"""
import pytest

from impl_v1.phase25.phase25_types import (
    EnvelopeIntegrityStatus,
    IntegrityViolation,
)


class TestEnvelopeIntegrityStatusEnum:
    """Tests for EnvelopeIntegrityStatus enum closedness."""

    def test_has_exactly_3_members(self) -> None:
        assert len(EnvelopeIntegrityStatus) == 3

    def test_has_valid(self) -> None:
        assert EnvelopeIntegrityStatus.VALID.name == "VALID"

    def test_has_invalid(self) -> None:
        assert EnvelopeIntegrityStatus.INVALID.name == "INVALID"

    def test_has_tampered(self) -> None:
        assert EnvelopeIntegrityStatus.TAMPERED.name == "TAMPERED"

    def test_all_members_listed(self) -> None:
        expected = {"VALID", "INVALID", "TAMPERED"}
        actual = {m.name for m in EnvelopeIntegrityStatus}
        assert actual == expected

    def test_members_are_distinct(self) -> None:
        values = [m.value for m in EnvelopeIntegrityStatus]
        assert len(values) == len(set(values))


class TestIntegrityViolationEnum:
    """Tests for IntegrityViolation enum closedness."""

    def test_has_exactly_4_members(self) -> None:
        assert len(IntegrityViolation) == 4

    def test_has_hash_mismatch(self) -> None:
        assert IntegrityViolation.HASH_MISMATCH.name == "HASH_MISMATCH"

    def test_has_missing_fields(self) -> None:
        assert IntegrityViolation.MISSING_FIELDS.name == "MISSING_FIELDS"

    def test_has_order_violation(self) -> None:
        assert IntegrityViolation.ORDER_VIOLATION.name == "ORDER_VIOLATION"

    def test_has_unknown_version(self) -> None:
        assert IntegrityViolation.UNKNOWN_VERSION.name == "UNKNOWN_VERSION"

    def test_all_members_listed(self) -> None:
        expected = {"HASH_MISMATCH", "MISSING_FIELDS", "ORDER_VIOLATION", "UNKNOWN_VERSION"}
        actual = {m.name for m in IntegrityViolation}
        assert actual == expected

    def test_members_are_distinct(self) -> None:
        values = [m.value for m in IntegrityViolation]
        assert len(values) == len(set(values))
