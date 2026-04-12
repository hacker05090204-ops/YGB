"""
TEST APPROVAL LEDGER — Signing, Chain Integrity, Tamper Detection
=================================================================
Validates the append-only hash-chained approval ledger.
NO boolean flags allowed for human approval.
"""

import os
import sys
import tempfile
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.insert(0, os.path.join(PROJECT_ROOT, 'backend'))

from governance.approval_ledger import ApprovalLedger, ApprovalToken


# ==================================================================
# TOKEN SIGNING
# ==================================================================

class TestTokenSigning:
    """Verify HMAC-based token creation."""

    def setup_method(self):
        self.tmp = tempfile.mkdtemp()
        self.ledger = ApprovalLedger(
            ledger_path=os.path.join(self.tmp, "test_ledger.jsonl")
        )

    def test_sign_returns_token(self):
        token = self.ledger.sign_approval(0, "admin-001", "Certification review passed")
        assert isinstance(token, ApprovalToken)
        assert token.field_id == 0
        assert token.approver_id == "admin-001"
        assert token.signature != ""

    def test_sign_requires_approver_id(self):
        with pytest.raises(ValueError, match="approver_id"):
            self.ledger.sign_approval(0, "", "reason")

    def test_sign_requires_reason(self):
        with pytest.raises(ValueError, match="reason"):
            self.ledger.sign_approval(0, "admin", "")

    def test_token_not_boolean(self):
        """Approval token is NOT a boolean — it's a signed structure."""
        token = self.ledger.sign_approval(0, "admin", "review passed")
        assert not isinstance(token, bool)
        assert hasattr(token, "signature")
        assert hasattr(token, "approver_id")
        assert hasattr(token, "timestamp")


# ==================================================================
# TOKEN VERIFICATION
# ==================================================================

class TestTokenVerification:
    """Verify HMAC signature checks."""

    def setup_method(self):
        self.tmp = tempfile.mkdtemp()
        self.ledger = ApprovalLedger(
            ledger_path=os.path.join(self.tmp, "test_ledger.jsonl")
        )

    def test_valid_token_verifies(self):
        token = self.ledger.sign_approval(0, "admin", "passed")
        assert self.ledger.verify_token(token) is True

    def test_tampered_signature_fails(self):
        token = self.ledger.sign_approval(0, "admin", "passed")
        token.signature = "0" * 64
        assert self.ledger.verify_token(token) is False

    def test_tampered_field_id_fails(self):
        token = self.ledger.sign_approval(0, "admin", "passed")
        token.field_id = 99
        assert self.ledger.verify_token(token) is False


# ==================================================================
# APPEND-ONLY CHAIN
# ==================================================================

class TestAppendOnlyChain:
    """Verify hash chain integrity."""

    def setup_method(self):
        self.tmp = tempfile.mkdtemp()
        path = os.path.join(self.tmp, "ledger.jsonl")
        self.ledger = ApprovalLedger(ledger_path=path)

    def test_genesis_hash(self):
        assert self.ledger.chain_hash == "0" * 64

    def test_single_append(self):
        token = self.ledger.sign_approval(0, "admin", "cert review")
        entry = self.ledger.append(token)
        assert entry["sequence"] == 0
        assert self.ledger.entry_count == 1
        assert self.ledger.chain_hash != "0" * 64

    def test_chain_links(self):
        t1 = self.ledger.sign_approval(0, "admin", "field 0")
        t2 = self.ledger.sign_approval(1, "admin", "field 1")
        e1 = self.ledger.append(t1)
        e2 = self.ledger.append(t2)
        assert e2["prev_hash"] == e1["entry_hash"]

    def test_verify_chain_valid(self):
        for i in range(5):
            t = self.ledger.sign_approval(i, "admin", f"field {i}")
            self.ledger.append(t)
        assert self.ledger.verify_chain() is True

    def test_verify_chain_tampered(self):
        for i in range(3):
            t = self.ledger.sign_approval(i, "admin", f"field {i}")
            self.ledger.append(t)
        # Tamper with entry
        self.ledger._entries[1]["entry_hash"] = "TAMPERED"
        assert self.ledger.verify_chain() is False


