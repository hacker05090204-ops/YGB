"""
Coverage boost round 8 — REAL DATA, targeting 130+ missing lines for 95%.

Targets:
  - report_generator.py: FastAPI TestClient for video start/stop/list + report CRUD (52 miss)
  - host_action_governor.py: validate_request OPEN_URL/RUN_TASK + unsupported (30 miss)
  - runtime_api.py: load_hmac_key from file, compute/validate HMAC, Flask register (26 miss)
  - report_orchestrator.py: run_tests() self-test + real create_report/assess_quality (31 miss)
  - db_safety.py: db_transaction async context + safe_db_write decorator (15 miss)
  - vault_session.py: vault_unlock session/role enforcement (12 miss)
"""

import hashlib
import json
import os
import secrets
import shutil
import sqlite3
import tempfile
import time
import asyncio
import unittest
from datetime import datetime, timezone
from unittest.mock import patch, MagicMock


# ---------------------------------------------------------------------------
# 1. report_generator.py — TestClient with real SQLite
# ---------------------------------------------------------------------------

class TestReportGeneratorTestClient(unittest.TestCase):
    """Real TestClient for report_generator video + report CRUD."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmp, "ygb_reports.db")
        conn = sqlite3.connect(self.db_path)
        conn.execute("""CREATE TABLE IF NOT EXISTS reports (
            id TEXT PRIMARY KEY, title TEXT, description TEXT, report_type TEXT,
            status TEXT, content TEXT, created_by TEXT, created_at TEXT,
            updated_at TEXT, metadata_json TEXT)""")
        conn.execute("""CREATE TABLE IF NOT EXISTS video_recordings (
            id TEXT PRIMARY KEY, report_id TEXT, filename TEXT, status TEXT,
            started_at TEXT, stopped_at TEXT, storage_path TEXT,
            duration_seconds REAL, file_size_bytes INTEGER,
            created_by TEXT, metadata_json TEXT)""")
        conn.execute("""CREATE TABLE IF NOT EXISTS report_activity_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT, user_id TEXT, action TEXT,
            detail TEXT, created_at TEXT)""")
        conn.commit()
        conn.close()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _make_app(self):
        from fastapi import FastAPI
        import backend.api.report_generator as rg
        # Reset table creation flag so tables are created on our temp DB
        rg._TABLES_CREATED = False
        app = FastAPI()
        app.include_router(rg.router)  # router already has prefix="/api/reports"

        db_path = self.db_path
        orig_get_db = rg.get_db_connection
        rg.get_db_connection = lambda: sqlite3.connect(db_path)

        # Bypass auth
        from backend.auth.auth_guard import require_auth
        app.dependency_overrides[require_auth] = lambda: {"sub": "test-user", "role": "admin"}
        return app, rg, orig_get_db

    def test_create_list_get_report(self):
        from fastapi.testclient import TestClient
        app, rg, orig = self._make_app()
        try:
            client = TestClient(app)
            # Create
            resp = client.post("/api/reports/", json={
                "title": "Test Vuln", "description": "XSS",
                "report_type": "vulnerability",
                "content": {"finding": "XSS"}, "metadata": {},
            })
            self.assertEqual(resp.status_code, 200)
            rid = resp.json()["report"]["id"]

            # List
            resp = client.get("/api/reports/")
            self.assertEqual(resp.status_code, 200)
            self.assertTrue(any(r["id"] == rid for r in resp.json()["reports"]))

            # Get single
            resp = client.get(f"/api/reports/{rid}")
            self.assertEqual(resp.status_code, 200)

            # Get content
            resp = client.get(f"/api/reports/{rid}/content")
            self.assertEqual(resp.status_code, 200)

            # Not found
            resp = client.get("/api/reports/nonexistent")
            self.assertEqual(resp.status_code, 404)
        finally:
            rg.get_db_connection = orig

    def test_video_lifecycle(self):
        from fastapi.testclient import TestClient
        app, rg, orig = self._make_app()
        try:
            with patch.dict(os.environ, {"YGB_HDD_ROOT": self.tmp}):
                client = TestClient(app)
                # Create a report first
                resp = client.post("/api/reports/", json={
                    "title": "Video Report", "description": "d",
                    "report_type": "assessment",
                })
                self.assertEqual(resp.status_code, 200)
                rid = resp.json()["report"]["id"]

                # Start recording
                resp = client.post("/api/reports/videos/start", json={
                    "report_id": rid, "filename": "rec.webm",
                })
                self.assertEqual(resp.status_code, 200)
                vid = resp.json()["recording"]["id"]

                # Stop recording
                resp = client.post(f"/api/reports/videos/{vid}/stop", json={
                    "duration_seconds": 30, "file_size_bytes": 500000,
                })
                self.assertEqual(resp.status_code, 200)
                self.assertEqual(resp.json()["recording"]["status"], "completed")

                # Stop nonexistent
                resp = client.post("/api/reports/videos/nope/stop", json={})
                self.assertEqual(resp.status_code, 404)
        finally:
            rg.get_db_connection = orig


# ---------------------------------------------------------------------------
# 2. host_action_governor.py — validate_request
# ---------------------------------------------------------------------------

class TestHostActionGovernorValidateRequest(unittest.TestCase):
    """Real validate_request tests with real sessions."""

    def _make_session(self, gov, **overrides):
        defaults = {
            "requested_by": "user-1",
            "approver_id": "admin-1",
            "reason": "test",
            "allowed_actions": ["OPEN_APP"],
            "allowed_apps": ["notepad"],
            "expiration_window_s": 300,
        }
        defaults.update(overrides)
        return gov.issue_session(**defaults)

    def test_validate_no_session_id(self):
        from backend.governance.host_action_governor import HostActionGovernor
        gov = HostActionGovernor()
        result = gov.validate_request("", "OPEN_APP", {})
        self.assertFalse(result["allowed"])
        self.assertEqual(result["reason"], "HOST_ACTION_SESSION_REQUIRED")

    def test_validate_session_not_found(self):
        from backend.governance.host_action_governor import HostActionGovernor
        gov = HostActionGovernor()
        # Issue a session to populate the ledger
        self._make_session(gov)
        result = gov.validate_request("nonexistent", "OPEN_APP", {})
        self.assertFalse(result["allowed"])

    def test_validate_action_not_approved(self):
        from backend.governance.host_action_governor import HostActionGovernor
        gov = HostActionGovernor()
        session = self._make_session(gov, allowed_actions=["OPEN_APP"])
        result = gov.validate_request(session.session_id, "OPEN_URL", {})
        self.assertFalse(result["allowed"])
        self.assertIn("NOT_APPROVED", result["reason"])

    def test_validate_open_app_unknown(self):
        from backend.governance.host_action_governor import HostActionGovernor
        gov = HostActionGovernor()
        session = self._make_session(gov)
        result = gov.validate_request(session.session_id, "OPEN_APP",
                                       {"app": "fake_app_xyz"})
        self.assertFalse(result["allowed"])
        self.assertEqual(result["reason"], "HOST_ACTION_APP_UNKNOWN")

    def test_validate_open_app_not_allowed(self):
        from backend.governance.host_action_governor import HostActionGovernor
        gov = HostActionGovernor()
        session = self._make_session(gov, allowed_apps=["notepad"])
        result = gov.validate_request(session.session_id, "OPEN_APP",
                                       {"app": "msedge"})
        # msedge is not in allowed_apps for this session
        self.assertFalse(result["allowed"])

    def test_validate_open_url_invalid_scheme(self):
        from backend.governance.host_action_governor import HostActionGovernor
        gov = HostActionGovernor()
        session = self._make_session(gov,
                                      allowed_actions=["OPEN_URL"],
                                      allowed_apps=["msedge"])
        result = gov.validate_request(session.session_id, "OPEN_URL",
                                       {"url": "ftp://bad.com"})
        self.assertFalse(result["allowed"])
        self.assertEqual(result["reason"], "HOST_ACTION_URL_INVALID")

    def test_validate_open_url_no_netloc(self):
        from backend.governance.host_action_governor import HostActionGovernor
        gov = HostActionGovernor()
        session = self._make_session(gov,
                                      allowed_actions=["OPEN_URL"],
                                      allowed_apps=["msedge"])
        result = gov.validate_request(session.session_id, "OPEN_URL",
                                       {"url": "not-a-url"})
        self.assertFalse(result["allowed"])


# ---------------------------------------------------------------------------
# 3. runtime_api.py — all HMAC tests (these 17 already pass)
# ---------------------------------------------------------------------------

class TestRuntimeAPIHMACReal(unittest.TestCase):
    """Real HMAC-SHA256 operations for runtime_api."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_load_hmac_key_from_env(self):
        import backend.api.runtime_api as rt
        with patch.dict(os.environ, {"YGB_HMAC_SECRET": "test_secret_key"}):
            key = rt.load_hmac_key()
        self.assertEqual(key, b"test_secret_key")

    def test_load_hmac_key_from_hex_env(self):
        import backend.api.runtime_api as rt
        hex_key = secrets.token_hex(32)
        with patch.dict(os.environ, {"YGB_HMAC_SECRET": hex_key}):
            key = rt.load_hmac_key()
        self.assertEqual(key, bytes.fromhex(hex_key))

    def test_load_hmac_key_missing_env_fails(self):
        import backend.api.runtime_api as rt
        with patch.dict(os.environ, {"YGB_HMAC_SECRET": ""}):
            with self.assertRaises(RuntimeError):
                rt.load_hmac_key()

    def test_compute_payload_hmac_missing_secret_fails(self):
        import backend.api.runtime_api as rt
        payload = {"schema_version": 1, "crc32": 12345, "timestamp": 1000}
        with patch.dict(os.environ, {"YGB_HMAC_SECRET": ""}):
            with self.assertRaises(RuntimeError):
                rt.compute_payload_hmac(payload)

    def test_compute_payload_hmac_real(self):
        import backend.api.runtime_api as rt
        payload = {"schema_version": 1, "crc32": 12345, "timestamp": 1000}
        with patch.dict(os.environ, {"YGB_HMAC_SECRET": "test_key_for_hmac"}):
            result = rt.compute_payload_hmac(payload)
        self.assertEqual(len(result), 64)

    def test_validate_hmac_valid(self):
        import backend.api.runtime_api as rt
        payload = {"schema_version": 1, "crc32": 999, "timestamp": 2000}
        with patch.dict(os.environ, {"YGB_HMAC_SECRET": "hmac_test_key"}):
            valid_hmac = rt.compute_payload_hmac(payload)
            payload["hmac"] = valid_hmac
            self.assertTrue(rt.validate_hmac(payload))

    def test_validate_hmac_invalid(self):
        import backend.api.runtime_api as rt
        payload = {"schema_version": 1, "crc32": 999, "timestamp": 2000,
                   "hmac": "bad_hmac_value"}
        with patch.dict(os.environ, {"YGB_HMAC_SECRET": "hmac_test_key"}):
            self.assertFalse(rt.validate_hmac(payload))

    def test_validate_hmac_missing(self):
        import backend.api.runtime_api as rt
        payload = {"schema_version": 1}
        self.assertFalse(rt.validate_hmac(payload))

    def test_save_and_load_last_seen(self):
        import backend.api.runtime_api as rt
        ts_path = os.path.join(self.tmp, "last_seen.json")
        with patch.object(rt, 'LAST_SEEN_PATH', ts_path):
            rt.save_last_seen_timestamp(123456789)
            loaded = rt.load_last_seen_timestamp()
        self.assertEqual(loaded, 123456789)

    def test_register_routes_flask(self):
        import backend.api.runtime_api as rt
        mock_app = MagicMock()
        mock_app.route = MagicMock(side_effect=lambda *a, **k: lambda f: f)
        rt.register_routes(mock_app)
        mock_app.route.assert_called()


