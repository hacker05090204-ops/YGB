"""
Coverage boost round 2 — targeting the remaining gaps to reach 85%.

Modules covered:
  - backend.api.field_progression_api (71% → ~90%)
  - backend.api.runtime_api (74% → ~90%)
  - backend.api.report_generator (28% → ~60%)
  - backend.auth.revocation_store (69% → ~85%)
  - backend.auth.auth (69% → ~85%)
"""

import hashlib
import hmac
import json
import os
import secrets
import struct
import sys
import tempfile
import time
import unittest
from pathlib import Path
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch, mock_open


# ---------------------------------------------------------------------------
# 1. field_progression_api.py — Pure function tests (~93 missing lines)
# ---------------------------------------------------------------------------

class TestFieldProgressionDefaults(unittest.TestCase):
    """Tests for _default_state and constants."""

    def test_default_state_structure(self):
        from backend.api.field_progression_api import _default_state, TOTAL_FIELDS
        state = _default_state()
        self.assertEqual(state["active_field_id"], 0)
        self.assertEqual(state["certified_count"], 0)
        self.assertEqual(state["total_fields"], TOTAL_FIELDS)
        self.assertEqual(len(state["fields"]), TOTAL_FIELDS)
        self.assertIn("last_updated", state)

    def test_default_state_first_field_active(self):
        from backend.api.field_progression_api import _default_state
        state = _default_state()
        f0 = state["fields"][0]
        self.assertTrue(f0["active"])
        self.assertFalse(f0["locked"])
        self.assertEqual(f0["state"], "TRAINING")

    def test_default_state_other_fields_locked(self):
        from backend.api.field_progression_api import _default_state
        state = _default_state()
        for f in state["fields"][1:]:
            self.assertFalse(f["active"])
            self.assertTrue(f["locked"])
            self.assertEqual(f["state"], "NOT_STARTED")


class TestFieldProgressionProgress(unittest.TestCase):
    """Tests for _calculate_progress."""

    def test_progress_no_metrics(self):
        from backend.api.field_progression_api import _calculate_progress
        field = {"id": 0, "precision": None, "fpr": None, "dup_detection": None,
                 "ece": None, "stability_days": 0}
        result = _calculate_progress(field)
        self.assertEqual(result["metrics_available"], 1)  # stability only
        self.assertIn("Awaiting Data", result["status"])

    def test_progress_all_metrics_perfect(self):
        from backend.api.field_progression_api import _calculate_progress
        field = {"id": 0, "precision": 0.99, "fpr": 0.01, "dup_detection": 0.95,
                 "ece": 0.005, "stability_days": 10}
        result = _calculate_progress(field)
        self.assertEqual(result["metrics_available"], 5)
        self.assertGreater(result["overall_percent"], 90)

    def test_progress_partial_metrics(self):
        from backend.api.field_progression_api import _calculate_progress
        field = {"id": 1, "precision": 0.97, "fpr": None, "dup_detection": None,
                 "ece": None, "stability_days": 3}
        result = _calculate_progress(field)
        self.assertEqual(result["metrics_available"], 2)  # precision + stability
        self.assertIsNotNone(result["precision_score"])
        self.assertIsNone(result["fpr_score"])

    def test_progress_bad_fpr(self):
        from backend.api.field_progression_api import _calculate_progress
        field = {"id": 1, "precision": 0.97, "fpr": 0.10, "dup_detection": None,
                 "ece": None, "stability_days": 0}
        result = _calculate_progress(field)
        self.assertIsNotNone(result["fpr_score"])
        # FPR of 0.10 is 2x the 0.05 threshold, so score should be 0
        self.assertEqual(result["fpr_score"], 0.0)

    def test_progress_bad_ece(self):
        from backend.api.field_progression_api import _calculate_progress
        field = {"id": 1, "precision": None, "fpr": None, "dup_detection": None,
                 "ece": 0.04, "stability_days": 0}
        result = _calculate_progress(field)
        self.assertIsNotNone(result["ece_score"])
        # ECE of 0.04 == 2x the 0.02 threshold, score should be 0
        self.assertEqual(result["ece_score"], 0.0)


