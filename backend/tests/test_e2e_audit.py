"""
test_e2e_audit.py — Consolidated end-to-end audit test suite.

Validates all critical infrastructure from the full repository audit:
  1. Metrics registry: all domain metrics recordable
  2. Health probes: endpoints have correct signatures
  3. Circuit breaker: state transitions work correctly
  4. Structured logging: formatter produces valid JSON
  5. Auth guard: preflight checks fail on weak secrets
  6. Dependency checker: checks run and return typed results
  7. Reliability gate: script imports and runs without error
  8. Metric completeness: all CRITICAL_METRICS are defined
"""

import json
import logging
import os
import sys
import time
import unittest
from pathlib import Path
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


# ============================================================================
# 1. Metrics Registry — Domain Metrics
# ============================================================================
class TestDomainMetrics(unittest.TestCase):
    """Verify all domain metrics can be recorded and queried."""

    def setUp(self):
        from backend.observability.metrics import MetricsRegistry
        self.registry = MetricsRegistry()

    def test_training_latency_recordable(self):
        self.registry.record("training_latency_ms", 1234.5)
        stats = self.registry.get_histogram_stats("training_latency_ms")
        self.assertEqual(stats["count"], 1)
        self.assertEqual(stats["mean"], 1234.5)

    def test_voice_inference_latency_recordable(self):
        self.registry.record("voice_inference_latency_ms", 50.0)
        self.registry.record("voice_inference_latency_ms", 75.0)
        stats = self.registry.get_histogram_stats("voice_inference_latency_ms")
        self.assertEqual(stats["count"], 2)
        self.assertAlmostEqual(stats["mean"], 62.5, places=1)

    def test_report_generation_latency_recordable(self):
        self.registry.record("report_generation_latency_ms", 200.0)
        stats = self.registry.get_histogram_stats("report_generation_latency_ms")
        self.assertEqual(stats["count"], 1)

    def test_model_accuracy_gauge(self):
        self.registry.set_gauge("model_accuracy", 0.95)
        self.assertEqual(self.registry.get_gauge("model_accuracy"), 0.95)

    def test_ece_gauge(self):
        self.registry.set_gauge("ece", 0.03)
        self.assertEqual(self.registry.get_gauge("ece"), 0.03)

    def test_drift_kl_gauge(self):
        self.registry.set_gauge("drift_kl", 0.01)
        self.assertEqual(self.registry.get_gauge("drift_kl"), 0.01)

    def test_duplicate_rate_gauge(self):
        self.registry.set_gauge("duplicate_rate", 0.005)
        self.assertEqual(self.registry.get_gauge("duplicate_rate"), 0.005)

    def test_snapshot_includes_all_critical(self):
        """Snapshot must include all critical metrics as counters."""
        from backend.observability.metrics import CRITICAL_METRICS
        snapshot = self.registry.get_snapshot()
        for name in CRITICAL_METRICS:
            self.assertIn(name, snapshot["counters"],
                          f"Critical metric '{name}' missing from snapshot counters")


# ============================================================================
# 2. CRITICAL_METRICS Completeness
# ============================================================================
class TestCriticalMetricsDefinition(unittest.TestCase):
    """Verify CRITICAL_METRICS includes all required domain metrics."""

    def test_infrastructure_metrics_present(self):
        from backend.observability.metrics import CRITICAL_METRICS
        infra = [
            "request_count", "error_count", "timeout_count",
            "measurement_completeness_ratio", "null_metric_ratio",
            "request_latency_ms", "dependency_latency_ms", "readiness_latency_ms",
        ]
        for name in infra:
            self.assertIn(name, CRITICAL_METRICS, f"Missing infra metric: {name}")

    def test_domain_metrics_present(self):
        from backend.observability.metrics import CRITICAL_METRICS
        domain = [
            "training_latency_ms", "voice_inference_latency_ms",
            "report_generation_latency_ms", "model_accuracy",
            "ece", "drift_kl", "duplicate_rate",
        ]
        for name in domain:
            self.assertIn(name, CRITICAL_METRICS, f"Missing domain metric: {name}")


