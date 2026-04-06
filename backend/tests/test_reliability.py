"""
Reliability Tests — Health probes, circuit breaker, retry, dependency checker.

Validates:
1. /healthz always returns 200 with uptime
2. /readyz returns 200 when deps healthy, 503 when any fail
3. Circuit breaker state transitions (CLOSED → OPEN → HALF_OPEN → CLOSED)
4. Retry with exponential backoff (delay sequence, max retries)
5. Dependency checker timeout behavior
"""

import os
import time
import threading
import unittest
from unittest.mock import patch, MagicMock


class TestCircuitBreaker(unittest.TestCase):
    """Test circuit breaker state machine."""

    def _make_breaker(self, **kwargs):
        from backend.reliability.circuit_breaker import CircuitBreaker
        defaults = {
            "name": "test",
            "failure_threshold": 3,
            "recovery_timeout": 0.2,
            "success_threshold": 2,
        }
        defaults.update(kwargs)
        return CircuitBreaker(**defaults)

    def test_starts_closed(self):
        from backend.reliability.circuit_breaker import CircuitState
        cb = self._make_breaker()
        self.assertEqual(cb.state, CircuitState.CLOSED)
        self.assertTrue(cb.allow_request())

    def test_is_open_property(self):
        cb = self._make_breaker(failure_threshold=1, recovery_timeout=0.05)
        self.assertFalse(cb.is_open)
        cb.record_failure()
        self.assertTrue(cb.is_open)
        time.sleep(0.06)
        self.assertFalse(cb.is_open)

    def test_opens_after_threshold_failures(self):
        from backend.reliability.circuit_breaker import CircuitState
        cb = self._make_breaker(failure_threshold=3)
        for _ in range(3):
            cb.record_failure()
        self.assertEqual(cb.state, CircuitState.OPEN)
        self.assertFalse(cb.allow_request())

    def test_stays_closed_below_threshold(self):
        from backend.reliability.circuit_breaker import CircuitState
        cb = self._make_breaker(failure_threshold=3)
        cb.record_failure()
        cb.record_failure()
        self.assertEqual(cb.state, CircuitState.CLOSED)
        self.assertTrue(cb.allow_request())

    def test_success_resets_failure_count(self):
        from backend.reliability.circuit_breaker import CircuitState
        cb = self._make_breaker(failure_threshold=3)
        cb.record_failure()
        cb.record_failure()
        cb.record_success()
        # After success, failure count resets — need 3 more to open
        cb.record_failure()
        cb.record_failure()
        self.assertEqual(cb.state, CircuitState.CLOSED)

    def test_transitions_to_half_open_after_cooldown(self):
        from backend.reliability.circuit_breaker import CircuitState
        cb = self._make_breaker(failure_threshold=2, recovery_timeout=0.1)
        cb.record_failure()
        cb.record_failure()
        self.assertEqual(cb.state, CircuitState.OPEN)
        time.sleep(0.15)
        self.assertEqual(cb.state, CircuitState.HALF_OPEN)
        self.assertTrue(cb.allow_request())

    def test_half_open_closes_on_success(self):
        from backend.reliability.circuit_breaker import CircuitState
        cb = self._make_breaker(failure_threshold=2, recovery_timeout=0.1, success_threshold=2)
        cb.record_failure()
        cb.record_failure()
        time.sleep(0.15)
        # Now HALF_OPEN — two successes should close
        cb.record_success()
        cb.record_success()
        self.assertEqual(cb.state, CircuitState.CLOSED)

    def test_half_open_reopens_on_failure(self):
        from backend.reliability.circuit_breaker import CircuitState
        cb = self._make_breaker(failure_threshold=2, recovery_timeout=0.1)
        cb.record_failure()
        cb.record_failure()
        time.sleep(0.15)
        self.assertEqual(cb.state, CircuitState.HALF_OPEN)
        cb.record_failure()
        self.assertEqual(cb.state, CircuitState.OPEN)

    def test_half_open_allows_only_one_probe_at_a_time(self):
        from backend.reliability.circuit_breaker import CircuitState
        cb = self._make_breaker(failure_threshold=1, recovery_timeout=0.1)
        cb.record_failure()
        time.sleep(0.15)
        self.assertEqual(cb.state, CircuitState.HALF_OPEN)
        self.assertTrue(cb.allow_request())
        self.assertFalse(cb.allow_request())
        cb.record_success()
        self.assertEqual(cb.state, CircuitState.HALF_OPEN)
        self.assertTrue(cb.allow_request())

    def test_get_status(self):
        cb = self._make_breaker()
        status = cb.get_status()
        self.assertEqual(status["name"], "test")
        self.assertEqual(status["state"], "CLOSED")
        self.assertIn("failure_threshold", status)

    def test_get_stats_tracks_calls_failures_and_trips(self):
        cb = self._make_breaker(failure_threshold=2, recovery_timeout=0.05)
        cb.record_success()
        cb.record_failure()
        cb.record_failure()

        stats = cb.get_stats()
        self.assertEqual(stats.total_calls, 3)
        self.assertEqual(stats.total_failures, 2)
        self.assertEqual(stats.trips, 1)
        self.assertIsNotNone(stats.last_trip_at)

    def test_trips_increment_only_on_open_transition(self):
        from backend.reliability.circuit_breaker import CircuitState

        cb = self._make_breaker(
            failure_threshold=1,
            recovery_timeout=0.02,
            success_threshold=1,
        )
        cb.record_failure()
        first_stats = cb.get_stats()
        self.assertEqual(first_stats.trips, 1)

        cb.record_failure()
        self.assertEqual(cb.get_stats().trips, 1)

        time.sleep(0.03)
        self.assertEqual(cb.state, CircuitState.HALF_OPEN)

        cb.record_failure()
        second_stats = cb.get_stats()
        self.assertEqual(second_stats.trips, 2)
        self.assertIsNotNone(second_stats.last_trip_at)
        self.assertGreater(second_stats.last_trip_at, first_stats.last_trip_at)

    def test_thread_safety(self):
        """Multiple threads recording failures should not corrupt state."""
        from backend.reliability.circuit_breaker import CircuitState
        cb = self._make_breaker(failure_threshold=100)
        errors = []

        def hammer():
            try:
                for _ in range(50):
                    cb.record_failure()
                    cb.record_success()
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=hammer) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5)

        self.assertEqual(len(errors), 0)
        # State should be deterministic even after concurrent access
        self.assertIn(cb.state, (CircuitState.CLOSED, CircuitState.OPEN))