class TestFieldProgressionBuildRuntime(unittest.TestCase):
    """Tests for _build_runtime_status."""

    def test_runtime_no_persisted_file(self):
        from backend.api.field_progression_api import _build_runtime_status
        state = {"fields": []}
        with patch('os.path.exists', return_value=False):
            result = _build_runtime_status(state)
        self.assertFalse(result["containment_active"])
        self.assertIsNone(result["gpu_utilization"])

    def test_runtime_with_persisted_data(self):
        from backend.api.field_progression_api import _build_runtime_status
        state = {"fields": []}
        persisted = {"gpu_utilization": 0.85, "drift_alert": True}
        with patch('os.path.exists', return_value=True):
            with patch('builtins.open', mock_open(read_data=json.dumps(persisted))):
                result = _build_runtime_status(state)
        self.assertEqual(result["gpu_utilization"], 0.85)
        self.assertTrue(result["drift_alert"])

    def test_runtime_demoted_field(self):
        from backend.api.field_progression_api import _build_runtime_status
        state = {"fields": [
            {"name": "Field-1", "demoted": True},
            {"name": "Field-2", "demoted": False},
        ]}
        with patch('os.path.exists', return_value=False):
            result = _build_runtime_status(state)
        self.assertTrue(result["containment_active"])
        self.assertIn("Field-1", result["containment_reason"])

    def test_runtime_file_read_error(self):
        from backend.api.field_progression_api import _build_runtime_status
        state = {"fields": []}
        with patch('os.path.exists', return_value=True):
            with patch('builtins.open', side_effect=Exception("read error")):
                result = _build_runtime_status(state)
        self.assertFalse(result["containment_active"])


class TestFieldProgressionAdvance(unittest.TestCase):
    """Tests for _advance_to_next_field."""

    def test_advance_normal(self):
        from backend.api.field_progression_api import _advance_to_next_field, _default_state
        state = _default_state()
        result = _advance_to_next_field(state)
        self.assertIsNotNone(result)
        self.assertEqual(state["active_field_id"], 1)
        self.assertTrue(result["active"])
        self.assertEqual(result["state"], "TRAINING")

    def test_advance_last_field(self):
        from backend.api.field_progression_api import _advance_to_next_field, _default_state, TOTAL_FIELDS
        state = _default_state()
        state["active_field_id"] = TOTAL_FIELDS - 1
        result = _advance_to_next_field(state)
        self.assertIsNone(result)

    def test_advance_already_training(self):
        from backend.api.field_progression_api import _advance_to_next_field, _default_state
        state = _default_state()
        state["fields"][1]["state"] = "TRAINING"
        result = _advance_to_next_field(state)
        self.assertIsNotNone(result)
        self.assertEqual(result["state"], "TRAINING")


class TestFieldProgressionGetActiveProgress(unittest.TestCase):
    """Tests for get_active_progress."""

    def test_get_active_progress_normal(self):
        from backend.api.field_progression_api import get_active_progress
        with patch('backend.api.field_progression_api._load_field_state') as mock_load:
            from backend.api.field_progression_api import _default_state
            mock_load.return_value = _default_state()
            result = get_active_progress()
        self.assertEqual(result["status"], "ok")
        self.assertIn("active_field", result)
        self.assertEqual(result["active_field"]["id"], 0)

    def test_get_active_progress_all_complete(self):
        from backend.api.field_progression_api import get_active_progress, _default_state, TOTAL_FIELDS
        state = _default_state()
        state["active_field_id"] = TOTAL_FIELDS
        with patch('backend.api.field_progression_api._load_field_state', return_value=state):
            result = get_active_progress()
        self.assertEqual(result["status"], "all_complete")


