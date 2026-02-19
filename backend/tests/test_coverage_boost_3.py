"""
test_coverage_boost_3.py — Final targeted tests to reach 95%

Covers remaining uncovered lines in:
  - approval_ledger.py: ApprovalToken.from_dict, key_missing,
    reused_token, expired_token, chain hash mismatch, load empty,
    POSIX permission path
  - integrity_bridge.py: record_batch, imbalance_ratio edge,
    governance reader error, storage warning path
"""

import hashlib
import json
import os
import sys
import tempfile
import time
import unittest

import numpy as np

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.insert(0, os.path.join(PROJECT_ROOT, 'backend'))


# =========================================================================
# APPROVAL LEDGER — Remaining uncovered lines
# =========================================================================

class TestApprovalTokenFromDict(unittest.TestCase):
    """Cover ApprovalToken.from_dict classmethod (line 235)."""

    def test_from_dict(self):
        from governance.approval_ledger import ApprovalToken
        d = {
            "field_id": 0,
            "approver_id": "admin",
            "reason": "certified",
            "timestamp": time.time(),
            "signature": "abc123",
            "nonce": "nonce1",
            "key_id": "key1",
        }
        token = ApprovalToken.from_dict(d)
        self.assertEqual(token.field_id, 0)
        self.assertEqual(token.approver_id, "admin")
        self.assertEqual(token.signature, "abc123")


class TestApprovalLedgerEdgePaths(unittest.TestCase):
    """Cover key_missing, reused token, expired token, chain mismatch."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.ledger_path = os.path.join(self.tmpdir, "test_ledger.jsonl")

    def test_get_signing_key_missing(self):
        """Cover line 167: raise ValueError for missing key."""
        from governance.approval_ledger import ApprovalLedger, KeyManager
        km = KeyManager()
        km._keys.clear()  # Remove all keys
        ledger = ApprovalLedger(self.ledger_path, key_manager=km)
        with self.assertRaises(ValueError):
            ledger._key_mgr.get_signing_key()

    def test_validate_reused_signature(self):
        """Cover line 335: REUSED_TOKEN check."""
        from governance.approval_ledger import ApprovalLedger
        ledger = ApprovalLedger(self.ledger_path)
        token = ledger.sign_approval(0, "admin", "test")
        # Pre-add signature to used set
        ledger._used_signatures.add(token.signature)
        result = ledger.validate_anti_replay(token)
        self.assertFalse(result["valid"])
        # Reason could be REUSED_TOKEN or DUPLICATE_NONCE
        self.assertIn(result["reason"], ("REUSED_TOKEN", "DUPLICATE_NONCE"))

    def test_validate_expired_token(self):
        """Cover line ~345: expired token check."""
        from governance.approval_ledger import ApprovalLedger, ApprovalToken
        ledger = ApprovalLedger(self.ledger_path)
        # Create a token manually with very old timestamp
        key_id, secret = ledger._key_mgr.get_signing_key()
        token = ApprovalToken(
            field_id=0, approver_id="admin", reason="test",
            timestamp=time.time() - 100000,  # very old
            signature="sig_expired",
            nonce="nonce_exp", key_id=key_id,
            expiration_window=3600.0,
        )
        result = ledger.validate_anti_replay(token)
        self.assertFalse(result["valid"])

    def test_verify_chain_tampered(self):
        """Cover line 396: prev_hash mismatch in chain verification."""
        from governance.approval_ledger import ApprovalLedger
        ledger = ApprovalLedger(self.ledger_path)
        # Add a legitimate entry
        token = ledger.sign_approval(0, "admin", "test reason")
        ledger.append(token)
        # Tamper with the stored entry's prev_hash
        if ledger._entries:
            ledger._entries[0]["prev_hash"] = "tampered" * 8
        result = ledger.verify_chain()
        self.assertFalse(result)

    def test_load_nonexistent_path(self):
        """Cover line 449: load() when file doesn't exist."""
        from governance.approval_ledger import ApprovalLedger
        path = os.path.join(self.tmpdir, "nonexistent_ledger.jsonl")
        ledger = ApprovalLedger(path)
        ledger.load()
        self.assertEqual(len(ledger._entries), 0)

    def test_load_existing_file(self):
        """Cover load() with an existing file."""
        from governance.approval_ledger import ApprovalLedger
        ledger = ApprovalLedger(self.ledger_path)
        token = ledger.sign_approval(0, "admin", "test")
        ledger.append(token)
        # Create new ledger and load
        ledger2 = ApprovalLedger(self.ledger_path)
        ledger2.load()
        self.assertEqual(len(ledger2._entries), 1)


