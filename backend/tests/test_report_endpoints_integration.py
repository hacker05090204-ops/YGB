"""
FastAPI TestClient integration tests for report_generator endpoints.

Uses a REAL SQLite file-backed database and bypasses auth with the
temporary auth bypass mode. Tests the actual HTTP endpoints end-to-end.
"""

import json
import os
import sqlite3
import tempfile
import unittest
from datetime import datetime
from unittest.mock import patch

from fastapi.testclient import TestClient


class TestReportEndpointsRealDB(unittest.TestCase):
    """Test report_generator endpoints via FastAPI TestClient with real DB."""

    @classmethod
    def setUpClass(cls):
        """Create a temp DB and configure the app."""
        cls.tmp_dir = tempfile.mkdtemp()
        cls.db_path = os.path.join(cls.tmp_dir, "test_reports.db")

        # Patch env BEFORE importing the app
        cls.env_patches = {
            "DATABASE_URL": f"sqlite:///{cls.db_path}",
            "YGB_TEMP_AUTH_BYPASS": "true",
            "YGB_HDD_ROOT": cls.tmp_dir,
            "YGB_REPORT_OUTPUT_DIR": os.path.join(cls.tmp_dir, "generated_reports"),
        }
        cls.patcher = patch.dict(os.environ, cls.env_patches)
        cls.patcher.start()

        # Reset _TABLES_CREATED flag
        from backend.api import report_generator
        report_generator._TABLES_CREATED = False

        # Create app with the report router
        from fastapi import FastAPI
        app = FastAPI()
        app.include_router(report_generator.router)
        cls.client = TestClient(app)

    @classmethod
    def tearDownClass(cls):
        cls.patcher.stop()
        from backend.api import report_generator
        report_generator._TABLES_CREATED = False
        if os.path.exists(cls.db_path):
            os.unlink(cls.db_path)
        import shutil
        shutil.rmtree(cls.tmp_dir, ignore_errors=True)

    def test_create_report_success(self):
        """POST /api/reports — create a real report."""
        resp = self.client.post("/api/reports", json={
            "title": "SQL Injection in Login",
            "description": "Union-based SQL injection in login endpoint",
            "report_type": "security",
            "content": {"severity": "critical", "cvss": 9.8},
            "metadata": {"source": "manual_test"},
        })
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data["success"])
        self.assertTrue(data["report"]["id"].startswith("rpt-"))
        self.assertEqual(data["report"]["title"], "SQL Injection in Login")
        self.assertEqual(data["report"]["status"], "draft")
        self.assertEqual(data["report"]["generator_version"], "1.0")
        self.assertEqual(len(data["report"]["sha256"]), 64)
        self.assertIsNotNone(
            datetime.fromisoformat(data["report"]["generated_at"].replace("Z", "+00:00"))
        )

        # Save the ID for later tests
        self.__class__.created_report_id = data["report"]["id"]

    def test_create_report_no_title(self):
        """POST /api/reports — should fail without title."""
        resp = self.client.post("/api/reports", json={
            "title": "",
            "description": "No title",
        })
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.json()["detail"]["error"], "VALIDATION_ERROR")

    def test_create_report_whitespace_title(self):
        """POST /api/reports — whitespace-only title should fail."""
        resp = self.client.post("/api/reports", json={
            "title": "   ",
        })
        self.assertEqual(resp.status_code, 400)

    def test_list_reports(self):
        """GET /api/reports — list reports."""
        # Create a report first
        self.client.post("/api/reports", json={"title": "List Test Report"})

        resp = self.client.get("/api/reports")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data["success"])
        self.assertGreater(len(data["reports"]), 0)
        self.assertIn("generated_at", data["reports"][0])
        self.assertEqual(data["reports"][0]["generator_version"], "1.0")

    def test_get_report(self):
        """GET /api/reports/{id} — get a specific report."""
        # Create report
        create_resp = self.client.post("/api/reports", json={
            "title": "Get Test Report",
            "content": {"detail": "test content"},
        })
        report_id = create_resp.json()["report"]["id"]

        resp = self.client.get(f"/api/reports/{report_id}")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data["success"])
        self.assertEqual(data["report"]["id"], report_id)
        self.assertIn("videos", data)
        self.assertIn("generated_at", data["report"])
        self.assertEqual(data["report"]["generator_version"], "1.0")

    def test_get_report_not_found(self):
        """GET /api/reports/{id} — should return 404 for non-existent."""
        resp = self.client.get("/api/reports/rpt-nonexistent")
        self.assertEqual(resp.status_code, 404)
        self.assertEqual(resp.json()["detail"]["error"], "NOT_FOUND")

    def test_get_report_content(self):
        """GET /api/reports/{id}/content — get report content."""
        create_resp = self.client.post("/api/reports", json={
            "title": "Content Test Report",
            "content": {
                "findings": [
                    {
                        "finding_id": "FND-CONTENT-1",
                        "title": "Cross-site scripting",
                        "description": "Reflected cross-site scripting in the search endpoint allows arbitrary JavaScript execution in victim browsers.",
                        "severity": "HIGH",
                        "cvss_score": 8.1,
                    }
                ]
            },
        })
        self.assertEqual(create_resp.status_code, 200)
        report_id = create_resp.json()["report"]["id"]

        resp = self.client.get(f"/api/reports/{report_id}/content")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data["success"])
        self.assertEqual(data["report_id"], report_id)
        self.assertIn("findings", data["content"])
        self.assertIn("generated_at", data)
        self.assertEqual(data["generator_version"], "1.0")
        self.assertEqual(len(data["sha256"]), 64)

    def test_create_report_with_findings_uses_report_engine(self):
        """POST /api/reports — findings payloads should use the report engine."""
        resp = self.client.post("/api/reports", json={
            "title": "Engine-backed report",
            "description": "Engine-backed vulnerability report",
            "content": {
                "scan_target": "api.example.com",
                "findings": [
                    {
                        "finding_id": "FND-200",
                        "title": "SQL injection in login",
                        "description": "Union-based SQL injection in the login workflow allows authentication bypass across multiple application roles.",
                        "severity": "HIGH",
                        "cvss_score": 8.8,
                        "model_confidence": 0.91,
                        "cve_id": "CVE-2026-2200",
                    }
                ],
            },
        })

        self.assertEqual(resp.status_code, 200)
        payload = resp.json()["report"]
        self.assertEqual(len(payload["sha256"]), 64)
        self.assertIn("executive_summary", payload["content"])
        self.assertIn("sections", payload["content"])
        self.assertEqual(payload["content"]["findings"][0]["finding_id"], "FND-200")

        metadata = json.loads(payload["metadata_json"])
        self.assertTrue(os.path.exists(metadata["report_storage_path"]))

    def test_create_report_with_empty_findings_returns_validation_error(self):
        """POST /api/reports — empty findings should be rejected."""
        resp = self.client.post("/api/reports", json={
            "title": "Invalid findings report",
            "content": {"findings": []},
        })

        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.json()["detail"]["error"], "VALIDATION_ERROR")

    def test_export_markdown_endpoint_returns_saved_report_markdown(self):
        """GET /api/reports/{id}/export/markdown — export saved report markdown."""
        create_resp = self.client.post("/api/reports", json={
            "title": "Markdown report",
            "description": "Markdown export coverage",
            "content": {
                "findings": [
                    {
                        "finding_id": "FND-300",
                        "title": "Cross-site scripting",
                        "description": "Reflected cross-site scripting in the search endpoint allows arbitrary JavaScript execution in victim browsers.",
                        "severity": "HIGH",
                        "cvss_score": 8.0,
                    },
                    {
                        "finding_id": "FND-301",
                        "title": "Missing CSRF protection",
                        "description": "The account settings workflow accepts state-changing POST requests without an anti-CSRF token or same-site validation.",
                        "severity": "MEDIUM",
                        "cvss_score": 6.4,
                    },
                ]
            },
        })
        report_id = create_resp.json()["report"]["id"]

        resp = self.client.get(f"/api/reports/{report_id}/export/markdown")

        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.headers["content-type"].startswith("text/markdown"))
        self.assertIn("FND-300", resp.text)
        self.assertIn("FND-301", resp.text)
        self.assertIn("## Executive Summary", resp.text)

    def test_export_markdown_v1_endpoint_returns_saved_report_markdown(self):
        """GET /api/v1/reports/{id}/export/markdown — export saved report markdown."""
        create_resp = self.client.post("/api/reports", json={
            "title": "Markdown v1 report",
            "description": "Markdown export v1 coverage",
            "content": {
                "findings": [
                    {
                        "finding_id": "FND-400",
                        "title": "Privilege escalation",
                        "description": "A privilege escalation path in the administrative API allows low-privilege users to invoke actions reserved for tenant administrators.",
                        "severity": "HIGH",
                        "cvss_score": 8.4,
                    }
                ]
            },
        })
        report_id = create_resp.json()["report"]["id"]

        resp = self.client.get(f"/api/v1/reports/{report_id}/export/markdown")

        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.headers["content-type"].startswith("text/markdown"))
        self.assertIn("FND-400", resp.text)
        self.assertIn("## Executive Summary", resp.text)

    def test_get_report_content_not_found(self):
        """GET /api/reports/{id}/content — 404 for non-existent."""
        resp = self.client.get("/api/reports/rpt-missing/content")
        self.assertEqual(resp.status_code, 404)

    def test_start_video_recording(self):
        """POST /api/reports/videos/start — start a video recording."""
        resp = self.client.post("/api/reports/videos/start", json={
            "filename": "test-recording.webm",
            "metadata": {"resolution": "1920x1080"},
        })
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data["success"])
        self.assertTrue(data["recording"]["id"].startswith("vid-"))
        self.assertEqual(data["recording"]["status"], "recording")

        self.__class__.video_id = data["recording"]["id"]

    def test_stop_video_recording(self):
        """POST /api/reports/videos/{id}/stop — stop a recording."""
        # Start first
        start_resp = self.client.post("/api/reports/videos/start", json={
            "filename": "stop-test.webm",
        })
        vid_id = start_resp.json()["recording"]["id"]

        resp = self.client.post(f"/api/reports/videos/{vid_id}/stop", json={
            "duration_seconds": 30.5,
            "file_size_bytes": 2048000,
        })
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data["success"])
        self.assertEqual(data["recording"]["status"], "completed")
        self.assertEqual(data["recording"]["duration_seconds"], 30.5)
        self.assertEqual(data["recording"]["file_size_bytes"], 2048000)

    def test_stop_video_not_found(self):
        """POST /api/reports/videos/{id}/stop — 404 for non-existent."""
        resp = self.client.post("/api/reports/videos/vid-nonexistent/stop", json={
            "duration_seconds": 10,
        })
        self.assertEqual(resp.status_code, 404)



    def test_full_report_workflow(self):
        """End-to-end: create report → start video → stop video → get report with videos."""
        # 1. Create report
        create_resp = self.client.post("/api/reports", json={
            "title": "Full Workflow Test",
            "description": "End-to-end integration test",
            "content": {"test": True},
        })
        self.assertEqual(create_resp.status_code, 200)
        report_id = create_resp.json()["report"]["id"]

        # 2. Start video attached to report
        start_resp = self.client.post("/api/reports/videos/start", json={
            "filename": "workflow-test.webm",
            "report_id": report_id,
        })
        self.assertEqual(start_resp.status_code, 200)
        video_id = start_resp.json()["recording"]["id"]

        # 3. Stop recording
        stop_resp = self.client.post(f"/api/reports/videos/{video_id}/stop", json={
            "duration_seconds": 60.0,
            "file_size_bytes": 5000000,
        })
        self.assertEqual(stop_resp.status_code, 200)

        # 4. Get report with attached videos
        get_resp = self.client.get(f"/api/reports/{report_id}")
        self.assertEqual(get_resp.status_code, 200)
        data = get_resp.json()
        self.assertEqual(data["report"]["id"], report_id)
        self.assertGreater(len(data["videos"]), 0)
        self.assertEqual(data["videos"][0]["status"], "completed")

    def test_create_multiple_reports_and_list(self):
        """Create several reports and verify listing."""
        titles = ["Report A", "Report B", "Report C"]
        for title in titles:
            resp = self.client.post("/api/reports", json={"title": title})
            self.assertEqual(resp.status_code, 200)

        resp = self.client.get("/api/reports")
        data = resp.json()
        # Should have at least the 3 we just created
        self.assertGreaterEqual(len(data["reports"]), 3)


