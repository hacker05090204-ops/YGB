import logging

import pytest

from backend.governance import approval_ledger


@pytest.fixture(autouse=True)
def _approval_secret(monkeypatch):
    monkeypatch.setenv("YGB_APPROVAL_SECRET", "a" * 64)
    monkeypatch.delenv("YGB_KEY_DIR", raising=False)
    monkeypatch.setattr(approval_ledger, "last_integrity_report", None)


def test_ledger_integrity_check_passes_for_valid_chain(tmp_path):
    ledger = approval_ledger.ApprovalLedger(ledger_path=str(tmp_path / "approval_ledger.jsonl"))
    ledger.append(ledger.sign_approval(1, "admin-1", "approved"))
    ledger.append(ledger.sign_approval(2, "admin-1", "approved"))

    report = approval_ledger.LedgerIntegrityCheck.verify(list(ledger._entries))

    assert report.entries_checked == 2
    assert report.hash_chain_valid is True
    assert report.first_broken_entry_id is None


def test_ledger_integrity_check_detects_tampered_entry_with_correct_id(tmp_path):
    ledger = approval_ledger.ApprovalLedger(ledger_path=str(tmp_path / "approval_ledger.jsonl"))
    ledger.append(ledger.sign_approval(1, "admin-1", "first"))
    ledger.append(ledger.sign_approval(2, "admin-1", "second"))
    ledger.append(ledger.sign_approval(3, "admin-1", "third"))
    ledger._entries[1]["token"]["reason"] = "tampered"

    report = approval_ledger.LedgerIntegrityCheck.verify(list(ledger._entries))

    assert report.hash_chain_valid is False
    assert report.first_broken_entry_id == str(ledger._entries[1]["sequence"])


def test_ledger_integrity_check_logs_critical_on_tamper(tmp_path, caplog):
    ledger = approval_ledger.ApprovalLedger(ledger_path=str(tmp_path / "approval_ledger.jsonl"))
    ledger.append(ledger.sign_approval(1, "admin-1", "approved"))
    ledger._entries[0]["entry_hash"] = "broken"

    with caplog.at_level(logging.CRITICAL):
        report = approval_ledger.LedgerIntegrityCheck.verify(list(ledger._entries))

    assert report.hash_chain_valid is False
    assert any(record.levelno == logging.CRITICAL for record in caplog.records)

