"""
Report Generator API Tests

Tests for report CRUD and video recording metadata lifecycle.
"""

import unittest
import json
import os
import sys
import sqlite3
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))


class TestReportGeneratorModule(unittest.TestCase):
    """Test the report generator module exists and has expected structure."""

    def test_module_imports(self):
        """Report generator module should import without errors."""
        from backend.api.report_generator import router
        self.assertIsNotNone(router)

    def test_router_has_expected_routes(self):
        """Router should register the expected endpoints."""
        from backend.api.report_generator import router
        routes = [r.path for r in router.routes]
        self.assertIn("/api/reports", routes, "POST/GET /api/reports should be registered")
        self.assertIn("/api/reports/videos/start", routes, "POST /api/reports/videos/start")
        self.assertIn("/api/reports/videos/{video_id}/stop", routes, "POST /api/reports/videos/{id}/stop")
        self.assertIn("/api/reports/videos", routes, "GET /api/reports/videos")
        self.assertIn("/api/reports/{report_id}", routes, "GET /api/reports/{id}")
        self.assertIn("/api/reports/{report_id}/content", routes, "GET /api/reports/{id}/content")

    def test_generate_id_format(self):
        """Generated IDs should have the correct prefix format."""
        from backend.api.report_generator import _generate_id
        rid = _generate_id("rpt")
        self.assertTrue(rid.startswith("rpt-"))
        self.assertEqual(len(rid), 4 + 16, "Should be prefix-16hexchars")

    def test_now_iso_format(self):
        """ISO timestamps should be properly formatted."""
        from backend.api.report_generator import _now_iso
        ts = _now_iso()
        self.assertIn("T", ts)
        self.assertTrue(ts.endswith("+00:00") or ts.endswith("Z"))


class TestReportTablesCreation(unittest.TestCase):
    """Test database table creation for reports and video recordings."""

    def test_ensure_tables_creates_schema(self):
        """_ensure_tables should create both tables without errors."""
        from backend.api import report_generator as rg
        # Reset global flag to force recreation
        rg._TABLES_CREATED = False

        # This depends on get_db_connection — if DB unavailable, should not crash
        try:
            rg._ensure_tables()
        except Exception as e:
            self.fail(f"_ensure_tables should not raise: {e}")

    def test_no_mock_keywords_in_source(self):
        """Report generator source should contain no mock/fake flags."""
        import inspect
        from backend.api import report_generator
        source = inspect.getsource(report_generator)
        forbidden = ["MOCK_", "FAKE_", "DEMO_", "simulated =", "random."]
        for pattern in forbidden:
            self.assertNotIn(
                pattern, source,
                f"Production code must not contain '{pattern}'"
            )


class TestVideoRecordingMetadata(unittest.TestCase):
    """Test video recording metadata helpers."""

    def test_video_id_format(self):
        """Video IDs should have vid- prefix."""
        from backend.api.report_generator import _generate_id
        vid = _generate_id("vid")
        self.assertTrue(vid.startswith("vid-"))

    def test_unique_ids(self):
        """Each generated ID should be unique."""
        from backend.api.report_generator import _generate_id
        ids = {_generate_id("vid") for _ in range(100)}
        self.assertEqual(len(ids), 100, "All 100 IDs should be unique")


if __name__ == "__main__":
    unittest.main()