class TestFieldProgressionApproveField(unittest.TestCase):
    """Tests for approve_field."""

    def test_approve_empty_approver(self):
        from backend.api.field_progression_api import approve_field
        result = approve_field(0, "", "some reason")
        self.assertEqual(result["status"], "error")
        self.assertIn("APPROVAL_REJECTED", result["message"])

    def test_approve_empty_reason(self):
        from backend.api.field_progression_api import approve_field
        result = approve_field(0, "admin", "")
        self.assertEqual(result["status"], "error")

    def test_approve_invalid_field_id(self):
        from backend.api.field_progression_api import approve_field
        result = approve_field(-1, "admin", "reason")
        self.assertEqual(result["status"], "error")
        self.assertIn("INVALID_FIELD_ID", result["message"])

    def test_approve_out_of_range(self):
        from backend.api.field_progression_api import approve_field, TOTAL_FIELDS
        result = approve_field(TOTAL_FIELDS + 1, "admin", "reason")
        self.assertEqual(result["status"], "error")


class TestFieldProgressionLoadSave(unittest.TestCase):
    """Tests for load/save field state."""

    def test_load_field_state_missing(self):
        from backend.api.field_progression_api import _load_field_state
        with patch('os.path.exists', return_value=False):
            state = _load_field_state()
        self.assertEqual(state["active_field_id"], 0)

    def test_load_field_state_corrupt(self):
        from backend.api.field_progression_api import _load_field_state
        with patch('os.path.exists', return_value=True):
            with patch('builtins.open', mock_open(read_data="not json")):
                state = _load_field_state()
        self.assertEqual(state["active_field_id"], 0)  # falls back to default


class TestFieldProgressionSaveRuntimeStatus(unittest.TestCase):
    """Tests for _save_runtime_status."""

    def test_save_runtime_status(self):
        from backend.api.field_progression_api import _save_runtime_status
        with patch('os.makedirs'):
            with patch('builtins.open', mock_open()):
                with patch('os.replace'):
                    with patch('os.fsync'):
                        _save_runtime_status({"test": True})


class TestFieldProgressionSignedApproval(unittest.TestCase):
    """Tests for _signed_approval_status."""

    def test_signed_approval_exception(self):
        from backend.api.field_progression_api import _signed_approval_status
        mock_ledger = MagicMock()
        mock_ledger.load.side_effect = Exception("broken")
        with patch('backend.api.field_progression_api.ApprovalLedger', return_value=mock_ledger):
            result = _signed_approval_status(0)
        self.assertFalse(result["has_signed_approval"])
        self.assertFalse(result["chain_valid"])


# ---------------------------------------------------------------------------
# 2. runtime_api.py — Validation logic tests (~56 missing lines)
# ---------------------------------------------------------------------------