# ---------------------------------------------------------------------------
# 4. report_orchestrator.py — full real workflow
# ---------------------------------------------------------------------------

class TestReportOrchestratorRealWorkflow(unittest.TestCase):
    """Real report orchestration using actual classes."""

    def test_run_tests_selftest(self):
        from backend.approval.report_orchestrator import run_tests
        result = run_tests()
        self.assertTrue(result)

    def test_full_workflow(self):
        from backend.approval.report_orchestrator import (
            ReportOrchestrator, Evidence, ConfidenceBand,
            ReportQuality, ApprovalStatus
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            orch = ReportOrchestrator(reports_dir=tmpdir)
            self.assertFalse(orch.auto_submit_enabled)

            ev = Evidence(
                screenshots=["s1.png", "s2.png"],
                videos=["v1.mp4"],
                poc_steps=["Step 1", "Step 2", "Step 3"],
            )
            cb = ConfidenceBand(
                confidence_pct=93.0, evidence_strength="High",
                reproducibility_pct=96.0, duplicate_risk_pct=10.0,
                scope_compliant=True,
            )
            # Positional args: title, vuln_type, severity, target,
            #                   description, impact, steps, evidence, confidence
            report = orch.create_report(
                "SQL Injection", "SQLi", "Critical", "api.example.com",
                "Auth bypass via SQLi", "Full DB access",
                ["Navigate to login", "Enter payload", "Observe"],
                ev, cb,
            )
            self.assertTrue(report.report_id.startswith("RPT-"))
            self.assertEqual(len(report.hash), 64)

            quality = orch.assess_quality(report)
            self.assertIn(quality, [ReportQuality.EXCELLENT, ReportQuality.GOOD])

            fp = orch.save_for_review(report)
            self.assertTrue(os.path.exists(fp))
            with open(fp) as f:
                saved = json.load(f)
            self.assertFalse(saved["auto_submit"])
            self.assertTrue(saved["human_review_required"])

            dec = orch.record_decision(
                report.report_id, ApprovalStatus.APPROVED, "reviewer"
            )
            self.assertEqual(dec.status, ApprovalStatus.APPROVED)

    def test_high_dup_risk_is_insufficient(self):
        from backend.approval.report_orchestrator import (
            ReportOrchestrator, Evidence, ConfidenceBand, ReportQuality
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            orch = ReportOrchestrator(reports_dir=tmpdir)
            dup_cb = ConfidenceBand(
                confidence_pct=95.0, duplicate_risk_pct=85.0,
                scope_compliant=True,
            )
            dup = orch.create_report(
                "Dup", "XSS", "Medium", "t.com",
                "t", "t", ["s"], Evidence(), dup_cb,
            )
            quality = orch.assess_quality(dup)
            self.assertEqual(quality, ReportQuality.INSUFFICIENT)


# ---------------------------------------------------------------------------
# 5. db_safety.py — async db_transaction and safe_db_write
# ---------------------------------------------------------------------------

class TestDBSafetyAsync(unittest.IsolatedAsyncioTestCase):
    """Real async db_transaction and safe_db_write tests."""

    async def test_db_transaction_commit(self):
        from backend.api.db_safety import db_transaction

        class FakeDB:
            def __init__(self):
                self.calls = []
            async def execute(self, sql):
                self.calls.append(sql)

        db = FakeDB()
        async with db_transaction(db) as conn:
            await conn.execute("INSERT INTO t VALUES (1)")
        self.assertIn("BEGIN IMMEDIATE", db.calls)
        self.assertIn("COMMIT", db.calls)

    async def test_db_transaction_rollback_on_error(self):
        from backend.api.db_safety import db_transaction

        class FakeDB:
            def __init__(self):
                self.calls = []
            async def execute(self, sql):
                self.calls.append(sql)
                if sql == "FAIL":
                    raise ValueError("Simulated failure")

        db = FakeDB()
        with self.assertRaises(ValueError):
            async with db_transaction(db) as conn:
                await conn.execute("FAIL")
        self.assertIn("ROLLBACK", db.calls)

    async def test_db_transaction_rollback_failure(self):
        from backend.api.db_safety import db_transaction

        class FakeDB:
            def __init__(self):
                self.calls = []
                self.fail_on_rollback = True
            async def execute(self, sql):
                self.calls.append(sql)
                if sql == "BAD_INSERT":
                    raise RuntimeError("insert failed")
                if sql == "ROLLBACK" and self.fail_on_rollback:
                    raise RuntimeError("rollback failed too")

        db = FakeDB()
        with self.assertRaises(RuntimeError):
            async with db_transaction(db) as conn:
                await conn.execute("BAD_INSERT")
        # Both failure paths covered

    async def test_safe_db_write_success(self):
        from backend.api.db_safety import safe_db_write

        @safe_db_write
        async def do_write(value):
            return {"written": value}

        result = await do_write("test_val")
        self.assertEqual(result["written"], "test_val")

    async def test_safe_db_write_error_logging(self):
        from backend.api.db_safety import safe_db_write

        @safe_db_write
        async def do_failing_write():
            raise RuntimeError("DB crash")

        with self.assertRaises(RuntimeError):
            await do_failing_write()


# ---------------------------------------------------------------------------
# 6. vault_session.py — vault_unlock
# ---------------------------------------------------------------------------

class TestVaultSessionReal(unittest.TestCase):
    """vault_unlock with real session/role enforcement."""

    def test_vault_unlock_no_session(self):
        from backend.api.vault_session import vault_unlock
        result = vault_unlock("password123", session_token="")
        self.assertEqual(result["status"], "unauthorized")
        self.assertIn("mandatory", result["message"])

    def test_vault_unlock_invalid_session(self):
        from backend.api.vault_session import vault_unlock
        with patch('backend.api.admin_auth.validate_session', return_value=None):
            result = vault_unlock("password", session_token="invalid-token")
        self.assertEqual(result["status"], "unauthorized")

    def test_vault_unlock_non_admin(self):
        from backend.api.vault_session import vault_unlock
        with patch('backend.api.admin_auth.validate_session',
                   return_value={"role": "viewer", "user_id": "u1"}):
            result = vault_unlock("password", session_token="valid-token")
        self.assertEqual(result["status"], "forbidden")

    def test_vault_unlock_already_unlocked(self):
        from backend.api.vault_session import vault_unlock
        with patch('backend.api.admin_auth.validate_session',
                   return_value={"role": "ADMIN", "user_id": "admin-1"}):
            with patch('backend.security.vault_kdf.is_vault_unlocked', return_value=True):
                result = vault_unlock("pw", session_token="valid-token")
        self.assertEqual(result["status"], "ok")
        self.assertIn("already", result["message"])

    def test_vault_unlock_empty_password(self):
        from backend.api.vault_session import vault_unlock
        with patch('backend.api.admin_auth.validate_session',
                   return_value={"role": "ADMIN", "user_id": "admin-1"}):
            with patch('backend.security.vault_kdf.is_vault_unlocked', return_value=False):
                result = vault_unlock("", session_token="valid-token")
        self.assertEqual(result["status"], "error")

    def test_vault_unlock_success(self):
        from backend.api.vault_session import vault_unlock
        with patch('backend.api.admin_auth.validate_session',
                   return_value={"role": "ADMIN", "user_id": "admin-1"}):
            with patch('backend.security.vault_kdf.is_vault_unlocked', return_value=False):
                with patch('backend.security.vault_kdf.unlock_vault', return_value=True):
                    result = vault_unlock("correct-pw", session_token="tok")
        self.assertEqual(result["status"], "ok")
        self.assertTrue(result["vault_unlocked"])

    def test_vault_unlock_bad_password(self):
        from backend.api.vault_session import vault_unlock
        with patch('backend.api.admin_auth.validate_session',
                   return_value={"role": "ADMIN", "user_id": "admin-1"}):
            with patch('backend.security.vault_kdf.is_vault_unlocked', return_value=False):
                with patch('backend.security.vault_kdf.unlock_vault', return_value=False):
                    result = vault_unlock("wrong-pw", session_token="tok")
        self.assertEqual(result["status"], "error")


if __name__ == "__main__":
    unittest.main()
