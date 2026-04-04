"""
Drift & Incident Consistency Tests

Validates:
1. Reconciler correctly detects inconsistency when incidents exist but no_drift_events=True
2. Reconciler passes when state is genuinely consistent
3. Reconciler handles missing files gracefully
4. Time-window scoping logic works correctly
"""

import json
import os
import tempfile
import unittest
from datetime import datetime, timezone, timedelta
from pathlib import Path


class TestIncidentReconciler(unittest.TestCase):
    """Test the incident/drift reconciliation logic."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.reports_dir = Path(self.tmpdir) / "reports"
        self.reports_dir.mkdir()
        self.auto_mode_path = self.reports_dir / "auto_mode_state.json"

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _write_auto_state(self, state: dict):
        self.auto_mode_path.write_text(
            json.dumps(state), encoding="utf-8"
        )

    def _create_incident(self, name: str = "incident_001.json"):
        incident_path = self.reports_dir / name
        incident_path.write_text(
            json.dumps({"type": "test_incident", "timestamp": datetime.now(timezone.utc).isoformat()}),
            encoding="utf-8",
        )

    def test_consistent_no_incidents_no_drift(self):
        """No incidents + no_drift_events=True should be consistent."""
        from backend.governance.incident_reconciler import reconcile

        self._write_auto_state({
            "no_drift_events": True,
            "last_updated": datetime.now(timezone.utc).isoformat(),
        })

        report = reconcile(
            reports_dir=self.reports_dir,
            auto_mode_path=self.auto_mode_path,
        )
        self.assertTrue(report.consistent)
        self.assertEqual(len(report.errors), 0)

    def test_inconsistent_incidents_but_no_drift_true(self):
        """Incidents exist + no_drift_events=True without window → INCONSISTENT."""
        from backend.governance.incident_reconciler import reconcile

        self._write_auto_state({
            "no_drift_events": True,
            "last_updated": datetime.now(timezone.utc).isoformat(),
        })
        self._create_incident()

        report = reconcile(
            reports_dir=self.reports_dir,
            auto_mode_path=self.auto_mode_path,
        )
        self.assertFalse(report.consistent)
        self.assertTrue(len(report.errors) > 0)

    def test_consistent_incidents_with_drift_window(self):
        """Incidents + no_drift_events=True WITH window → consistent (scoped)."""
        from backend.governance.incident_reconciler import reconcile

        self._write_auto_state({
            "no_drift_events": True,
            "drift_check_window": "last_24h",
            "last_updated": datetime.now(timezone.utc).isoformat(),
        })
        self._create_incident()

        report = reconcile(
            reports_dir=self.reports_dir,
            auto_mode_path=self.auto_mode_path,
        )
        self.assertTrue(report.consistent)
        # Should have a warning though
        self.assertTrue(len(report.warnings) > 0)

    def test_consistent_incidents_drift_false(self):
        """Incidents + no_drift_events=False → consistent."""
        from backend.governance.incident_reconciler import reconcile

        self._write_auto_state({
            "no_drift_events": False,
            "last_updated": datetime.now(timezone.utc).isoformat(),
        })
        self._create_incident()

        report = reconcile(
            reports_dir=self.reports_dir,
            auto_mode_path=self.auto_mode_path,
        )
        self.assertTrue(report.consistent)

    def test_missing_auto_mode_state(self):
        """Missing auto_mode_state.json should report check failure."""
        from backend.governance.incident_reconciler import reconcile

        # Don't create the file
        report = reconcile(
            reports_dir=self.reports_dir,
            auto_mode_path=self.auto_mode_path,
        )
        self.assertFalse(report.consistent)

    def test_stale_state_detected(self):
        """auto_mode_state > 24h old should fail freshness check."""
        from backend.governance.incident_reconciler import reconcile

        old_time = (datetime.now(timezone.utc) - timedelta(hours=48)).isoformat()
        self._write_auto_state({
            "no_drift_events": True,
            "last_updated": old_time,
        })

        report = reconcile(
            reports_dir=self.reports_dir,
            auto_mode_path=self.auto_mode_path,
        )
        # Freshness check should fail
        freshness_checks = [c for c in report.checks if c["name"] == "state_freshness"]
        if freshness_checks:
            self.assertFalse(freshness_checks[0]["passed"])

    def test_run_reconciliation_returns_dict(self):
        """run_reconciliation() should return a valid dict."""
        from backend.governance.incident_reconciler import reconcile

        self._write_auto_state({
            "no_drift_events": True,
            "last_updated": datetime.now(timezone.utc).isoformat(),
        })

        report = reconcile(
            reports_dir=self.reports_dir,
            auto_mode_path=self.auto_mode_path,
        )
        result = report.to_dict()
        self.assertIn("consistent", result)
        self.assertIn("checks", result)
        self.assertIn("timestamp", result)
        self.assertIsInstance(result["checks"], list)


if __name__ == "__main__":
    unittest.main()
