"""
Tests for modules at 0% coverage — bringing them into the test suite.

Covers:
  - backend.governance.device_authority (156 stmts)
  - backend.governance.governance_policy_check (36 stmts)
  - backend.governance.report_draft_assistant (39 stmts)
  - backend.governance.report_similarity (61 stmts)
  - backend.governance.audit_archive (72 stmts)
  - backend.api.training_progress (50 stmts)
  - backend.api.vault_session (44 stmts — mocked deps)
  - backend.api.report_generator (243 stmts — mocked deps)
  - backend.api.admin_auth (290 stmts — mocked deps)
  - backend.api.auth_server (246 stmts — mocked deps)
  - backend.api.fido2_auth (115 stmts — mocked deps)
"""

import json
import math
import os
import tempfile
import time
import unittest
from unittest.mock import patch, MagicMock


# =========================================================================
# GovernancePolicyCheck
# =========================================================================

class TestGovernancePolicyCheck(unittest.TestCase):
    def test_all_passed_true(self):
        from backend.governance.governance_policy_check import (
            run_policy_check, enforce_export_policy,
        )
        result = run_policy_check(
            target_in_scope=True,
            policy_accepted=True,
            no_automated_submission=True,
            human_approved=True,
            checked_by="admin",
        )
        self.assertTrue(result.all_passed)
        output = enforce_export_policy(result)
        self.assertEqual(output["status"], "approved")
        self.assertEqual(output["checked_by"], "admin")

    def test_all_passed_false_missing_target(self):
        from backend.governance.governance_policy_check import run_policy_check
        result = run_policy_check(
            target_in_scope=False,
            policy_accepted=True,
            no_automated_submission=True,
            human_approved=True,
            checked_by="admin",
        )
        self.assertFalse(result.all_passed)

    def test_enforce_raises_on_failure(self):
        from backend.governance.governance_policy_check import (
            run_policy_check, enforce_export_policy,
        )
        result = run_policy_check(
            target_in_scope=False,
            policy_accepted=False,
            no_automated_submission=False,
            human_approved=False,
            checked_by="test",
        )
        with self.assertRaises(PermissionError) as ctx:
            enforce_export_policy(result)
        msg = str(ctx.exception)
        self.assertIn("target_not_in_scope", msg)
        self.assertIn("policy_not_accepted", msg)
        self.assertIn("automated_submission_detected", msg)
        self.assertIn("human_approval_missing", msg)

    def test_to_dict(self):
        from backend.governance.governance_policy_check import PolicyCheckResult
        result = PolicyCheckResult()
        d = result.to_dict()
        self.assertIn("all_passed", d)
        self.assertIn("checked_at", d)
        self.assertFalse(d["all_passed"])

    def test_partial_failures(self):
        from backend.governance.governance_policy_check import (
            run_policy_check, enforce_export_policy,
        )
        result = run_policy_check(True, True, True, False, "reviewer")
        self.assertFalse(result.all_passed)
        with self.assertRaises(PermissionError) as ctx:
            enforce_export_policy(result)
        self.assertIn("human_approval_missing", str(ctx.exception))


# =========================================================================
# ReportDraftAssistant
# =========================================================================

class TestReportDraftAssistant(unittest.TestCase):
    def test_requires_manual_submit_flag(self):
        from backend.governance.report_draft_assistant import REQUIRES_MANUAL_SUBMIT
        self.assertTrue(REQUIRES_MANUAL_SUBMIT)

    def test_create_draft(self):
        from backend.governance.report_draft_assistant import create_draft
        draft = create_draft(
            target_id="target-1", summary="XSS in search",
            impact="Cookie theft", reproduction_steps="1. Go to search",
            evidence="screenshot.png", suggested_fix="Sanitize input",
            severity="high",
        )
        self.assertEqual(draft.target_id, "target-1")
        self.assertEqual(draft.severity, "high")
        self.assertTrue(draft.requires_manual_submit)
        self.assertFalse(draft.is_export_allowed())

    def test_approve_and_export(self):
        from backend.governance.report_draft_assistant import create_draft, export_draft
        draft = create_draft("t1", "sum", "impact", "steps", "ev", "fix")
        draft.approve("SecurityReviewer")
        self.assertTrue(draft.is_export_allowed())
        result = export_draft(draft)
        self.assertEqual(result["approved_by"], "SecurityReviewer")
        self.assertTrue(result["export_allowed"])

    def test_export_blocked_without_approval(self):
        from backend.governance.report_draft_assistant import create_draft, export_draft
        draft = create_draft("t1", "sum", "impact", "steps", "ev", "fix")
        with self.assertRaises(PermissionError):
            export_draft(draft)

    def test_to_dict(self):
        from backend.governance.report_draft_assistant import create_draft
        draft = create_draft("t1", "sum", "impact", "steps", "ev", "fix")
        d = draft.to_dict()
        self.assertIn("summary", d)
        self.assertIn("export_allowed", d)
        self.assertFalse(d["export_allowed"])


