"""
Phase-27 Types Tests.

Tests for CLOSED enums:
- EnvelopeStatus: 3 members

Tests enforce:
- Exact member counts (closedness)
- No additional members
- Correct member names/values
"""
import pytest

from impl_v1.phase27.phase27_types import EnvelopeStatus


class TestEnvelopeStatusEnum:
    """Tests for EnvelopeStatus enum closedness."""

    def test_envelope_status_has_exactly_3_members(self) -> None:
        """EnvelopeStatus must have exactly 3 members."""
        assert len(EnvelopeStatus) == 3

    def test_envelope_status_has_created(self) -> None:
        """EnvelopeStatus must have CREATED."""
        assert EnvelopeStatus.CREATED is not None
        assert EnvelopeStatus.CREATED.name == "CREATED"

    def test_envelope_status_has_validated(self) -> None:
        """EnvelopeStatus must have VALIDATED."""
        assert EnvelopeStatus.VALIDATED is not None
        assert EnvelopeStatus.VALIDATED.name == "VALIDATED"

    def test_envelope_status_has_invalid(self) -> None:
        """EnvelopeStatus must have INVALID."""
        assert EnvelopeStatus.INVALID is not None
        assert EnvelopeStatus.INVALID.name == "INVALID"

    def test_envelope_status_all_members_listed(self) -> None:
        """All EnvelopeStatus members must be exactly as expected."""
        expected = {"CREATED", "VALIDATED", "INVALID"}
        actual = {m.name for m in EnvelopeStatus}
        assert actual == expected

    def test_envelope_status_members_are_distinct(self) -> None:
        """All EnvelopeStatus members must have distinct values."""
        values = [m.value for m in EnvelopeStatus]
        assert len(values) == len(set(values))
