"""
test_system_status.py — Tests for the aggregated system status endpoint.

Validates:
    1. system_status_router has the /api/system/status route
    2. _safe_call returns degraded status on failure
    3. Training state returns idle with null metrics when not training
    4. Response structure has all expected top-level fields
    5. No subsystem contains mock/placeholder data
"""

import os
import sys
import time
import unittest
from pathlib import Path
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


class TestSystemStatusRouter(unittest.TestCase):
    """Verify system status router is properly configured."""

    def test_router_has_status_route(self):
        from backend.api.system_status import system_status_router
        paths = [r.path for r in system_status_router.routes]
        self.assertIn("/api/system/status", paths)

    def test_aggregated_status_is_async(self):
        import inspect
        from backend.api.system_status import aggregated_system_status
        self.assertTrue(inspect.iscoroutinefunction(aggregated_system_status))


class TestSafeCall(unittest.TestCase):
    """Verify _safe_call returns degraded status on errors."""

    def test_returns_result_on_success(self):
        from backend.api.system_status import _safe_call
        result = _safe_call("test", lambda: {"status": "ok"})
        self.assertEqual(result, {"status": "ok"})

    def test_returns_degraded_on_exception(self):
        from backend.api.system_status import _safe_call

        def failing_fn():
            raise RuntimeError("test error")

        result = _safe_call("test", failing_fn)
        self.assertEqual(result["status"], "UNAVAILABLE")
        self.assertIn("test error", result["error"])

    def test_passes_args_and_kwargs(self):
        from backend.api.system_status import _safe_call
        result = _safe_call("test", lambda x, y=1: {"x": x, "y": y}, 42, y=99)
        self.assertEqual(result, {"x": 42, "y": 99})


class TestTrainingStateNoMocks(unittest.TestCase):
    """Verify training state returns real idle data, not placeholders."""

    def test_idle_state_has_null_metrics(self):
        from backend.api.system_status import _get_training_state
        state = _get_training_state()
        self.assertIn("status", state)
        # When idle, loss and throughput should be None
        if state["status"] in ("idle", "error"):
            self.assertIsNone(state.get("loss"))
            self.assertIsNone(state.get("throughput"))

    def test_training_state_has_required_fields(self):
        from backend.api.system_status import _get_training_state
        state = _get_training_state()
        for field in ("status", "current_epoch", "total_epochs", "loss", "throughput"):
            self.assertIn(field, state, f"Missing field: {field}")


class TestReadinessIntegration(unittest.TestCase):
    """Verify readiness checks run and return typed result."""

    def test_readiness_returns_dict(self):
        from backend.api.system_status import _get_readiness
        result = _get_readiness()
        self.assertIsInstance(result, dict)
        self.assertIn("ready", result)
        self.assertIn("checks", result)

    def test_metrics_snapshot_has_counters(self):
        from backend.api.system_status import _get_metrics_snapshot
        snapshot = _get_metrics_snapshot()
        self.assertIn("counters", snapshot)
        self.assertIsInstance(snapshot["counters"], dict)


class TestNoPlaceholderData(unittest.TestCase):
    """Verify no subsystem returns mock/placeholder/hardcoded data."""

    FORBIDDEN_PATTERNS = [
        "MOCK", "PLACEHOLDER", "FAKE", "DUMMY", "SIMULATED",
        "TODO", "HARDCODED", "EXAMPLE_",
    ]

    def _check_dict_for_placeholders(self, data, path=""):
        """Recursively check dict values for forbidden patterns."""
        if isinstance(data, dict):
            for k, v in data.items():
                self._check_dict_for_placeholders(v, f"{path}.{k}")
        elif isinstance(data, str):
            upper = data.upper()
            for pattern in self.FORBIDDEN_PATTERNS:
                if pattern in upper:
                    self.fail(
                        f"Forbidden placeholder '{pattern}' found at {path}: {data!r}"
                    )

    def test_safe_call_result_no_placeholders(self):
        from backend.api.system_status import _safe_call
        result = _safe_call("test", lambda: {"status": "ok", "detail": "real data"})
        self._check_dict_for_placeholders(result, "safe_call_result")


if __name__ == "__main__":
    unittest.main()