class TestApprovalLedgerKeyDir(unittest.TestCase):
    """Cover key loading from YGB_KEY_DIR (lines 70-77, 105-109, 146)."""

    def test_key_loading_fallback_env(self):
        """Cover line 146: key fallback to env var."""
        from governance.approval_ledger import ApprovalLedger, KeyManager
        tmpdir = tempfile.mkdtemp()
        path = os.path.join(tmpdir, "ledger.jsonl")
        # With no YGB_KEY_DIR set, should use fallback
        old_env = os.environ.get("YGB_KEY_DIR")
        try:
            if "YGB_KEY_DIR" in os.environ:
                del os.environ["YGB_KEY_DIR"]
            km = KeyManager()
            ledger = ApprovalLedger(path, key_manager=km)
            # Should still have a default key
            key_id, key = km.get_signing_key()
            self.assertTrue(len(key) > 0)
        finally:
            if old_env:
                os.environ["YGB_KEY_DIR"] = old_env

    def test_key_loading_with_key_dir(self):
        """Cover lines 70-77 and 105-109: load keys from dir."""
        from governance.approval_ledger import ApprovalLedger, KeyManager
        tmpdir = tempfile.mkdtemp()
        key_dir = os.path.join(tmpdir, "keys")
        os.makedirs(key_dir)
        # Create a key file
        key_path = os.path.join(key_dir, "test_key.key")
        with open(key_path, "wb") as f:
            f.write(b"test-secret-key-data-here")

        ledger_path = os.path.join(tmpdir, "ledger.jsonl")
        old_env = os.environ.get("YGB_KEY_DIR")
        try:
            os.environ["YGB_KEY_DIR"] = key_dir
            km = KeyManager()
            ledger = ApprovalLedger(ledger_path, key_manager=km)
            # Should have loaded key from dir
            self.assertTrue(len(km._keys) >= 1)
        finally:
            if old_env:
                os.environ["YGB_KEY_DIR"] = old_env
            elif "YGB_KEY_DIR" in os.environ:
                del os.environ["YGB_KEY_DIR"]


# =========================================================================
# INTEGRITY BRIDGE — Remaining uncovered lines
# =========================================================================

class TestDatasetWatchdogBatch(unittest.TestCase):
    """Cover record_batch (lines 262-263)."""

    def test_record_batch(self):
        from integrity.integrity_bridge import DatasetIntegrityWatchdog
        w = DatasetIntegrityWatchdog(n_classes=2)
        labels = np.array([0, 1, 0, 1])
        features = np.random.rand(4, 5)
        w.record_batch(labels, features)
        self.assertEqual(w.total_samples, 4)

    def test_imbalance_ratio_single_class(self):
        """Cover line 267: n_classes <= 1."""
        from integrity.integrity_bridge import DatasetIntegrityWatchdog
        w = DatasetIntegrityWatchdog(n_classes=1)
        self.assertEqual(w.compute_imbalance_ratio(), 1.0)


class TestGovernanceReaderError(unittest.TestCase):
    """Cover lines 422-423: governance reader error path."""

    def test_read_nonexistent_state(self):
        from integrity.integrity_bridge import GovernanceIntegrityReader
        from pathlib import Path
        reader = GovernanceIntegrityReader(
            state_path=Path("/nonexistent/path/state.json")
        )
        state = reader.read_state()
        self.assertFalse(state["auto_mode_safe"])

    def test_compute_score_no_data(self):
        from integrity.integrity_bridge import GovernanceIntegrityReader
        from pathlib import Path
        reader = GovernanceIntegrityReader(
            state_path=Path("/nonexistent/path/state.json")
        )
        score, details = reader.compute_score()
        self.assertEqual(score, 0.0)
        self.assertEqual(details["reason"], "no_governance_data")


class TestAutonomyStorageWarning(unittest.TestCase):
    """Cover line 680: storage_warning_active in _evaluate_autonomy."""

    def test_storage_warning_blocks_shadow(self):
        from integrity.integrity_bridge import SystemIntegritySupervisor
        sup = SystemIntegritySupervisor()
        ds_stats = sup.dataset_watchdog.get_stats()
        result = sup._evaluate_autonomy(
            overall=99.0, ml_score=100.0,
            dataset_score=100.0, storage_score=50.0,  # below 90
            ds_stats=ds_stats,
        )
        self.assertFalse(result["shadow_allowed"])
        self.assertIn("storage_warning_active", result["blocked_reasons"])


class TestScoreToStatus(unittest.TestCase):
    """Cover _score_to_status."""

    def test_green(self):
        from integrity.integrity_bridge import _score_to_status
        self.assertEqual(_score_to_status(95.0), "GREEN")

    def test_yellow(self):
        from integrity.integrity_bridge import _score_to_status
        self.assertEqual(_score_to_status(75.0), "YELLOW")

    def test_red(self):
        from integrity.integrity_bridge import _score_to_status
        self.assertEqual(_score_to_status(50.0), "RED")


if __name__ == "__main__":
    unittest.main()