# ============================================================================
# 3. Health Probes — Endpoint Existence
# ============================================================================
class TestHealthProbeEndpoints(unittest.TestCase):
    """Verify health probe module has correct endpoints."""

    def test_healthz_exists(self):
        from backend.reliability.health_endpoints import liveness
        import inspect
        self.assertTrue(inspect.iscoroutinefunction(liveness))

    def test_readyz_exists(self):
        from backend.reliability.health_endpoints import readiness
        import inspect
        self.assertTrue(inspect.iscoroutinefunction(readiness))

    def test_health_router_has_routes(self):
        from backend.reliability.health_endpoints import health_router
        paths = [r.path for r in health_router.routes]
        self.assertIn("/healthz", paths)
        self.assertIn("/readyz", paths)


# ============================================================================
# 4. Circuit Breaker — State Transitions
# ============================================================================
class TestCircuitBreakerStateTransitions(unittest.TestCase):
    """Verify circuit breaker state machine works correctly."""

    def test_closed_to_open_on_failures(self):
        from backend.reliability.circuit_breaker import CircuitBreaker, CircuitState
        cb = CircuitBreaker("test", failure_threshold=3, recovery_timeout=0.1)
        self.assertEqual(cb.state, CircuitState.CLOSED)

        for _ in range(3):
            cb.record_failure()
        self.assertEqual(cb.state, CircuitState.OPEN)

    def test_open_to_half_open_after_timeout(self):
        from backend.reliability.circuit_breaker import CircuitBreaker, CircuitState
        cb = CircuitBreaker("test", failure_threshold=1, recovery_timeout=0.1)
        cb.record_failure()
        self.assertEqual(cb.state, CircuitState.OPEN)

        time.sleep(0.15)
        self.assertEqual(cb.state, CircuitState.HALF_OPEN)

    def test_half_open_to_closed_on_success(self):
        from backend.reliability.circuit_breaker import CircuitBreaker, CircuitState
        cb = CircuitBreaker("test", failure_threshold=1, recovery_timeout=0.01, success_threshold=1)
        cb.record_failure()
        time.sleep(0.02)
        self.assertEqual(cb.state, CircuitState.HALF_OPEN)

        cb.record_success()
        self.assertEqual(cb.state, CircuitState.CLOSED)

    def test_retry_with_backoff_decorator_exists(self):
        from backend.reliability.circuit_breaker import retry_with_backoff
        self.assertTrue(callable(retry_with_backoff))


# ============================================================================
# 5. Structured Logging — JSON Output
# ============================================================================
class TestStructuredLogging(unittest.TestCase):
    """Verify structured logging formatter produces valid JSON."""

    def test_formatter_produces_json(self):
        from backend.observability.log_config import StructuredFormatter
        formatter = StructuredFormatter()
        record = logging.LogRecord(
            name="test", level=logging.INFO,
            pathname="test.py", lineno=1,
            msg="Test message", args=(), exc_info=None,
        )
        output = formatter.format(record)
        parsed = json.loads(output)
        self.assertEqual(parsed["level"], "INFO")
        self.assertIn("Test message", parsed["msg"])

    def test_secret_redaction(self):
        from backend.observability.log_config import _redact
        result = _redact("password=hunter2")
        self.assertNotIn("hunter2", result)
        self.assertIn("[REDACTED]", result)

    def test_configure_logging_importable(self):
        from backend.observability.log_config import configure_logging
        self.assertTrue(callable(configure_logging))


# ============================================================================
# 6. Auth Guard — Preflight Checks
# ============================================================================
class TestPreflightChecks(unittest.TestCase):
    """Verify preflight checks fail on weak secrets."""

    def test_missing_jwt_secret_fails(self):
        from backend.auth.auth_guard import preflight_check_secrets
        env = {k: v for k, v in os.environ.items()
               if k not in ("JWT_SECRET", "YGB_HMAC_SECRET", "YGB_VIDEO_JWT_SECRET")}
        with patch.dict(os.environ, env, clear=True):
            with self.assertRaises(RuntimeError):
                preflight_check_secrets()

    def test_placeholder_secret_fails(self):
        from backend.auth.auth_guard import preflight_check_secrets
        env = {k: v for k, v in os.environ.items()}
        env["JWT_SECRET"] = "changeme"
        env["YGB_HMAC_SECRET"] = "changeme"
        env["YGB_VIDEO_JWT_SECRET"] = "changeme"
        with patch.dict(os.environ, env, clear=True):
            with self.assertRaises(RuntimeError):
                preflight_check_secrets()


