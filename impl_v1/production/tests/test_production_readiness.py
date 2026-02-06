"""
Production Readiness Tests
==========================

Tests for production-grade validation.
"""

import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from impl_v1.production.validation.large_scale_validation import (
    generate_large_scale_dataset,
    production_scan,
    calculate_production_metrics,
    SampleType,
)

from impl_v1.production.observability.metrics_exporter import (
    MetricsRegistry,
    SystemMetricsCollector,
    get_metrics,
)

from impl_v1.production.observability.alert_router import (
    AlertRouter,
    AlertSeverity,
    Alert,
)

from impl_v1.production.legal.jurisdiction_check import (
    JurisdictionChecker,
    ScopeValidation,
)

from impl_v1.production.legal.scope_enforcement_proof import (
    EvidenceChain,
    ScopeEnforcementProof,
)

from impl_v1.production.workflow.human_workflow_simulation import (
    generate_valid_reports,
    simulate_review,
    run_workflow_simulation,
)


class TestLargeScaleValidation(unittest.TestCase):
    """Test large-scale validation."""
    
    def test_generate_dataset(self):
        """Generate 16K sample dataset."""
        dataset = generate_large_scale_dataset()
        self.assertEqual(len(dataset), 16000)
    
    def test_sample_types(self):
        """All sample types present."""
        dataset = generate_large_scale_dataset()
        types = set(s.sample_type for s in dataset)
        self.assertEqual(len(types), 4)
    
    def test_production_scan(self):
        """Production scan returns result."""
        dataset = generate_large_scale_dataset()
        result = production_scan(dataset[0])
        self.assertIsNotNone(result.sample_id)


class TestMetricsExporter(unittest.TestCase):
    """Test Prometheus metrics exporter."""
    
    def test_registry_gauge(self):
        """Register gauge metric."""
        registry = MetricsRegistry()
        registry.gauge("test_metric", 42.0)
        self.assertEqual(len(registry.metrics), 1)
    
    def test_export_format(self):
        """Export in Prometheus format."""
        collector = SystemMetricsCollector()
        collector.collect_auto_mode_state(True)
        output = collector.export()
        self.assertIn("ygb_auto_mode_enabled", output)


class TestAlertRouter(unittest.TestCase):
    """Test alert routing."""
    
    def test_create_alert(self):
        """Create and route alert."""
        router = AlertRouter()
        alert = router.create_alert(
            AlertSeverity.LOW,
            "test",
            "Test alert",
        )
        self.assertEqual(len(router.processed), 1)
    
    def test_critical_alert_action(self):
        """Critical alerts trigger emergency actions."""
        router = AlertRouter()
        results = router.route(Alert(
            id="TEST",
            severity=AlertSeverity.CRITICAL,
            source="test",
            message="Critical test",
            timestamp="now",
            metadata={},
        ))
        self.assertIn("action_emergency_lock: OK", results)


class TestJurisdictionCheck(unittest.TestCase):
    """Test jurisdiction checking."""
    
    def test_no_scope_blocks(self):
        """No scope = blocked."""
        checker = JurisdictionChecker()
        checker.scope = None
        validation = checker.is_target_in_scope("example.com")
        self.assertFalse(validation.is_valid)


class TestWorkflowSimulation(unittest.TestCase):
    """Test human workflow simulation."""
    
    def test_generate_valid_reports(self):
        """Generate 100 valid reports."""
        reports = generate_valid_reports(100)
        self.assertEqual(len(reports), 100)
    
    def test_simulate_review(self):
        """Simulate review returns result."""
        reports = generate_valid_reports(1)
        result = simulate_review(reports[0])
        self.assertIsNotNone(result.outcome)
    
    def test_run_full_simulation(self):
        """Run full workflow simulation."""
        metrics, report = run_workflow_simulation()
        self.assertEqual(metrics.total_reports, 300)


if __name__ == "__main__":
    unittest.main()