class TestReportEndpointsDBFailure(unittest.TestCase):
    """Test report endpoints when database is unavailable."""

    def test_create_report_db_unavailable(self):
        """POST /api/reports should return 503 when DB is down."""
        from backend.api import report_generator
        from fastapi import FastAPI

        app = FastAPI()
        app.include_router(report_generator.router)
        client = TestClient(app)

        with patch.dict(os.environ, {"YGB_TEMP_AUTH_BYPASS": "true"}):
            with patch('backend.api.report_generator.get_db_connection', return_value=None):
                report_generator._TABLES_CREATED = True  # Skip table creation
                resp = client.post("/api/reports", json={"title": "Test"})
                self.assertEqual(resp.status_code, 503)
                report_generator._TABLES_CREATED = False

    def test_list_reports_db_unavailable(self):
        """GET /api/reports should return empty list when DB is down."""
        from backend.api import report_generator
        from fastapi import FastAPI

        app = FastAPI()
        app.include_router(report_generator.router)
        client = TestClient(app)

        with patch.dict(os.environ, {"YGB_TEMP_AUTH_BYPASS": "true"}):
            with patch('backend.api.report_generator.get_db_connection', return_value=None):
                report_generator._TABLES_CREATED = True
                resp = client.get("/api/reports")
                self.assertEqual(resp.status_code, 200)
                self.assertEqual(resp.json()["reports"], [])
                report_generator._TABLES_CREATED = False



if __name__ == "__main__":
    unittest.main()