class TestRuntimeApiHelpers(unittest.TestCase):
    """Tests for runtime_api pure functions."""

    def test_validate_structure_all_present(self):
        from backend.api.runtime_api import _validate_structure, REQUIRED_FIELDS
        data = {f: 0 for f in REQUIRED_FIELDS}
        self.assertEqual(_validate_structure(data), [])

    def test_validate_structure_missing(self):
        from backend.api.runtime_api import _validate_structure
        missing = _validate_structure({})
        self.assertGreater(len(missing), 0)
        self.assertIn("total_epochs", missing)

    def test_sign_payload(self):
        from backend.api.runtime_api import _sign_payload
        sig = _sign_payload({"a": 1, "b": 2})
        self.assertEqual(len(sig), 64)
        # Same payload should produce same signature
        sig2 = _sign_payload({"b": 2, "a": 1})
        self.assertEqual(sig, sig2)

    def test_crc32_table(self):
        from backend.api.runtime_api import _CRC_TABLE
        self.assertEqual(len(_CRC_TABLE), 256)

    def test_compute_crc32(self):
        from backend.api.runtime_api import compute_crc32
        crc = compute_crc32(b"hello")
        self.assertIsInstance(crc, int)
        # Known CRC32 value for "hello"
        self.assertEqual(crc, 0x3610A686)

    def test_compute_payload_crc(self):
        from backend.api.runtime_api import compute_payload_crc
        payload = {
            "schema_version": 1,
            "determinism_status": True,
            "freeze_status": False,
            "precision": 0.95,
            "recall": 0.90,
            "kl_divergence": 0.01,
            "ece": 0.02,
            "loss": 0.5,
            "gpu_temperature": 65.0,
            "epoch": 10,
            "batch_size": 32,
            "timestamp": 1000,
            "monotonic_timestamp": 2000,
        }
        crc = compute_payload_crc(payload)
        self.assertIsInstance(crc, int)

    def test_get_hmac_secret_set(self):
        from backend.api.runtime_api import get_hmac_secret
        with patch.dict(os.environ, {"YGB_HMAC_SECRET": "mysecret"}):
            self.assertEqual(get_hmac_secret(), "mysecret")

    def test_get_hmac_secret_missing(self):
        from backend.api.runtime_api import get_hmac_secret
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(RuntimeError):
                get_hmac_secret()

    def test_load_hmac_key_from_env(self):
        from backend.api.runtime_api import load_hmac_key
        with patch.dict(os.environ, {"YGB_HMAC_SECRET": "not-hex!"}):
            key = load_hmac_key()
        self.assertEqual(key, b"not-hex!")  # treated as UTF-8 since not valid hex

    def test_load_hmac_key_hex_env(self):
        from backend.api.runtime_api import load_hmac_key
        with patch.dict(os.environ, {"YGB_HMAC_SECRET": "aabbccdd"}):
            key = load_hmac_key()
        self.assertEqual(key, bytes.fromhex("aabbccdd"))

    def test_load_hmac_key_no_env_no_file(self):
        from backend.api.runtime_api import load_hmac_key
        with patch.dict(os.environ, {"YGB_HMAC_SECRET": ""}, clear=True):
            with patch('builtins.open', side_effect=FileNotFoundError):
                with self.assertRaises(RuntimeError):
                    load_hmac_key()

    def test_validate_hmac_missing(self):
        from backend.api.runtime_api import validate_hmac
        self.assertFalse(validate_hmac({"no_hmac": True}))

    def test_load_last_seen_timestamp_missing(self):
        from backend.api.runtime_api import load_last_seen_timestamp
        with patch('builtins.open', side_effect=FileNotFoundError):
            ts = load_last_seen_timestamp()
        self.assertEqual(ts, 0)

    def test_load_last_seen_timestamp_valid(self):
        from backend.api.runtime_api import load_last_seen_timestamp
        with patch('builtins.open', mock_open(read_data='{"last_seen": 12345}')):
            ts = load_last_seen_timestamp()
        self.assertEqual(ts, 12345)


class TestRuntimeApiValidation(unittest.TestCase):
    """Tests for validate_telemetry."""

    def test_validate_telemetry_missing_file(self):
        from backend.api.runtime_api import validate_telemetry
        with patch('os.path.exists', return_value=False):
            result = validate_telemetry()
        self.assertEqual(result["status"], "corrupted")
        self.assertEqual(result["reason"], "telemetry_missing")

    def test_validate_telemetry_read_error(self):
        from backend.api.runtime_api import validate_telemetry
        with patch('os.path.exists', return_value=True):
            with patch('builtins.open', side_effect=IOError("read error")):
                result = validate_telemetry()
        self.assertEqual(result["status"], "corrupted")
        self.assertEqual(result["reason"], "read_failed")

    def test_validate_telemetry_invalid_json(self):
        from backend.api.runtime_api import validate_telemetry
        with patch('os.path.exists', return_value=True):
            with patch('builtins.open', mock_open(read_data="not json{{{")):
                result = validate_telemetry()
        self.assertEqual(result["status"], "corrupted")
        self.assertEqual(result["reason"], "json_parse_failed")

    def test_validate_telemetry_missing_field(self):
        from backend.api.runtime_api import validate_telemetry
        data = {"schema_version": 1}  # Missing other required fields
        with patch('os.path.exists', return_value=True):
            with patch('builtins.open', mock_open(read_data=json.dumps(data))):
                result = validate_telemetry()
        self.assertEqual(result["status"], "corrupted")
        self.assertEqual(result["reason"], "missing_field")