# =========================================================================
# ReportSimilarity
# =========================================================================

class TestReportSimilarity(unittest.TestCase):
    def test_tokenize(self):
        from backend.governance.report_similarity import tokenize
        tokens = tokenize("Hello, World! Test-123.")
        self.assertIn("hello", tokens)
        self.assertIn("world", tokens)
        self.assertIn("test", tokens)
        self.assertIn("123", tokens)

    def test_compute_tf(self):
        from backend.governance.report_similarity import compute_tf
        tf = compute_tf(["a", "b", "a"])
        self.assertAlmostEqual(tf["a"], 2 / 3)
        self.assertAlmostEqual(tf["b"], 1 / 3)

    def test_compute_tf_empty(self):
        from backend.governance.report_similarity import compute_tf
        tf = compute_tf([])
        self.assertEqual(tf, {})

    def test_compute_idf(self):
        from backend.governance.report_similarity import compute_idf
        corpus = [["a", "b"], ["b", "c"]]
        idf = compute_idf(corpus)
        self.assertIn("a", idf)
        self.assertIn("b", idf)

    def test_cosine_similarity_identical(self):
        from backend.governance.report_similarity import cosine_similarity
        vec = [1.0, 2.0, 3.0]
        sim = cosine_similarity(vec, vec)
        self.assertAlmostEqual(sim, 1.0, places=5)

    def test_cosine_similarity_orthogonal(self):
        from backend.governance.report_similarity import cosine_similarity
        sim = cosine_similarity([1.0, 0.0], [0.0, 1.0])
        self.assertAlmostEqual(sim, 0.0, places=5)

    def test_cosine_similarity_zero_vector(self):
        from backend.governance.report_similarity import cosine_similarity
        sim = cosine_similarity([0.0, 0.0], [1.0, 1.0])
        self.assertEqual(sim, 0.0)

    def test_check_report_similarity_empty(self):
        from backend.governance.report_similarity import check_report_similarity
        result = check_report_similarity("new report", [])
        self.assertEqual(result, [])

    def test_check_report_similarity_no_match(self):
        from backend.governance.report_similarity import check_report_similarity
        result = check_report_similarity(
            "SQL injection in login form authentication bypass",
            ["Cross-site scripting vulnerability in search widget rendering engine"],
            threshold=0.95,
        )
        # These are different enough
        self.assertEqual(len(result), 0)

    def test_check_report_similarity_match(self):
        from backend.governance.report_similarity import check_report_similarity
        report = "SQL injection in login form allows authentication bypass"
        existing = [report]
        result = check_report_similarity(report, existing, threshold=0.5)
        self.assertGreater(len(result), 0)
        self.assertGreater(result[0][1], 0.5)

    def test_log_potential_duplicate(self):
        from backend.governance.report_similarity import log_potential_duplicate
        tmpdir = tempfile.mkdtemp()
        log_path = os.path.join(tmpdir, "dupes.json")
        with patch("backend.governance.report_similarity.SIMILARITY_LOG", log_path):
            log_potential_duplicate("RPT-1", "RPT-2", 0.95)
            self.assertTrue(os.path.exists(log_path))
            with open(log_path) as f:
                data = json.load(f)
            self.assertEqual(len(data), 1)
            self.assertEqual(data[0]["similarity"], 0.95)

    def test_log_potential_duplicate_existing_file(self):
        from backend.governance.report_similarity import log_potential_duplicate
        tmpdir = tempfile.mkdtemp()
        log_path = os.path.join(tmpdir, "dupes.json")
        with open(log_path, "w") as f:
            json.dump([{"existing": True}], f)
        with patch("backend.governance.report_similarity.SIMILARITY_LOG", log_path):
            log_potential_duplicate("RPT-3", "RPT-4", 0.88)
            with open(log_path) as f:
                data = json.load(f)
            self.assertEqual(len(data), 2)


