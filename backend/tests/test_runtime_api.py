"""
test_runtime_api.py — Tests for GET /runtime/status

Covers:
  - Missing file → awaiting_data
  - Valid file → active with all fields
  - Invalid structure → missing fields error
  - Stale data detection
  - Determinism flag verification
  - Signature presence
  - Corrupt file → error
"""

import json
import os
import tempfile
import time
import unittest
from unittest import mock

from backend.api.runtime_api import (
    get_runtime_status,
    get_detailed_status,
    _validate_structure,
    _sign_payload,
    REQUIRED_FIELDS,
    STALE_THRESHOLD_MS,
)


def _make_valid_state(**overrides):
    """Create a valid runtime_state dict."""
    now_ms = int(time.time() * 1000)
    state = {
        "total_epochs": 100,
        "completed_epochs": 42,
        "current_loss": 0.3500,
        "best_loss": 0.2800,
        "precision": 0.9500,
        "ece": 0.0120,
        "drift_kl": 0.0500,
        "duplicate_rate": 0.0100,
        "gpu_util": 85.50,
        "cpu_util": 60.00,
        "temperature": 72.3,
        "determinism_status": True,
        "freeze_status": True,
        "mode": "MODE_A",
        "progress_pct": 42.00,
        "loss_trend": -0.010000,
        "last_update_ms": now_ms,
        "training_start_ms": now_ms - 3600000,
        "total_errors": 0,
    }
    state.update(overrides)
    return state


class TestValidateStructure(unittest.TestCase):
    def test_all_fields_present(self):
        data = _make_valid_state()
        self.assertEqual(_validate_structure(data), [])

    def test_missing_fields(self):
        data = {"total_epochs": 100}
        missing = _validate_structure(data)
        self.assertIn("completed_epochs", missing)
        self.assertIn("precision", missing)

    def test_empty_dict(self):
        self.assertEqual(len(_validate_structure({})), len(REQUIRED_FIELDS))


class TestSignPayload(unittest.TestCase):
    def test_deterministic(self):
        payload = {"a": 1, "b": 2}
        sig1 = _sign_payload(payload)
        sig2 = _sign_payload(payload)
        self.assertEqual(sig1, sig2)

    def test_different_payloads(self):
        sig1 = _sign_payload({"a": 1})
        sig2 = _sign_payload({"a": 2})
        self.assertNotEqual(sig1, sig2)


