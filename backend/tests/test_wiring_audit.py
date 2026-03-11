"""
Wiring Audit Test — verifies end-to-end metric wiring, health probe structure,
and critical-metric registration across the YGB system.

Covers:
  - Metrics registry singleton initialization
  - Critical metric registration
  - Infrastructure vs training-only metric classification
  - Health endpoint structure (/healthz, /readyz)
  - Dependency checker includes all required sub-checks
  - Voice and report latency metrics can be recorded
"""

import os
import sys
import pytest

# Ensure project root is on path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

os.environ.setdefault("YGB_HMAC_SECRET", "test-hmac-secret-for-audit")


# =============================================================================
# METRICS REGISTRY WIRING
# =============================================================================

class TestMetricsRegistryWiring:
    """Verify the observability metrics registry is correctly wired."""

    def test_singleton_exists(self):
        from backend.observability.metrics import metrics_registry
        assert metrics_registry is not None

    def test_critical_metrics_registered(self):
        from backend.observability.metrics import (
            metrics_registry, CRITICAL_METRICS,
        )
        snapshot = metrics_registry.get_snapshot()
        counters = snapshot.get("counters", {})
        # All critical metrics should be pre-registered as counters
        for name in CRITICAL_METRICS:
            assert name in counters, f"Critical metric '{name}' not pre-registered"

    def test_infrastructure_vs_training_split(self):
        from backend.observability.metrics import (
            INFRASTRUCTURE_METRICS, TRAINING_ONLY_METRICS, CRITICAL_METRICS,
        )
        # Infrastructure and training-only must be disjoint
        overlap = INFRASTRUCTURE_METRICS & TRAINING_ONLY_METRICS
        assert len(overlap) == 0, f"Overlap: {overlap}"
        # Combined must equal CRITICAL_METRICS
        assert INFRASTRUCTURE_METRICS | TRAINING_ONLY_METRICS == CRITICAL_METRICS

    def test_check_critical_metrics_only_flags_infrastructure(self):
        """check_critical_metrics() should NOT flag training-only metrics."""
        from backend.observability.metrics import (
            MetricsRegistry, TRAINING_ONLY_METRICS,
        )
        fresh = MetricsRegistry()
        missing = fresh.check_critical_metrics()
        # Training-only metrics should NOT appear in the missing list
        for name in TRAINING_ONLY_METRICS:
            assert name not in missing, (
                f"Training-only metric '{name}' should not be flagged as missing"
            )

    def test_record_voice_latency(self):
        from backend.observability.metrics import metrics_registry
        metrics_registry.record("voice_inference_latency_ms", 42.0)
        stats = metrics_registry.get_histogram_stats("voice_inference_latency_ms")
        assert stats["count"] >= 1

    def test_record_report_latency(self):
        from backend.observability.metrics import metrics_registry
        metrics_registry.record("report_generation_latency_ms", 15.0)
        stats = metrics_registry.get_histogram_stats("report_generation_latency_ms")
        assert stats["count"] >= 1

    def test_record_training_latency(self):
        from backend.observability.metrics import metrics_registry
        metrics_registry.record("training_latency_ms", 5000.0)
        stats = metrics_registry.get_histogram_stats("training_latency_ms")
        assert stats["count"] >= 1

    def test_snapshot_is_json_serializable(self):
        import json
        from backend.observability.metrics import metrics_registry
        snapshot = metrics_registry.get_snapshot()
        # Must not raise
        serialized = json.dumps(snapshot)
        assert len(serialized) > 10


# =============================================================================
# DEPENDENCY CHECKER WIRING
# =============================================================================

class TestDependencyCheckerWiring:
    """Verify readiness dependency checks include all required sub-checks."""

    def test_builtin_checks_include_storage(self):
        from backend.reliability.dependency_checker import _BUILTIN_CHECKS
        names = [getattr(fn, "__name__", str(fn)) for fn in _BUILTIN_CHECKS]
        assert "_check_storage" in names

    def test_builtin_checks_include_revocation(self):
        from backend.reliability.dependency_checker import _BUILTIN_CHECKS
        names = [getattr(fn, "__name__", str(fn)) for fn in _BUILTIN_CHECKS]
        assert "_check_revocation_backend" in names

    def test_builtin_checks_include_config(self):
        from backend.reliability.dependency_checker import _BUILTIN_CHECKS
        names = [getattr(fn, "__name__", str(fn)) for fn in _BUILTIN_CHECKS]
        assert "_check_config_integrity" in names

    def test_builtin_checks_include_metrics(self):
        from backend.reliability.dependency_checker import _BUILTIN_CHECKS
        names = [getattr(fn, "__name__", str(fn)) for fn in _BUILTIN_CHECKS]
        assert "_check_metrics_registry" in names

    def test_run_all_checks_returns_structure(self):
        from backend.reliability.dependency_checker import run_all_checks
        result = run_all_checks(timeout_per_check=3.0)
        assert "ready" in result
        assert "total_latency_ms" in result
        assert "checks" in result
        assert isinstance(result["checks"], list)
        assert len(result["checks"]) >= 4

    def test_each_check_returns_required_fields(self):
        from backend.reliability.dependency_checker import run_all_checks
        result = run_all_checks(timeout_per_check=3.0)
        for check in result["checks"]:
            assert "name" in check, f"Check missing 'name': {check}"
            assert "ok" in check, f"Check missing 'ok': {check}"
            assert "latency_ms" in check, f"Check missing 'latency_ms': {check}"
            assert "detail" in check, f"Check missing 'detail': {check}"


# =============================================================================
# HEALTH ENDPOINT STRUCTURE
# =============================================================================

class TestHealthEndpointStructure:
    """Verify health endpoint router is importable and correctly configured."""

    def test_health_router_exists(self):
        from backend.reliability.health_endpoints import health_router
        assert health_router is not None

    def test_health_router_has_healthz(self):
        from backend.reliability.health_endpoints import health_router
        routes = [r.path for r in health_router.routes]
        assert "/healthz" in routes

    def test_health_router_has_readyz(self):
        from backend.reliability.health_endpoints import health_router
        routes = [r.path for r in health_router.routes]
        assert "/readyz" in routes


# =============================================================================
# CIRCUIT BREAKER WIRING
# =============================================================================

class TestCircuitBreakerWiring:
    """Verify circuit breaker module is importable and functional."""

    def test_circuit_breaker_import(self):
        from backend.reliability.circuit_breaker import CircuitBreaker, CircuitState
        cb = CircuitBreaker("test_audit")
        assert cb.state == CircuitState.CLOSED

    def test_retry_decorator_import(self):
        from backend.reliability.circuit_breaker import retry_with_backoff
        assert callable(retry_with_backoff)