# =========================================================================
# DeviceAuthority
# =========================================================================

class TestDeviceAuthority(unittest.TestCase):
    def test_load_whitelist_no_file(self):
        from backend.governance.device_authority import load_whitelist
        with patch("backend.governance.device_authority.WHITELIST_PATH", "/nonexistent"):
            result = load_whitelist()
            self.assertEqual(result, [])

    def test_load_whitelist_with_data(self):
        from backend.governance.device_authority import load_whitelist
        tmpdir = tempfile.mkdtemp()
        path = os.path.join(tmpdir, "whitelist.json")
        with open(path, "w") as f:
            json.dump({"trusted_devices": [{"device_id": "dev1"}]}, f)
        with patch("backend.governance.device_authority.WHITELIST_PATH", path):
            result = load_whitelist()
            self.assertEqual(len(result), 1)

    def test_is_whitelisted(self):
        from backend.governance.device_authority import is_whitelisted
        tmpdir = tempfile.mkdtemp()
        path = os.path.join(tmpdir, "whitelist.json")
        with open(path, "w") as f:
            json.dump({"trusted_devices": [{"device_id": "dev1"}]}, f)
        with patch("backend.governance.device_authority.WHITELIST_PATH", path):
            self.assertTrue(is_whitelisted("dev1"))
            self.assertFalse(is_whitelisted("unknown"))

    def test_load_revocation_list_no_file(self):
        from backend.governance.device_authority import load_revocation_list
        with patch("backend.governance.device_authority.REVOCATION_PATH", "/nonexistent"):
            result = load_revocation_list()
            self.assertEqual(result, [])

    def test_is_revoked(self):
        from backend.governance.device_authority import is_revoked
        tmpdir = tempfile.mkdtemp()
        path = os.path.join(tmpdir, "revoked.json")
        with open(path, "w") as f:
            json.dump({"revoked_devices": ["baddev"]}, f)
        with patch("backend.governance.device_authority.REVOCATION_PATH", path):
            self.assertTrue(is_revoked("baddev"))
            self.assertFalse(is_revoked("gooddev"))

    def test_revoke_device(self):
        from backend.governance.device_authority import revoke_device
        tmpdir = tempfile.mkdtemp()
        rev_path = os.path.join(tmpdir, "revoked.json")
        cert_dir = os.path.join(tmpdir, "certs")
        with patch("backend.governance.device_authority.REVOCATION_PATH", rev_path), \
             patch("backend.governance.device_authority.CERT_DIR", cert_dir):
            result = revoke_device("dev-to-revoke")
            self.assertTrue(result)
            with open(rev_path) as f:
                data = json.load(f)
            self.assertIn("dev-to-revoke", data["revoked_devices"])

    def test_generate_and_verify_otp(self):
        from backend.governance.device_authority import generate_otp, verify_otp, _pending_otps
        _pending_otps.clear()
        otp = generate_otp("testdev")
        self.assertEqual(len(otp), 6)
        self.assertTrue(verify_otp("testdev", otp))
        # Should be consumed
        self.assertFalse(verify_otp("testdev", otp))

    def test_verify_otp_wrong(self):
        from backend.governance.device_authority import generate_otp, verify_otp, _pending_otps
        _pending_otps.clear()
        generate_otp("testdev2")
        self.assertFalse(verify_otp("testdev2", "000000"))

    def test_verify_otp_expired(self):
        from backend.governance.device_authority import generate_otp, verify_otp, _pending_otps
        _pending_otps.clear()
        otp = generate_otp("testdev3")
        # Simulate expiry
        _pending_otps["testdev3"]["expires_at"] = time.time() - 1
        self.assertFalse(verify_otp("testdev3", otp))

    def test_verify_otp_unknown_device(self):
        from backend.governance.device_authority import verify_otp
        self.assertFalse(verify_otp("unknown_device_xyz", "123456"))

    def test_sign_certificate(self):
        from backend.governance.device_authority import sign_certificate
        cert = {"device_id": "dev1", "role": "WORKER"}
        with patch.dict(os.environ, {"YGB_AUTHORITY_SECRET": "test-secret"}):
            sig = sign_certificate(cert)
            self.assertEqual(len(sig), 64)

    def test_sign_certificate_fallback_hmac(self):
        from backend.governance.device_authority import sign_certificate
        cert = {"device_id": "dev1"}
        with patch.dict(os.environ, {"YGB_AUTHORITY_SECRET": "", "YGB_HMAC_SECRET": "hmac-key"}):
            sig = sign_certificate(cert)
            self.assertEqual(len(sig), 64)

    def test_sign_certificate_no_key_raises(self):
        from backend.governance.device_authority import sign_certificate
        with patch.dict(os.environ, {"YGB_AUTHORITY_SECRET": "", "YGB_HMAC_SECRET": ""}, clear=False):
            with self.assertRaises(RuntimeError):
                sign_certificate({"device_id": "dev1"})

    def test_issue_certificate(self):
        from backend.governance.device_authority import issue_certificate
        with patch.dict(os.environ, {"YGB_AUTHORITY_SECRET": "test-key"}):
            cert = issue_certificate("dev1", "WORKER", "pubkey", "10.0.0.5")
            self.assertEqual(cert["device_id"], "dev1")
            self.assertIn("signature", cert)
            self.assertIn("expires_at", cert)

    def test_assign_mesh_ip(self):
        from backend.governance.device_authority import _assign_mesh_ip
        ip = _assign_mesh_ip("test-device")
        self.assertTrue(ip.startswith("10.0.0."))
        parts = ip.split(".")
        host = int(parts[3])
        self.assertGreaterEqual(host, 2)
        self.assertLessEqual(host, 254)

    def test_load_pairing_request_not_found(self):
        from backend.governance.device_authority import load_pairing_request
        with patch("backend.governance.device_authority.PAIRING_DIR", "/nonexistent"):
            self.assertIsNone(load_pairing_request("dev1"))

    def test_list_pending_requests_no_dir(self):
        from backend.governance.device_authority import list_pending_requests
        with patch("backend.governance.device_authority.PAIRING_DIR", "/nonexistent"):
            result = list_pending_requests()
            self.assertEqual(result, [])

    def test_list_pending_requests(self):
        from backend.governance.device_authority import list_pending_requests
        tmpdir = tempfile.mkdtemp()
        pair_dir = os.path.join(tmpdir, "pairing")
        os.makedirs(pair_dir)
        with open(os.path.join(pair_dir, "dev1.json"), "w") as f:
            json.dump({"status": "pending", "device_id": "dev1"}, f)
        with open(os.path.join(pair_dir, "dev2.json"), "w") as f:
            json.dump({"status": "approved", "device_id": "dev2"}, f)
        with patch("backend.governance.device_authority.PAIRING_DIR", pair_dir):
            result = list_pending_requests()
            self.assertEqual(len(result), 1)
            self.assertEqual(result[0]["device_id"], "dev1")

    def test_process_pairing_revoked(self):
        from backend.governance.device_authority import process_pairing_request
        tmpdir = tempfile.mkdtemp()
        rev_path = os.path.join(tmpdir, "revoked.json")
        with open(rev_path, "w") as f:
            json.dump({"revoked_devices": ["bad-dev"]}, f)
        with patch("backend.governance.device_authority.REVOCATION_PATH", rev_path):
            result = process_pairing_request("bad-dev")
            self.assertEqual(result["status"], "denied")

    def test_process_pairing_no_request(self):
        from backend.governance.device_authority import process_pairing_request
        with patch("backend.governance.device_authority.REVOCATION_PATH", "/nonexistent"), \
             patch("backend.governance.device_authority.PAIRING_DIR", "/nonexistent"):
            result = process_pairing_request("dev-none")
            self.assertEqual(result["status"], "error")

    def test_process_pairing_generates_otp(self):
        from backend.governance.device_authority import process_pairing_request, _pending_otps
        _pending_otps.clear()
        tmpdir = tempfile.mkdtemp()
        pair_dir = os.path.join(tmpdir, "pairing")
        os.makedirs(pair_dir)
        with open(os.path.join(pair_dir, "newdev.json"), "w") as f:
            json.dump({"status": "pending", "requested_role": "WORKER", "public_key": "pk"}, f)
        with patch("backend.governance.device_authority.REVOCATION_PATH", "/nonexistent"), \
             patch("backend.governance.device_authority.WHITELIST_PATH", "/nonexistent"), \
             patch("backend.governance.device_authority.PAIRING_DIR", pair_dir):
            result = process_pairing_request("newdev")
            self.assertEqual(result["status"], "pending_approval")
            self.assertIn("otp", result)

    def test_save_certificate(self):
        from backend.governance.device_authority import save_certificate
        tmpdir = tempfile.mkdtemp()
        cert_dir = os.path.join(tmpdir, "certs")
        with patch("backend.governance.device_authority.CERT_DIR", cert_dir):
            cert = {"device_id": "dev1", "signature": "abc"}
            path = save_certificate(cert, "dev1")
            self.assertTrue(os.path.exists(path))

    def test_update_request_status(self):
        from backend.governance.device_authority import _update_request_status
        tmpdir = tempfile.mkdtemp()
        pair_dir = os.path.join(tmpdir, "pairing")
        os.makedirs(pair_dir)
        path = os.path.join(pair_dir, "dev1.json")
        with open(path, "w") as f:
            json.dump({"status": "pending"}, f)
        with patch("backend.governance.device_authority.PAIRING_DIR", pair_dir):
            _update_request_status("dev1", "approved")
            with open(path) as f:
                data = json.load(f)
            self.assertEqual(data["status"], "approved")