class TestRuntimeApiGetStatus(unittest.TestCase):
    """Tests for get_runtime_status."""

    def test_get_runtime_status_no_files(self):
        from backend.api.runtime_api import get_runtime_status
        with patch('os.path.exists', return_value=False):
            result = get_runtime_status()
        self.assertEqual(result["status"], "awaiting_data")
        self.assertEqual(result["storage_engine_status"], "NOT_INITIALIZED")

    def test_get_runtime_status_valid_state(self):
        from backend.api.runtime_api import get_runtime_status, REQUIRED_FIELDS
        import time as _time
        data = {f: 0 for f in REQUIRED_FIELDS}
        data["last_update_ms"] = int(_time.time() * 1000)
        data["determinism_status"] = True
        data["total_errors"] = 0

        def exists_side_effect(path):
            return "runtime_state" in path

        with patch('os.path.exists', side_effect=exists_side_effect):
            with patch('builtins.open', mock_open(read_data=json.dumps(data))):
                result = get_runtime_status()
        self.assertEqual(result["status"], "active")
        self.assertEqual(result["storage_engine_status"], "ACTIVE")

    def test_get_runtime_status_stale(self):
        from backend.api.runtime_api import get_runtime_status, REQUIRED_FIELDS
        data = {f: 0 for f in REQUIRED_FIELDS}
        data["last_update_ms"] = 1000  # Very old
        data["determinism_status"] = True
        data["total_errors"] = 0

        def exists_side_effect(path):
            return "runtime_state" in path

        with patch('os.path.exists', side_effect=exists_side_effect):
            with patch('builtins.open', mock_open(read_data=json.dumps(data))):
                result = get_runtime_status()
        self.assertEqual(result["status"], "active")
        self.assertEqual(result["storage_engine_status"], "STALE")
        self.assertTrue(result["stale"])

    def test_get_runtime_status_degraded(self):
        from backend.api.runtime_api import get_runtime_status, REQUIRED_FIELDS
        import time as _time
        data = {f: 0 for f in REQUIRED_FIELDS}
        data["last_update_ms"] = int(_time.time() * 1000)
        data["total_errors"] = 5

        def exists_side_effect(path):
            return "runtime_state" in path

        with patch('os.path.exists', side_effect=exists_side_effect):
            with patch('builtins.open', mock_open(read_data=json.dumps(data))):
                result = get_runtime_status()
        self.assertEqual(result["storage_engine_status"], "DEGRADED")

    def test_get_runtime_status_missing_fields(self):
        from backend.api.runtime_api import get_runtime_status
        data = {"partial": True}

        def exists_side_effect(path):
            return "runtime_state" in path

        with patch('os.path.exists', side_effect=exists_side_effect):
            with patch('builtins.open', mock_open(read_data=json.dumps(data))):
                result = get_runtime_status()
        self.assertEqual(result["status"], "invalid")

    def test_get_runtime_status_corrupt_json(self):
        from backend.api.runtime_api import get_runtime_status

        def exists_side_effect(path):
            return "runtime_state" in path

        with patch('os.path.exists', side_effect=exists_side_effect):
            with patch('builtins.open', mock_open(read_data="not json")):
                result = get_runtime_status()
        self.assertEqual(result["status"], "error")


