"""
Incident Reconciler Tests — backend/governance/incident_reconciler.py

Coverage targets:
- Missing auto_mode_state.json
- No incidents + no_drift=true (consistent)
- Incidents present + no_drift=true without window (inconsistent)
- Incidents present + no_drift=true with window (scoped, OK)
- Incidents present + no_drift=false (consistent)
- Timestamp freshness checks
- run_reconciliation() entry point
- ReconciliationReport structure
"""

import json
import os
import sys
import tempfile
import unittest
from datetime import datetime, timezone, timedelta
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from backend.governance.incident_reconciler import (
    reconcile,
    run_reconciliation,
    ReconciliationReport,
    _load_json_file,
    _find_incident_files,
)


class TestReconciliationReport(unittest.TestCase):
    """Test ReconciliationReport data structure."""

    def test_default_state(self):
        report = ReconciliationReport()
        self.assertTrue(report.consistent)
        self.assertEqual(report.checks, [])
        self.assertEqual(report.warnings, [])
        self.assertEqual(report.errors, [])

    def test_add_passing_check(self):
        report = ReconciliationReport()
        report.add_check("test_check", True, "OK")
        self.assertTrue(report.consistent)
        self.assertEqual(len(report.checks), 1)
        self.assertTrue(report.checks[0]["passed"])

    def test_add_failing_check(self):
        report = ReconciliationReport()
        report.add_check("test_check", False, "FAILED")
        self.assertFalse(report.consistent)

    def test_to_dict(self):
        report = ReconciliationReport()
        report.add_check("c1", True, "ok")
        report.warnings.append("warn1")
        d = report.to_dict()
        self.assertIn("consistent", d)
        self.assertIn("checks", d)
        self.assertIn("warnings", d)
        self.assertIn("errors", d)
        self.assertIn("timestamp", d)
        self.assertTrue(d["consistent"])