# =========================================================================
# AuditArchive
# =========================================================================

class TestAuditArchive(unittest.TestCase):
    def test_strip_payloads(self):
        from backend.governance.audit_archive import strip_payloads
        report = {
            "target_id": "target-1",
            "severity": "critical",
            "status": "closed",
            "exploit_code": "DROP TABLE users",
            "timestamp": 1234567890,
        }
        safe = strip_payloads(report)
        self.assertIn("report_hash", safe)
        self.assertEqual(len(safe["report_hash"]), 64)
        self.assertEqual(safe["target"], "target-1")
        self.assertNotIn("exploit_code", safe)

    def test_get_or_create_key(self):
        from backend.governance.audit_archive import get_or_create_archive_key
        tmpdir = tempfile.mkdtemp()
        key_path = os.path.join(tmpdir, "test_key.key")
        with patch("backend.governance.audit_archive.ARCHIVE_KEY_PATH", key_path), \
             patch("backend.governance.audit_archive.ARCHIVE_DIR", os.path.join(tmpdir, "archived")), \
             patch("backend.governance.audit_archive.CONFIG_DIR", tmpdir):
            key1 = get_or_create_archive_key()
            self.assertEqual(len(key1), 32)
            key2 = get_or_create_archive_key()
            self.assertEqual(key1, key2)

    def test_aes_encrypt_decrypt(self):
        try:
            from backend.governance.audit_archive import aes_encrypt, aes_decrypt
            key = os.urandom(32)
            data = b"Hello, World! This is secret data."
            encrypted = aes_encrypt(data, key)
            self.assertNotEqual(encrypted, data)
            decrypted = aes_decrypt(encrypted, key)
            self.assertEqual(decrypted, data)
        except RuntimeError:
            # PyCryptodome not installed — verify the error message
            from backend.governance.audit_archive import aes_encrypt
            try:
                aes_encrypt(b"test", os.urandom(32))
                self.fail("Should have raised RuntimeError")
            except RuntimeError as e:
                self.assertIn("pycryptodome", str(e))

    def test_archive_and_read(self):
        from backend.governance.audit_archive import archive_report, read_archived_report
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("backend.governance.audit_archive.ARCHIVE_DIR", os.path.join(tmpdir, "archived")), \
                 patch("backend.governance.audit_archive.CONFIG_DIR", tmpdir), \
                 patch("backend.governance.audit_archive.ARCHIVE_KEY_PATH", os.path.join(tmpdir, "key.key")):
                report = {"target_id": "tgt", "severity": "high", "status": "closed"}
                try:
                    path = archive_report(report, "RPT-001")
                except RuntimeError as exc:
                    if "pycryptodome" not in str(exc).lower():
                        raise
                    self.skipTest(f"PyCryptodome unavailable: {exc}")
                self.assertTrue(os.path.exists(path))
                restored = read_archived_report("RPT-001")
                self.assertIsNotNone(restored)
                self.assertIn("report_hash", restored)

    def test_read_archived_not_found(self):
        from backend.governance.audit_archive import read_archived_report
        tmpdir = tempfile.mkdtemp()
        with patch("backend.governance.audit_archive.ARCHIVE_DIR", tmpdir):
            self.assertIsNone(read_archived_report("nonexistent"))