class TestRuntimeApiInitialize(unittest.TestCase):
    """Tests for initialize_runtime."""

    def test_initialize_non_production(self):
        from backend.api.runtime_api import initialize_runtime
        with patch.dict(os.environ, {"YGB_ENV": "development"}):
            initialize_runtime()  # Should return without error

    def test_initialize_production_no_secret(self):
        from backend.api.runtime_api import initialize_runtime
        with patch.dict(os.environ, {"YGB_ENV": "production", "YGB_HMAC_SECRET": ""}):
            with self.assertRaises(RuntimeError):
                initialize_runtime()

    def test_initialize_production_with_secret(self):
        from backend.api.runtime_api import initialize_runtime
        with patch.dict(os.environ, {"YGB_ENV": "production", "YGB_HMAC_SECRET": "secret123"}):
            with patch('os.path.exists', return_value=False):
                initialize_runtime()  # Should not raise


# ---------------------------------------------------------------------------
# 3. report_generator.py — Helper and ID generation tests
# ---------------------------------------------------------------------------

class TestReportGeneratorHelpers2(unittest.TestCase):
    """Additional tests for report_generator helpers."""

    def test_generate_id(self):
        from backend.api.report_generator import _generate_id
        rid = _generate_id("rpt")
        self.assertTrue(rid.startswith("rpt-"))
        self.assertEqual(len(rid), 3 + 1 + 16)

    def test_now_iso(self):
        from backend.api.report_generator import _now_iso
        ts = _now_iso()
        self.assertIn("T", ts)
        # Should be valid ISO format
        dt = datetime.fromisoformat(ts.replace("+00:00", "+00:00"))
        self.assertIsNotNone(dt)

    def test_ensure_tables_success(self):
        from backend.api import report_generator
        report_generator._TABLES_CREATED = False
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        with patch('backend.api.report_generator.get_db_connection', return_value=mock_conn):
            report_generator._ensure_tables()
        self.assertTrue(report_generator._TABLES_CREATED)
        mock_conn.commit.assert_called_once()
        mock_conn.close.assert_called_once()
        report_generator._TABLES_CREATED = False

    def test_ensure_tables_db_error(self):
        from backend.api import report_generator
        report_generator._TABLES_CREATED = False
        mock_conn = MagicMock()
        mock_conn.cursor.side_effect = Exception("SQL error")
        with patch('backend.api.report_generator.get_db_connection', return_value=mock_conn):
            report_generator._ensure_tables()
        self.assertFalse(report_generator._TABLES_CREATED)
        mock_conn.close.assert_called_once()


# ---------------------------------------------------------------------------
# 4. auth_server.py login endpoint — cover the remaining branches
# ---------------------------------------------------------------------------