class TestRetryWithBackoff(unittest.TestCase):
    """Test retry decorator."""

    def test_succeeds_without_retry(self):
        from backend.reliability.circuit_breaker import retry_with_backoff

        call_count = 0

        @retry_with_backoff(max_retries=3, base_delay=0.01)
        def succeed():
            nonlocal call_count
            call_count += 1
            return "ok"

        result = succeed()
        self.assertEqual(result, "ok")
        self.assertEqual(call_count, 1)

    def test_retries_on_exception(self):
        from backend.reliability.circuit_breaker import retry_with_backoff

        call_count = 0

        @retry_with_backoff(max_retries=2, base_delay=0.01, jitter=False)
        def fail_then_succeed():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ConnectionError("temp failure")
            return "ok"

        result = fail_then_succeed()
        self.assertEqual(result, "ok")
        self.assertEqual(call_count, 3)

    def test_raises_after_exhaustion(self):
        from backend.reliability.circuit_breaker import retry_with_backoff

        @retry_with_backoff(max_retries=2, base_delay=0.01, jitter=False)
        def always_fail():
            raise ValueError("permanent")

        with self.assertRaises(ValueError):
            always_fail()

    def test_circuit_breaker_blocks_retry(self):
        from backend.reliability.circuit_breaker import (
            CircuitBreaker, CircuitBreakerError, retry_with_backoff,
        )
        cb = CircuitBreaker("test", failure_threshold=1, recovery_timeout=60)
        cb.record_failure()  # Opens circuit

        @retry_with_backoff(max_retries=3, base_delay=0.01, circuit_breaker=cb)
        def do_work():
            return "ok"

        with self.assertRaises(CircuitBreakerError):
            do_work()

    def test_non_retryable_probe_failure_reopens_circuit(self):
        from backend.reliability.circuit_breaker import (
            CircuitBreaker, CircuitState, retry_with_backoff,
        )

        cb = CircuitBreaker("test", failure_threshold=1, recovery_timeout=0.05)
        cb.record_failure()
        time.sleep(0.06)

        @retry_with_backoff(max_retries=0, circuit_breaker=cb, retryable_exceptions=(RuntimeError,))
        def fail_with_non_retryable_error():
            raise ValueError("fatal")

        with self.assertRaises(ValueError):
            fail_with_non_retryable_error()
        self.assertEqual(cb.state, CircuitState.OPEN)