# =========================================================================
# TrainingProgress
# =========================================================================

class TestTrainingProgress(unittest.TestCase):
    def test_no_telemetry_file(self):
        from backend.api.training_progress import get_training_progress
        with patch("backend.api.training_progress.TELEMETRY_PATH", "/nonexistent"):
            result = get_training_progress()
            self.assertEqual(result["status"], "awaiting_data")
            self.assertFalse(result["stalled"])

    def test_valid_telemetry(self):
        from backend.api.training_progress import get_training_progress
        tmpdir = tempfile.mkdtemp()
        path = os.path.join(tmpdir, "telemetry.json")
        now = time.time()
        with open(path, "w") as f:
            json.dump({
                "wall_clock_unix": now,
                "monotonic_start_time": 1000,
                "monotonic_timestamp": 2000,
                "training_duration_seconds": 3661,
                "samples_per_second": 42.5,
                "epoch": 3,
                "loss": 0.05,
                "gpu_temperature": 72.5,
            }, f)
        with patch("backend.api.training_progress.TELEMETRY_PATH", path):
            result = get_training_progress()
            self.assertEqual(result["status"], "training")
            self.assertEqual(result["epoch"], 3)
            self.assertEqual(result["elapsed"], "01:01:01")
            self.assertFalse(result["stalled"])

    def test_stalled_detection(self):
        from backend.api.training_progress import get_training_progress
        tmpdir = tempfile.mkdtemp()
        path = os.path.join(tmpdir, "telemetry.json")
        with open(path, "w") as f:
            json.dump({
                "wall_clock_unix": time.time() - 120,
                "training_duration_seconds": 100,
            }, f)
        # Set file mtime to 2 minutes ago
        old_time = time.time() - 120
        os.utime(path, (old_time, old_time))
        with patch("backend.api.training_progress.TELEMETRY_PATH", path):
            result = get_training_progress()
            self.assertTrue(result["stalled"])

    def test_invalid_json(self):
        from backend.api.training_progress import get_training_progress
        tmpdir = tempfile.mkdtemp()
        path = os.path.join(tmpdir, "bad.json")
        with open(path, "w") as f:
            f.write("NOT JSON")
        with patch("backend.api.training_progress.TELEMETRY_PATH", path):
            result = get_training_progress()
            self.assertEqual(result["status"], "error")


