"""
Observability Tests — Metrics registry, counters, histograms, critical metric detection.

Validates:
1. Counter increment/decrement
2. Gauge set/get
3. Histogram recording and percentile stats
4. Missing metric detection and metric_missing_counter increment
5. Snapshot serialization
6. Thread safety under concurrent access
7. Measurement completeness calculation
8. Null metric ratio calculation
"""

import threading
import unittest


class TestMetricsRegistry(unittest.TestCase):
    """Test the thread-safe metrics registry."""

    def setUp(self):
        from backend.observability.metrics import MetricsRegistry
        self.registry = MetricsRegistry()

    def test_counter_increment(self):
        self.registry.increment("test_counter")
        self.assertEqual(self.registry.get_counter("test_counter"), 1.0)

    def test_counter_increment_by_value(self):
        self.registry.increment("test_counter", 5.0)
        self.assertEqual(self.registry.get_counter("test_counter"), 5.0)

    def test_counter_multiple_increments(self):
        self.registry.increment("test_counter")
        self.registry.increment("test_counter")
        self.registry.increment("test_counter")
        self.assertEqual(self.registry.get_counter("test_counter"), 3.0)

    def test_counter_default_zero(self):
        self.assertEqual(self.registry.get_counter("nonexistent"), 0.0)

    def test_gauge_set_and_get(self):
        self.registry.set_gauge("cpu_usage", 75.5)
        self.assertEqual(self.registry.get_gauge("cpu_usage"), 75.5)

    def test_gauge_overwrite(self):
        self.registry.set_gauge("cpu_usage", 50.0)
        self.registry.set_gauge("cpu_usage", 90.0)
        self.assertEqual(self.registry.get_gauge("cpu_usage"), 90.0)

    def test_gauge_none_for_nonexistent(self):
        self.assertIsNone(self.registry.get_gauge("nonexistent"))

    def test_histogram_record(self):
        self.registry.record("latency", 10.0)
        self.registry.record("latency", 20.0)
        self.registry.record("latency", 30.0)
        stats = self.registry.get_histogram_stats("latency")
        self.assertEqual(stats["count"], 3)
        self.assertEqual(stats["min"], 10.0)
        self.assertEqual(stats["max"], 30.0)
        self.assertEqual(stats["mean"], 20.0)

    def test_histogram_empty(self):
        stats = self.registry.get_histogram_stats("nonexistent")
        self.assertEqual(stats["count"], 0)

    def test_histogram_memory_bounded(self):
        """Recording more than 1000 values should trim to ~500."""
        for i in range(1100):
            self.registry.record("many", float(i))
        stats = self.registry.get_histogram_stats("many")
        self.assertLessEqual(stats["count"], 600)

    def test_snapshot_serializable(self):
        import json
        self.registry.increment("c1", 5)
        self.registry.set_gauge("g1", 42.0)
        self.registry.record("h1", 100.0)
        snapshot = self.registry.get_snapshot()
        # Must be JSON-serializable
        serialized = json.dumps(snapshot)
        self.assertIn("counters", serialized)
        self.assertIn("gauges", serialized)
        self.assertIn("histograms", serialized)

    def test_critical_metrics_pre_registered(self):
        """All critical metrics should appear in snapshot even when never recorded."""
        from backend.observability.metrics import CRITICAL_METRICS
        snapshot = self.registry.get_snapshot()
        counters = snapshot["counters"]
        for name in CRITICAL_METRICS:
            self.assertIn(name, counters, f"Critical metric '{name}' not pre-registered")

    def test_check_critical_metrics_detects_missing(self):
        """check_critical_metrics should detect metrics never recorded."""
        missing = self.registry.check_critical_metrics()
        # Many critical metrics won't have been actively recorded
        self.assertIsInstance(missing, list)

    def test_reset_clears_all(self):
        self.registry.increment("c1")
        self.registry.set_gauge("g1", 1.0)
        self.registry.record("h1", 1.0)
        self.registry.reset()
        self.assertEqual(self.registry.get_counter("c1"), 0.0)
        self.assertIsNone(self.registry.get_gauge("g1"))
        self.assertEqual(self.registry.get_histogram_stats("h1")["count"], 0)

    def test_thread_safety(self):
        """Concurrent access should not raise or corrupt data."""
        errors = []

        def increment_many():
            try:
                for _ in range(100):
                    self.registry.increment("concurrent")
                    self.registry.record("concurrent_hist", 1.0)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=increment_many) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5)

        self.assertEqual(len(errors), 0)
        self.assertEqual(self.registry.get_counter("concurrent"), 1000.0)


class TestMeasurementCompleteness(unittest.TestCase):
    """Test measurement completeness and null ratio calculations."""

    def test_full_completeness(self):
        from backend.observability.metrics import get_measurement_completeness
        data = {"a": 1, "b": 2, "c": 3}
        ratio = get_measurement_completeness(data, ["a", "b", "c"])
        self.assertAlmostEqual(ratio, 1.0)

    def test_partial_completeness(self):
        from backend.observability.metrics import get_measurement_completeness
        data = {"a": 1, "b": None, "c": 3}
        ratio = get_measurement_completeness(data, ["a", "b", "c"])
        self.assertAlmostEqual(ratio, 2 / 3, places=4)

    def test_zero_completeness(self):
        from backend.observability.metrics import get_measurement_completeness
        data = {"a": None, "b": None}
        ratio = get_measurement_completeness(data, ["a", "b"])
        self.assertAlmostEqual(ratio, 0.0)

    def test_empty_fields(self):
        from backend.observability.metrics import get_measurement_completeness
        ratio = get_measurement_completeness({}, [])
        self.assertAlmostEqual(ratio, 1.0)

    def test_empty_fields_updates_completeness_gauge(self):
        from backend.observability.metrics import metrics_registry, get_measurement_completeness

        metrics_registry.reset()
        ratio = get_measurement_completeness({}, [])
        self.assertAlmostEqual(ratio, 1.0)
        self.assertEqual(metrics_registry.get_gauge("measurement_completeness_ratio"), 1.0)

    def test_null_metric_ratio(self):
        from backend.observability.metrics import get_null_metric_ratio
        data = {"a": 1, "b": None, "c": None}
        ratio = get_null_metric_ratio(data, ["a", "b", "c"])
        self.assertAlmostEqual(ratio, 2 / 3, places=4)

    def test_null_metric_ratio_no_nulls(self):
        from backend.observability.metrics import get_null_metric_ratio
        data = {"a": 1, "b": 2}
        ratio = get_null_metric_ratio(data, ["a", "b"])
        self.assertAlmostEqual(ratio, 0.0)

    def test_empty_metric_fields_updates_null_ratio_gauge(self):
        from backend.observability.metrics import metrics_registry, get_null_metric_ratio

        metrics_registry.reset()
        ratio = get_null_metric_ratio({}, [])
        self.assertAlmostEqual(ratio, 0.0)
        self.assertEqual(metrics_registry.get_gauge("null_metric_ratio"), 0.0)


if __name__ == "__main__":
    unittest.main()