# ==================================================================
# FIELD LOOKUP
# ==================================================================

class TestFieldLookup:
    """Verify field approval queries."""

    def setup_method(self):
        self.tmp = tempfile.mkdtemp()
        path = os.path.join(self.tmp, "ledger.jsonl")
        self.ledger = ApprovalLedger(ledger_path=path)

    def test_no_approval(self):
        assert self.ledger.has_approval(0) is False
        assert self.ledger.get_approval(0) is None

    def test_has_approval_after_append(self):
        t = self.ledger.sign_approval(5, "admin", "passed")
        self.ledger.append(t)
        assert self.ledger.has_approval(5) is True
        assert self.ledger.has_approval(0) is False

    def test_get_approval_returns_entry(self):
        t = self.ledger.sign_approval(3, "admin", "review ok")
        self.ledger.append(t)
        entry = self.ledger.get_approval(3)
        assert entry is not None
        assert entry["token"]["field_id"] == 3


# ==================================================================
# PERSISTENCE
# ==================================================================

class TestLedgerPersistence:
    """Verify file-based persistence and reload."""

    def test_save_and_reload(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "ledger.jsonl")
            ledger1 = ApprovalLedger(ledger_path=path)

            t = ledger1.sign_approval(0, "admin", "approved")
            ledger1.append(t)
            t = ledger1.sign_approval(1, "admin", "approved")
            ledger1.append(t)

            # Reload
            ledger2 = ApprovalLedger(ledger_path=path)
            ledger2.load()
            assert ledger2.entry_count == 2
            assert ledger2.has_approval(0) is True
            assert ledger2.has_approval(1) is True


def test_env_key_mode_logs_critical_in_production(monkeypatch, caplog):
    import backend.governance.approval_ledger as approval_ledger_module

    monkeypatch.delenv("YGB_KEY_DIR", raising=False)
    monkeypatch.setenv("YGB_APPROVAL_SECRET", "a" * 64)
    monkeypatch.setenv("YGB_ENV", "production")

    with caplog.at_level("CRITICAL"):
        approval_ledger_module._log_ledger_key_mode_startup_status()

    assert approval_ledger_module.get_ledger_key_mode() is approval_ledger_module.LedgerKeyMode.ENV_KEY
    assert any(
        record.levelname == "CRITICAL" and "ENV_KEY" in record.message
        for record in caplog.records
    )


def test_governance_key_status_endpoint_returns_production_safe_payload(monkeypatch):
    import backend.api.runtime_api as runtime_api

    monkeypatch.delenv("YGB_KEY_DIR", raising=False)
    monkeypatch.setenv("YGB_APPROVAL_SECRET", "a" * 64)
    monkeypatch.setenv("YGB_ENV", "production")
    monkeypatch.delenv("YGB_AUTHORITY_KEY", raising=False)

    app = FastAPI()
    app.include_router(runtime_api.router)
    app.dependency_overrides[runtime_api.require_admin] = lambda: {
        "sub": "admin-1",
        "role": "admin",
    }
    client = TestClient(app)

    response = client.get("/api/v1/governance/key-status")

    assert response.status_code == 200

    payload = response.json()
    assert payload["status"] == "ERROR"
    assert payload["production_mode"] is True
    assert payload["key_mode"] == "ENV_KEY"
    assert payload["using_env_fallback"] is True
    assert payload["key_dir"] is None
    assert payload["available"] is False
    assert payload["available_key_ids"] == []
    assert payload["audit_events"] == []
    assert payload["error"] == "signing_key_unavailable"
    assert "YGB_APPROVAL_SECRET" not in response.text
    assert ("a" * 64) not in response.text