# =========================================================================
# VaultSession (mocked — has external deps)
# =========================================================================

class TestVaultSession(unittest.TestCase):
    def test_vault_unlock_no_session(self):
        from backend.api.vault_session import vault_unlock
        result = vault_unlock("password123", session_token="", ip="127.0.0.1")
        self.assertEqual(result["status"], "unauthorized")

    def test_vault_lock(self):
        from backend.api.vault_session import vault_lock
        with patch("backend.security.vault_kdf.lock_vault"):
            result = vault_lock(session_token="tok", ip="127.0.0.1")
            self.assertEqual(result["status"], "ok")
            self.assertFalse(result["vault_unlocked"])

    def test_vault_status(self):
        from backend.api.vault_session import vault_status
        with patch("backend.security.vault_kdf.is_vault_unlocked", return_value=False):
            result = vault_status()
            self.assertEqual(result["status"], "ok")
            self.assertFalse(result["vault_unlocked"])

    def test_vault_unlock_invalid_session(self):
        from backend.api.vault_session import vault_unlock
        with patch("backend.api.admin_auth.validate_session", return_value=None):
            result = vault_unlock("pass", session_token="bad-tok", ip="127.0.0.1")
            self.assertEqual(result["status"], "unauthorized")

    def test_vault_unlock_non_admin(self):
        from backend.api.vault_session import vault_unlock
        with patch("backend.api.admin_auth.validate_session", return_value={"role": "viewer"}), \
             patch("backend.security.vault_kdf.is_vault_unlocked", return_value=False):
            result = vault_unlock("pass", session_token="valid", ip="127.0.0.1")
            self.assertEqual(result["status"], "forbidden")

    def test_audit_log_writes(self):
        from backend.api.vault_session import _audit_log
        tmpdir = tempfile.mkdtemp()
        audit_path = os.path.join(tmpdir, "audit.json")
        with patch("backend.api.vault_session.AUDIT_LOG_PATH", audit_path):
            _audit_log("TEST_ACTION", "127.0.0.1", "test details")
            self.assertTrue(os.path.exists(audit_path))
            with open(audit_path) as f:
                line = f.readline()
                data = json.loads(line)
                self.assertEqual(data["action"], "TEST_ACTION")