# ============================================================================
# 7. Dependency Checker — CheckResult Type
# ============================================================================
class TestDependencyChecker(unittest.TestCase):
    """Verify dependency checker produces typed results."""

    def test_check_result_is_namedtuple(self):
        from backend.reliability.dependency_checker import CheckResult
        result = CheckResult("test", True, 1.5, "ok")
        self.assertEqual(result.name, "test")
        self.assertTrue(result.ok)
        self.assertEqual(result.latency_ms, 1.5)

    def test_run_all_checks_returns_dict(self):
        from backend.reliability.dependency_checker import run_all_checks
        result = run_all_checks(timeout_per_check=2.0)
        self.assertIn("ready", result)
        self.assertIn("total_latency_ms", result)
        self.assertIn("checks", result)
        self.assertIsInstance(result["checks"], list)

    def test_config_check_passes_with_hmac(self):
        from backend.reliability.dependency_checker import _check_config_integrity
        result = _check_config_integrity()
        # If YGB_HMAC_SECRET is set in env, this should pass
        if os.environ.get("YGB_HMAC_SECRET"):
            self.assertTrue(result.ok)
        else:
            self.assertFalse(result.ok)


# ============================================================================
# 8. Reliability Gate — Script Importability
# ============================================================================
class TestReliabilityGate(unittest.TestCase):
    """Verify reliability gate script is importable and runs."""

    def test_gate_importable(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "reliability_gate",
            str(PROJECT_ROOT.parent / "scripts" / "reliability_gate.py"),
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        self.assertTrue(hasattr(mod, "run_gate"))
        self.assertTrue(callable(mod.run_gate))

    def test_gate_returns_report(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "reliability_gate",
            str(PROJECT_ROOT.parent / "scripts" / "reliability_gate.py"),
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        report = mod.run_gate()
        self.assertIn("passed", report)
        self.assertIn("checks", report)
        self.assertIsInstance(report["checks"], list)


# ============================================================================
# 9. Measurement Completeness
# ============================================================================
class TestMeasurementCompleteness(unittest.TestCase):
    """Verify measurement completeness functions work correctly."""

    def test_full_completeness(self):
        from backend.observability.metrics import get_measurement_completeness
        data = {"a": 1, "b": 2, "c": 3}
        ratio = get_measurement_completeness(data, ["a", "b", "c"])
        self.assertEqual(ratio, 1.0)

    def test_partial_completeness(self):
        from backend.observability.metrics import get_measurement_completeness
        data = {"a": 1, "b": None}
        ratio = get_measurement_completeness(data, ["a", "b"])
        self.assertEqual(ratio, 0.5)

    def test_null_metric_ratio(self):
        from backend.observability.metrics import get_null_metric_ratio
        data = {"a": 1, "b": None, "c": None}
        ratio = get_null_metric_ratio(data, ["a", "b", "c"])
        self.assertAlmostEqual(ratio, 2/3, places=2)


# ============================================================================
# 10. Training State Manager — No Mock Data
# ============================================================================
class TestTrainingStateManagerNoMocks(unittest.TestCase):
    """Verify training state never returns fabricated data."""

    def test_idle_metrics_are_null(self):
        from backend.training.state_manager import TrainingStateManager
        mgr = TrainingStateManager()
        metrics = mgr.get_training_progress()
        self.assertIn(metrics.status, ("idle", "error"))
        # Active training metrics should be None when idle
        self.assertIsNone(metrics.loss)
        self.assertIsNone(metrics.throughput)

    def test_emit_training_metrics_exists(self):
        from backend.training.state_manager import TrainingStateManager
        mgr = TrainingStateManager()
        self.assertTrue(hasattr(mgr, "emit_training_metrics"))


if __name__ == "__main__":
    unittest.main()