class TestGetRuntimeStatus(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(
            mode='w', suffix='.json', delete=False
        )
        self.tmp_path = self.tmp.name
        self.tmp.close()

    def tearDown(self):
        if os.path.exists(self.tmp_path):
            os.unlink(self.tmp_path)

    def _write_state(self, data):
        with open(self.tmp_path, 'w') as f:
            json.dump(data, f)

    def _assert_trace_id(self, result):
        self.assertIn("trace_id", result)
        self.assertEqual(len(result["trace_id"]), 8)

    @mock.patch('backend.api.runtime_api.RUNTIME_STATE_PATH', '/nonexistent/path.json')
    def test_missing_file_returns_awaiting(self):
        result = get_runtime_status()
        self.assertEqual(result["status"], "awaiting_data")
        self.assertIn("timestamp", result)
        self._assert_trace_id(result)

    @mock.patch('backend.api.runtime_api.RUNTIME_STATE_PATH')
    def test_valid_file_returns_active(self, mock_path):
        mock_path.__str__ = lambda s: self.tmp_path
        # Patch at module level
        with mock.patch('backend.api.runtime_api.RUNTIME_STATE_PATH', self.tmp_path):
            state = _make_valid_state()
            self._write_state(state)
            result = get_runtime_status()
            self.assertEqual(result["status"], "active")
            self.assertIn("runtime", result)
            self.assertIn("signature", result)
            self.assertEqual(result["runtime"]["total_epochs"], 100)
            self.assertEqual(result["runtime"]["completed_epochs"], 42)
            self.assertEqual(result["runtime"]["precision"], 0.95)
            self.assertTrue(result["determinism_ok"])
            self._assert_trace_id(result)

    @mock.patch('backend.api.runtime_api.RUNTIME_STATE_PATH')
    def test_invalid_structure_returns_invalid(self, mock_path):
        with mock.patch('backend.api.runtime_api.RUNTIME_STATE_PATH', self.tmp_path):
            self._write_state({"total_epochs": 50})  # Missing many fields
            result = get_runtime_status()
            self.assertEqual(result["status"], "invalid")
            self.assertIn("Missing required fields", result["message"])
            self._assert_trace_id(result)

    @mock.patch('backend.api.runtime_api.RUNTIME_STATE_PATH')
    def test_stale_data_detected(self, mock_path):
        with mock.patch('backend.api.runtime_api.RUNTIME_STATE_PATH', self.tmp_path):
            old_ms = int(time.time() * 1000) - STALE_THRESHOLD_MS - 10000
            state = _make_valid_state(last_update_ms=old_ms)
            self._write_state(state)
            result = get_runtime_status()
            self.assertEqual(result["status"], "active")
            self.assertTrue(result["stale"])
            self._assert_trace_id(result)

    @mock.patch('backend.api.runtime_api.RUNTIME_STATE_PATH')
    def test_fresh_data_not_stale(self, mock_path):
        with mock.patch('backend.api.runtime_api.RUNTIME_STATE_PATH', self.tmp_path):
            state = _make_valid_state(last_update_ms=int(time.time() * 1000))
            self._write_state(state)
            result = get_runtime_status()
            self.assertEqual(result["status"], "active")
            self.assertFalse(result["stale"])
            self._assert_trace_id(result)

    @mock.patch('backend.api.runtime_api.RUNTIME_STATE_PATH')
    def test_determinism_false_flagged(self, mock_path):
        with mock.patch('backend.api.runtime_api.RUNTIME_STATE_PATH', self.tmp_path):
            state = _make_valid_state(determinism_status=False)
            self._write_state(state)
            result = get_runtime_status()
            self.assertEqual(result["status"], "active")
            self.assertFalse(result["determinism_ok"])
            self._assert_trace_id(result)

    @mock.patch('backend.api.runtime_api.RUNTIME_STATE_PATH')
    def test_corrupt_file_returns_error(self, mock_path):
        with mock.patch('backend.api.runtime_api.RUNTIME_STATE_PATH', self.tmp_path):
            with open(self.tmp_path, 'w') as f:
                f.write("not json {{{")
            result = get_runtime_status()
            self.assertEqual(result["status"], "error")
            self.assertIn("detail", result)
            self._assert_trace_id(result)


class TestDetailedRuntimeStatus(unittest.TestCase):
    def test_detailed_status_response_shape(self):
        from backend.training.feature_bridge import FeatureHealthReport

        mock_pipeline = mock.Mock()
        mock_pipeline.get_source_status.return_value = {
            "nvd": {
                "name": "NVD",
                "status": "CONNECTED",
                "circuit_breaker": "CLOSED",
            }
        }
        mock_worker = mock.Mock()
        mock_worker.get_status.return_value = {
            "last_batch": {
                "batch_id": "CBI-000001",
                "ingested": 3,
                "deduped": 1,
            }
        }
        mock_diversifier = mock.Mock()
        mock_diversifier.get_health.return_value = FeatureHealthReport(
            total=1,
            valid=1,
            invalid=0,
            invalid_paths=[],
        )

        with mock.patch('backend.cve.cve_pipeline.get_pipeline', return_value=mock_pipeline), \
                mock.patch('backend.sync.peer_transport.get_peer_statuses', return_value={"peer-a": "REACHABLE"}), \
                mock.patch(
                    'backend.storage.tiered_storage.get_tier_health',
                    return_value=[{
                        "tier_name": "ssd",
                        "available_bytes": 1024,
                        "used_bytes": 512,
                        "read_latency_ms": 0.5,
                        "write_latency_ms": 0.75,
                    }],
                ), \
                mock.patch('backend.training.feature_bridge.FeatureDiversifier', return_value=mock_diversifier), \
                mock.patch('backend.cve.bridge_ingestion_worker.get_bridge_worker', return_value=mock_worker):
            result = get_detailed_status()

        self.assertIn("trace_id", result)
        self.assertEqual(len(result["trace_id"]), 8)
        self.assertIn("timestamp", result)
        self.assertIn("components", result)

        for name in (
            "circuit_breaker_stats",
            "peer_statuses",
            "tier_health",
            "feature_health",
            "last_batch",
        ):
            self.assertIn(name, result["components"])
            self.assertIn("status", result["components"][name])
            self.assertIn("detail", result["components"][name])


if __name__ == "__main__":
    unittest.main()