# =========================================================================
# DBSafety (async)
# =========================================================================

class TestDBSafety(unittest.TestCase):
    def test_safe_db_write_decorator(self):
        import asyncio
        from backend.api.db_safety import safe_db_write

        @safe_db_write
        async def my_write():
            return "ok"

        result = asyncio.get_event_loop().run_until_complete(my_write())
        self.assertEqual(result, "ok")

    def test_safe_db_write_raises(self):
        import asyncio
        from backend.api.db_safety import safe_db_write

        @safe_db_write
        async def my_bad_write():
            raise ValueError("DB error")

        with self.assertRaises(ValueError):
            asyncio.get_event_loop().run_until_complete(my_bad_write())

    def test_db_transaction_success(self):
        import asyncio
        from backend.api.db_safety import db_transaction

        class FakeDB:
            def __init__(self):
                self.calls = []
            async def execute(self, sql):
                self.calls.append(sql)

        async def run():
            db = FakeDB()
            async with db_transaction(db) as conn:
                await conn.execute("INSERT INTO t VALUES (1)")
            return db.calls

        calls = asyncio.get_event_loop().run_until_complete(run())
        self.assertIn("BEGIN IMMEDIATE", calls)
        self.assertIn("COMMIT", calls)

    def test_db_transaction_rollback(self):
        import asyncio
        from backend.api.db_safety import db_transaction

        class FakeDB:
            def __init__(self):
                self.calls = []
            async def execute(self, sql):
                self.calls.append(sql)
                if sql.startswith("INSERT"):
                    raise ValueError("Insert failed")

        async def run():
            db = FakeDB()
            caught = None
            try:
                async with db_transaction(db) as conn:
                    await conn.execute("INSERT INTO t VALUES (1)")
            except ValueError as exc:
                caught = exc
            self.assertIsNotNone(caught)
            self.assertEqual(str(caught), "Insert failed")
            return db.calls

        calls = asyncio.get_event_loop().run_until_complete(run())
        self.assertIn("BEGIN IMMEDIATE", calls)
        self.assertIn("ROLLBACK", calls)


# =========================================================================
# SystemStatus (mocked — has external deps)
# =========================================================================

class TestSystemStatus(unittest.TestCase):
    def test_safe_call_success(self):
        from backend.api.system_status import _safe_call
        result = _safe_call("test", lambda: {"status": "ok"})
        self.assertEqual(result["status"], "ok")

    def test_safe_call_failure(self):
        from backend.api.system_status import _safe_call
        def failing_fn():
            raise RuntimeError("boom")
        result = _safe_call("test", failing_fn)
        self.assertEqual(result["status"], "UNAVAILABLE")
        self.assertIn("boom", result["error"])


if __name__ == "__main__":
    unittest.main()
