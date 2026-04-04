"""
Phase-33 Context Tests.

Tests for dataclass immutability.
"""
import pytest
from dataclasses import FrozenInstanceError


class TestExecutionIntentImmutability:
    """Test ExecutionIntent is frozen."""

    def _create_valid_intent(self):
        from impl_v1.phase33.phase33_context import ExecutionIntent
        return ExecutionIntent(
            intent_id="INTENT-abc12345",
            decision_id="DEC-def67890",
            decision_type="CONTINUE",
            evidence_chain_hash="evidencehash123",
            session_id="SESS-ghi11111",
            execution_state="AWAITING_DECISION",
            created_at="2026-01-26T12:00:00Z",
            created_by="human-1",
            intent_hash="hash123"
        )

    def test_can_create(self) -> None:
        intent = self._create_valid_intent()
        assert intent.intent_id == "INTENT-abc12345"

    def test_cannot_modify_intent_id(self) -> None:
        intent = self._create_valid_intent()
        with pytest.raises(FrozenInstanceError):
            intent.intent_id = "HACKED"  # type: ignore

    def test_cannot_modify_decision_id(self) -> None:
        intent = self._create_valid_intent()
        with pytest.raises(FrozenInstanceError):
            intent.decision_id = "HACKED"  # type: ignore

    def test_cannot_modify_decision_type(self) -> None:
        intent = self._create_valid_intent()
        with pytest.raises(FrozenInstanceError):
            intent.decision_type = "HACKED"  # type: ignore

    def test_has_nine_fields(self) -> None:
        from impl_v1.phase33.phase33_context import ExecutionIntent
        import dataclasses
        assert len(dataclasses.fields(ExecutionIntent)) == 9


class TestIntentRevocationImmutability:
    """Test IntentRevocation is frozen."""

    def _create_valid_revocation(self):
        from impl_v1.phase33.phase33_context import IntentRevocation
        return IntentRevocation(
            revocation_id="INTENTREV-abc12345",
            intent_id="INTENT-def67890",
            revoked_by="human-1",
            revocation_reason="Security concern",
            revoked_at="2026-01-26T13:00:00Z",
            revocation_hash="revhash123"
        )

    def test_can_create(self) -> None:
        rev = self._create_valid_revocation()
        assert rev.revocation_id == "INTENTREV-abc12345"

    def test_cannot_modify_revocation_id(self) -> None:
        rev = self._create_valid_revocation()
        with pytest.raises(FrozenInstanceError):
            rev.revocation_id = "HACKED"  # type: ignore

    def test_has_six_fields(self) -> None:
        from impl_v1.phase33.phase33_context import IntentRevocation
        import dataclasses
        assert len(dataclasses.fields(IntentRevocation)) == 6


class TestIntentRecordImmutability:
    """Test IntentRecord is frozen."""

    def _create_valid_record(self):
        from impl_v1.phase33.phase33_context import IntentRecord
        return IntentRecord(
            record_id="INTREC-abc12345",
            record_type="BINDING",
            intent_id="INTENT-def67890",
            timestamp="2026-01-26T12:00:00Z",
            prior_hash="",
            self_hash="rechash123"
        )

    def test_can_create(self) -> None:
        rec = self._create_valid_record()
        assert rec.record_id == "INTREC-abc12345"

    def test_cannot_modify_record_id(self) -> None:
        rec = self._create_valid_record()
        with pytest.raises(FrozenInstanceError):
            rec.record_id = "HACKED"  # type: ignore

    def test_has_six_fields(self) -> None:
        from impl_v1.phase33.phase33_context import IntentRecord
        import dataclasses
        assert len(dataclasses.fields(IntentRecord)) == 6


class TestIntentAuditImmutability:
    """Test IntentAudit is frozen."""

    def _create_empty_audit(self):
        from impl_v1.phase33.phase33_context import IntentAudit
        return IntentAudit(
            audit_id="INTAUDIT-abc12345",
            records=(),
            session_id="SESS-def67890",
            head_hash="",
            length=0
        )

    def test_can_create(self) -> None:
        audit = self._create_empty_audit()
        assert audit.audit_id == "INTAUDIT-abc12345"

    def test_cannot_modify_audit_id(self) -> None:
        audit = self._create_empty_audit()
        with pytest.raises(FrozenInstanceError):
            audit.audit_id = "HACKED"  # type: ignore

    def test_has_five_fields(self) -> None:
        from impl_v1.phase33.phase33_context import IntentAudit
        import dataclasses
        assert len(dataclasses.fields(IntentAudit)) == 5

    def test_records_is_tuple(self) -> None:
        audit = self._create_empty_audit()
        assert isinstance(audit.records, tuple)