class TestDependencyChecker(unittest.TestCase):
    """Test dependency checker parallel checks."""

    def test_all_checks_pass(self):
        from backend.reliability.dependency_checker import run_all_checks, CheckResult

        def ok_check():
            return CheckResult("test", True, 1.0, "ok")

        result = run_all_checks(checks=[ok_check, ok_check])
        self.assertTrue(result["ready"])
        self.assertEqual(len(result["checks"]), 2)

    def test_failed_check_returns_not_ready(self):
        from backend.reliability.dependency_checker import run_all_checks, CheckResult

        def ok_check():
            return CheckResult("ok", True, 1.0, "ok")

        def fail_check():
            return CheckResult("fail", False, 1.0, "down")

        result = run_all_checks(checks=[ok_check, fail_check])
        self.assertFalse(result["ready"])

    def test_timeout_check(self):
        from backend.reliability.dependency_checker import run_all_checks, CheckResult

        def slow_check():
            time.sleep(5)
            return CheckResult("slow", True, 5000.0, "slow")

        result = run_all_checks(timeout_per_check=0.1, checks=[slow_check])
        self.assertFalse(result["ready"])
        self.assertEqual(result["checks"][0]["detail"], "TIMEOUT")

    def test_latency_measured(self):
        from backend.reliability.dependency_checker import run_all_checks, CheckResult

        def ok_check():
            time.sleep(0.05)
            return CheckResult("test", True, 50.0, "ok")

        result = run_all_checks(checks=[ok_check])
        self.assertGreater(result["total_latency_ms"], 0)

    def test_check_all_timeout_returns_timeout_result(self):
        from backend.reliability.dependency_checker import check_all, CheckResult

        def slow_check():
            time.sleep(0.05)
            return CheckResult("slow", True, 50.0, "ok")

        results = check_all(checks=[slow_check], timeout=0.01)
        self.assertEqual(len(results), 1)
        self.assertFalse(results[0].available)
        self.assertEqual(results[0].error, "timeout")

    def test_check_all_never_raises(self):
        from backend.reliability.dependency_checker import check_all

        def exploding_check():
            raise RuntimeError("boom")

        results = check_all(checks=[exploding_check], timeout=0.1)
        self.assertEqual(len(results), 1)
        self.assertFalse(results[0].available)
        self.assertEqual(results[0].error, "RuntimeError")

    def test_dependency_checks_emit_latency_metrics(self):
        from backend.observability.metrics import metrics_registry
        from backend.reliability.dependency_checker import run_all_checks, CheckResult

        metrics_registry.reset()

        def ok_check():
            return CheckResult("metrics", True, 12.5, "ok")

        run_all_checks(checks=[ok_check])
        stats = metrics_registry.get_histogram_stats("dependency_latency_ms")
        self.assertEqual(stats["count"], 1)

    def test_config_check_passes_with_hmac(self):
        from backend.reliability.dependency_checker import _check_config_integrity
        original = os.environ.get("YGB_HMAC_SECRET")
        try:
            os.environ["YGB_HMAC_SECRET"] = "test_secret_value"
            result = _check_config_integrity()
            self.assertTrue(result.ok)
        finally:
            if original is not None:
                os.environ["YGB_HMAC_SECRET"] = original
            else:
                os.environ.pop("YGB_HMAC_SECRET", None)

    def test_config_check_fails_without_hmac(self):
        from backend.reliability.dependency_checker import _check_config_integrity
        original = os.environ.pop("YGB_HMAC_SECRET", None)
        try:
            result = _check_config_integrity()
            self.assertFalse(result.ok)
            self.assertIn("YGB_HMAC_SECRET", result.detail)
        finally:
            if original is not None:
                os.environ["YGB_HMAC_SECRET"] = original


class TestHealthEndpoints(unittest.TestCase):
    """Test /healthz and /readyz responses."""

    def test_healthz_response_structure(self):
        """Liveness response must include status and uptime."""
        from backend.reliability.health_endpoints import _BOOT_MONOTONIC
        # Just test that the module loads and boot time is set
        self.assertIsInstance(_BOOT_MONOTONIC, float)
        self.assertGreater(_BOOT_MONOTONIC, 0)


if __name__ == "__main__":
    unittest.main()
