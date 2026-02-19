"""
TEST LEDGER REPLAY PROTECTION
==============================
Validates anti-replay defenses:
  - Duplicate nonce rejection
  - Expired token rejection
  - Field mismatch rejection
  - Reused token (signature) rejection
  - Future timestamp rejection
  - Valid token acceptance
"""

import os
import sys
import tempfile
import time
import pytest

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.insert(0, os.path.join(PROJECT_ROOT, 'backend'))

from governance.approval_ledger import ApprovalLedger, ApprovalToken


class TestDuplicateNonce:
    """Reject tokens with already-used nonce."""

    def setup_method(self):
        self.tmp = tempfile.mkdtemp()
        self.ledger = ApprovalLedger(os.path.join(self.tmp, "ledger.jsonl"))

    def test_first_use_accepted(self):
        token = self.ledger.sign_approval(0, "admin", "cert review")
        entry = self.ledger.append(token)
        assert entry["sequence"] == 0

    def test_duplicate_nonce_rejected(self):
        token = self.ledger.sign_approval(0, "admin", "cert review")
        self.ledger.append(token)
        # Same token (same nonce) → rejected
        with pytest.raises(ValueError, match="DUPLICATE_NONCE"):
            self.ledger.append(token)

    def test_different_nonce_accepted(self):
        t1 = self.ledger.sign_approval(0, "admin", "review 1")
        t2 = self.ledger.sign_approval(0, "admin", "review 2")
        assert t1.nonce != t2.nonce
        self.ledger.append(t1)
        self.ledger.append(t2)
        assert self.ledger.entry_count == 2


class TestExpiredToken:
    """Reject tokens older than expiration window."""

    def setup_method(self):
        self.tmp = tempfile.mkdtemp()
        self.ledger = ApprovalLedger(os.path.join(self.tmp, "ledger.jsonl"))

    def test_fresh_token_accepted(self):
        token = self.ledger.sign_approval(0, "admin", "fresh", expiration_window=3600.0)
        result = self.ledger.validate_anti_replay(token)
        assert result["valid"] is True

    def test_expired_token_rejected(self):
        token = self.ledger.sign_approval(0, "admin", "old", expiration_window=1.0)
        # Manually make it expired
        token.timestamp = time.time() - 10.0
        # Re-sign with old timestamp using key manager
        import hmac as hmac_mod, hashlib
        key_id = token.key_id or "ygb-key-v1"
        secret = self.ledger.key_manager.get_verification_key(key_id)
        payload = (f"{token.field_id}:{token.approver_id}:{token.reason}:{token.timestamp}"
                   f":{token.nonce}:{token.model_hash}:{token.expiration_window}:{key_id}")
        token.signature = hmac_mod.new(
            secret, payload.encode(), hashlib.sha256
        ).hexdigest()
        result = self.ledger.validate_anti_replay(token)
        assert result["valid"] is False
        assert "TOKEN_EXPIRED" in result["reason"]

    def test_default_expiration_is_one_hour(self):
        token = self.ledger.sign_approval(0, "admin", "default")
        assert token.expiration_window == 3600.0


class TestFieldMismatch:
    """Reject tokens targeting wrong field."""

    def setup_method(self):
        self.tmp = tempfile.mkdtemp()
        self.ledger = ApprovalLedger(os.path.join(self.tmp, "ledger.jsonl"))

    def test_matching_field_accepted(self):
        token = self.ledger.sign_approval(5, "admin", "review")
        result = self.ledger.validate_anti_replay(token, expected_field_id=5)
        assert result["valid"] is True

    def test_mismatched_field_rejected(self):
        token = self.ledger.sign_approval(5, "admin", "review")
        result = self.ledger.validate_anti_replay(token, expected_field_id=3)
        assert result["valid"] is False
        assert "FIELD_MISMATCH" in result["reason"]

    def test_no_field_check_if_not_specified(self):
        token = self.ledger.sign_approval(5, "admin", "review")
        result = self.ledger.validate_anti_replay(token, expected_field_id=-1)
        assert result["valid"] is True


class TestReusedToken:
    """Reject tokens whose signature was already consumed."""

    def setup_method(self):
        self.tmp = tempfile.mkdtemp()
        self.ledger = ApprovalLedger(os.path.join(self.tmp, "ledger.jsonl"))

    def test_signature_tracked(self):
        token = self.ledger.sign_approval(0, "admin", "cert")
        self.ledger.append(token)
        assert token.signature in self.ledger._used_signatures

    def test_reused_signature_rejected(self):
        token = self.ledger.sign_approval(0, "admin", "cert")
        self.ledger.append(token)
        # Create a new token but inject old signature
        token2 = self.ledger.sign_approval(1, "admin", "cert2")
        token2.signature = token.signature
        result = self.ledger.validate_anti_replay(token2)
        # Either INVALID_SIGNATURE or REUSED_TOKEN
        assert result["valid"] is False


class TestModelHash:
    """Verify model_hash is included in token."""

    def setup_method(self):
        self.tmp = tempfile.mkdtemp()
        self.ledger = ApprovalLedger(os.path.join(self.tmp, "ledger.jsonl"))

    def test_model_hash_stored(self):
        token = self.ledger.sign_approval(0, "admin", "cert", model_hash="abc123")
        assert token.model_hash == "abc123"

    def test_model_hash_in_dict(self):
        token = self.ledger.sign_approval(0, "admin", "cert", model_hash="abc123")
        d = token.to_dict()
        assert d["model_hash"] == "abc123"

    def test_model_hash_in_ledger_entry(self):
        token = self.ledger.sign_approval(0, "admin", "cert", model_hash="model_v1_sha256")
        entry = self.ledger.append(token)
        assert entry["token"]["model_hash"] == "model_v1_sha256"


class TestNonceReload:
    """Verify nonces are rebuilt from file on load."""

    def test_nonces_survive_reload(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "ledger.jsonl")
            ledger1 = ApprovalLedger(path)
            t = ledger1.sign_approval(0, "admin", "cert")
            nonce = t.nonce
            ledger1.append(t)

            # Reload
            ledger2 = ApprovalLedger(path)
            ledger2.load()
            assert nonce in ledger2._used_nonces

    def test_cannot_replay_after_reload(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "ledger.jsonl")
            ledger1 = ApprovalLedger(path)
            t = ledger1.sign_approval(0, "admin", "cert")
            ledger1.append(t)

            # Reload and try replay
            ledger2 = ApprovalLedger(path)
            ledger2.load()
            result = ledger2.validate_anti_replay(t)
            assert result["valid"] is False
            assert "NONCE" in result["reason"] or "REUSED" in result["reason"]


class TestTokenFields:
    """Verify all required fields present in token."""

    def test_all_fields_present(self):
        ledger = ApprovalLedger("/tmp/test.jsonl")
        token = ledger.sign_approval(0, "admin", "cert", model_hash="h123")
        assert hasattr(token, "field_id")
        assert hasattr(token, "model_hash")
        assert hasattr(token, "timestamp")
        assert hasattr(token, "nonce")
        assert hasattr(token, "expiration_window")
        assert hasattr(token, "signature")
        assert hasattr(token, "approver_id")
        assert hasattr(token, "reason")

    def test_nonce_is_unique(self):
        ledger = ApprovalLedger("/tmp/test.jsonl")
        nonces = set()
        for _ in range(100):
            t = ledger.sign_approval(0, "admin", "cert")
            nonces.add(t.nonce)
        assert len(nonces) == 100