class TestLoadJsonFile(unittest.TestCase):
    """Test JSON file loading helper."""

    def test_load_nonexistent(self):
        result = _load_json_file(Path("/nonexistent/file.json"))
        self.assertIsNone(result)

    def test_load_valid_json(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump({"key": "value"}, f)
            f.flush()
            path = Path(f.name)
        try:
            result = _load_json_file(path)
            self.assertEqual(result, {"key": "value"})
        finally:
            os.unlink(path)

    def test_load_invalid_json(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            f.write("not valid json {{{")
            f.flush()
            path = Path(f.name)
        try:
            result = _load_json_file(path)
            self.assertIsNone(result)
        finally:
            os.unlink(path)


class TestFindIncidentFiles(unittest.TestCase):
    """Test incident file discovery."""

    def test_no_incident_files(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            files = _find_incident_files(Path(tmpdir))
            self.assertEqual(files, [])

    def test_finds_incident_files(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create matching files
            (Path(tmpdir) / "incident_20260301.json").write_text("{}")
            (Path(tmpdir) / "incidents.json").write_text("{}")
            (Path(tmpdir) / "incident_log_001.json").write_text("{}")
            # Create non-matching file
            (Path(tmpdir) / "other_file.json").write_text("{}")

            files = _find_incident_files(Path(tmpdir))
            # Multiple glob patterns may overlap, so we check at least 3 found
            self.assertGreaterEqual(len(files), 3)
            # Verify no non-incident files included
            filenames = [f.name for f in files]
            self.assertNotIn("other_file.json", filenames)

    def test_nonexistent_directory(self):
        files = _find_incident_files(Path("/nonexistent/dir"))
        self.assertEqual(files, [])


class TestReconcile(unittest.TestCase):
    """Test reconciliation logic."""

    def test_missing_auto_mode_state(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            report = reconcile(
                reports_dir=Path(tmpdir),
                auto_mode_path=Path(tmpdir) / "auto_mode_state.json",
            )
            self.assertFalse(report.consistent)
            names = [c["name"] for c in report.checks]
            self.assertIn("auto_mode_state_exists", names)

    def test_no_incidents_no_drift_true(self):
        """Consistent: no incidents and no_drift_events=True."""
        with tempfile.TemporaryDirectory() as tmpdir:
            state_path = Path(tmpdir) / "auto_mode_state.json"
            state_path.write_text(json.dumps({
                "no_drift_events": True,
                "last_updated": datetime.now(timezone.utc).isoformat(),
            }))
            report = reconcile(reports_dir=Path(tmpdir), auto_mode_path=state_path)
            self.assertTrue(report.consistent)

    def test_incidents_and_no_drift_true_inconsistent(self):
        """Inconsistent: incidents exist but no_drift_events=True without window."""
        with tempfile.TemporaryDirectory() as tmpdir:
            state_path = Path(tmpdir) / "auto_mode_state.json"
            state_path.write_text(json.dumps({
                "no_drift_events": True,
                "last_updated": datetime.now(timezone.utc).isoformat(),
            }))
            # Create incident file
            (Path(tmpdir) / "incident_001.json").write_text(json.dumps({"type": "drift"}))

            report = reconcile(reports_dir=Path(tmpdir), auto_mode_path=state_path)
            self.assertFalse(report.consistent)
            self.assertTrue(any("INCONSISTENCY" in c["detail"] for c in report.checks))

    def test_incidents_and_no_drift_true_with_window(self):
        """Scoped: incidents exist, no_drift=True but with explicit window."""
        with tempfile.TemporaryDirectory() as tmpdir:
            state_path = Path(tmpdir) / "auto_mode_state.json"
            state_path.write_text(json.dumps({
                "no_drift_events": True,
                "drift_check_window": "last_24h",
                "last_updated": datetime.now(timezone.utc).isoformat(),
            }))
            (Path(tmpdir) / "incident_001.json").write_text(json.dumps({"type": "drift"}))

            report = reconcile(reports_dir=Path(tmpdir), auto_mode_path=state_path)
            self.assertTrue(report.consistent)
            self.assertTrue(any("scoped" in w.lower() or "window" in w.lower() for w in report.warnings))

    def test_incidents_and_no_drift_false(self):
        """Consistent: incidents exist and no_drift_events=False."""
        with tempfile.TemporaryDirectory() as tmpdir:
            state_path = Path(tmpdir) / "auto_mode_state.json"
            state_path.write_text(json.dumps({
                "no_drift_events": False,
                "last_updated": datetime.now(timezone.utc).isoformat(),
            }))
            (Path(tmpdir) / "incident_001.json").write_text(json.dumps({"type": "drift"}))

            report = reconcile(reports_dir=Path(tmpdir), auto_mode_path=state_path)
            self.assertTrue(report.consistent)

    def test_no_drift_field_missing(self):
        """No assertion: no_drift_events field not present."""
        with tempfile.TemporaryDirectory() as tmpdir:
            state_path = Path(tmpdir) / "auto_mode_state.json"
            state_path.write_text(json.dumps({
                "last_updated": datetime.now(timezone.utc).isoformat(),
            }))

            report = reconcile(reports_dir=Path(tmpdir), auto_mode_path=state_path)
            self.assertTrue(report.consistent)
            self.assertTrue(any("missing" in w.lower() for w in report.warnings))

    def test_stale_timestamp(self):
        """Stale auto_mode_state.json (>24h old)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            old_time = (datetime.now(timezone.utc) - timedelta(hours=48)).isoformat()
            state_path = Path(tmpdir) / "auto_mode_state.json"
            state_path.write_text(json.dumps({
                "no_drift_events": True,
                "last_updated": old_time,
            }))

            report = reconcile(reports_dir=Path(tmpdir), auto_mode_path=state_path)
            stale_checks = [c for c in report.checks if c["name"] == "state_freshness"]
            self.assertEqual(len(stale_checks), 1)
            self.assertFalse(stale_checks[0]["passed"])

    def test_fresh_timestamp(self):
        """Fresh auto_mode_state.json (<24h old)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            state_path = Path(tmpdir) / "auto_mode_state.json"
            state_path.write_text(json.dumps({
                "no_drift_events": True,
                "last_updated": datetime.now(timezone.utc).isoformat(),
            }))

            report = reconcile(reports_dir=Path(tmpdir), auto_mode_path=state_path)
            stale_checks = [c for c in report.checks if c["name"] == "state_freshness"]
            self.assertEqual(len(stale_checks), 1)
            self.assertTrue(stale_checks[0]["passed"])

    def test_no_timestamp_field(self):
        """No timestamp in auto_mode_state.json."""
        with tempfile.TemporaryDirectory() as tmpdir:
            state_path = Path(tmpdir) / "auto_mode_state.json"
            state_path.write_text(json.dumps({"no_drift_events": True}))

            report = reconcile(reports_dir=Path(tmpdir), auto_mode_path=state_path)
            self.assertTrue(any("timestamp" in w.lower() for w in report.warnings))


class TestRunReconciliation(unittest.TestCase):
    """Test run_reconciliation entry point."""

    def test_returns_dict(self):
        result = run_reconciliation()
        self.assertIsInstance(result, dict)
        self.assertIn("consistent", result)
        self.assertIn("checks", result)
        self.assertIn("timestamp", result)


if __name__ == "__main__":
    unittest.main()