class TestAuthServerLoginEndpoint(unittest.TestCase):
    """Tests for the login endpoint in auth_server."""

    def _mock_request(self, ip="127.0.0.1"):
        req = MagicMock()
        req.client.host = ip
        return req

    def test_login_user_not_found(self):
        from backend.api.auth_server import login, LoginRequest
        from fastapi import HTTPException
        from backend.api import auth_server
        auth_server._login_attempts.clear()
        auth_server._failure_counts.clear()

        request = self._mock_request()
        response = MagicMock()
        req = LoginRequest(username="noone", password="pass", device_id="dev1")

        with patch('backend.api.auth_server.load_json', return_value={}):
            with patch('backend.api.auth_server.log_audit'):
                with self.assertRaises(HTTPException) as ctx:
                    login(req, request, response)
        self.assertEqual(ctx.exception.status_code, 401)

    def test_login_bad_password(self):
        from backend.api.auth_server import login, LoginRequest
        from fastapi import HTTPException
        from backend.api import auth_server
        import bcrypt
        auth_server._login_attempts.clear()
        auth_server._failure_counts.clear()

        hashed = bcrypt.hashpw(b"correct", bcrypt.gensalt()).decode('utf-8')
        users = {"testuser": {"password_hash": hashed}}
        request = self._mock_request()
        response = MagicMock()
        req = LoginRequest(username="testuser", password="wrong", device_id="dev1")

        with patch('backend.api.auth_server.load_json', return_value=users):
            with patch('backend.api.auth_server.log_audit'):
                with self.assertRaises(HTTPException) as ctx:
                    login(req, request, response)
        self.assertEqual(ctx.exception.status_code, 401)

    def test_login_trusted_device(self):
        from backend.api.auth_server import login, LoginRequest
        from backend.api import auth_server
        import bcrypt
        auth_server._login_attempts.clear()
        auth_server._failure_counts.clear()

        hashed = bcrypt.hashpw(b"correct", bcrypt.gensalt()).decode('utf-8')
        users = {"testuser": {"password_hash": hashed, "email": "u@test.com"}}
        request = self._mock_request()
        response = MagicMock()
        req = LoginRequest(username="testuser", password="correct", device_id="dev1")

        with patch('backend.api.auth_server.load_json', return_value=users):
            with patch('backend.api.auth_server.is_trusted_device', return_value=True):
                with patch('backend.api.auth_server.create_session', return_value="tok" * 21):
                    with patch('backend.api.auth_server.log_audit'):
                        result = login(req, request, response)
        self.assertEqual(result["status"], "success")
        self.assertFalse(result["require_otp"])

    def test_login_untrusted_new_device_otp(self):
        from backend.api.auth_server import login, LoginRequest
        from backend.api import auth_server
        import bcrypt
        auth_server._login_attempts.clear()
        auth_server._failure_counts.clear()
        auth_server._otp_requests.clear()

        hashed = bcrypt.hashpw(b"correct", bcrypt.gensalt()).decode('utf-8')
        users = {"testuser": {"password_hash": hashed, "email": "u@test.com"}}
        request = self._mock_request()
        response = MagicMock()
        req = LoginRequest(username="testuser", password="correct", device_id="dev1")

        with patch('backend.api.auth_server.load_json', return_value=users):
            with patch('backend.api.auth_server.is_trusted_device', return_value=False):
                with patch('backend.api.auth_server.generate_and_store_otp', return_value=True):
                    with patch('backend.api.auth_server.log_audit'):
                        result = login(req, request, response)
        self.assertEqual(result["status"], "pending")
        self.assertTrue(result["require_otp"])


class TestAuthServerVerifyOTP(unittest.TestCase):
    """Tests for verify_otp endpoint."""

    def test_verify_otp_no_pending(self):
        from backend.api.auth_server import verify_otp, OTPVerifyRequest
        from fastapi import HTTPException
        req = OTPVerifyRequest(username="u1", otp="123456", fingerprint="fp1")
        request = MagicMock()
        request.client.host = "1.2.3.4"
        response = MagicMock()
        with patch('backend.api.auth_server.load_json', return_value={}):
            with self.assertRaises(HTTPException) as ctx:
                verify_otp(req, request, response)
        self.assertEqual(ctx.exception.status_code, 401)

    def test_verify_otp_expired(self):
        from backend.api.auth_server import verify_otp, OTPVerifyRequest
        from fastapi import HTTPException
        otps = {"u1": {"hash": "abc", "expires_at": time.time() - 100, "used": False}}
        req = OTPVerifyRequest(username="u1", otp="123456", fingerprint="fp1")
        request = MagicMock()
        request.client.host = "1.2.3.4"
        response = MagicMock()
        with patch('backend.api.auth_server.load_json', return_value=otps):
            with self.assertRaises(HTTPException) as ctx:
                verify_otp(req, request, response)
        self.assertEqual(ctx.exception.status_code, 401)

    def test_verify_otp_invalid_hash(self):
        from backend.api.auth_server import verify_otp, OTPVerifyRequest
        from fastapi import HTTPException
        otps = {"u1": {"hash": "wrong_hash", "expires_at": time.time() + 300, "used": False}}
        req = OTPVerifyRequest(username="u1", otp="123456", fingerprint="fp1")
        request = MagicMock()
        request.client.host = "1.2.3.4"
        response = MagicMock()
        with patch('backend.api.auth_server.load_json', return_value=otps):
            with patch('backend.api.auth_server.log_audit'):
                with self.assertRaises(HTTPException) as ctx:
                    verify_otp(req, request, response)
        self.assertEqual(ctx.exception.status_code, 401)


# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    unittest.main()
