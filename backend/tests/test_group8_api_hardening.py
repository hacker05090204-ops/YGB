"""Focused Group 8 coverage for report, status, and training hardening."""

from __future__ import annotations

import asyncio
import json
import os
import tempfile
import unittest
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient


class TestGroup8ReportGenerator(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, "group8_reports.db")
        self.env_patcher = patch.dict(
            os.environ,
            {
                "DATABASE_URL": f"sqlite:///{self.db_path}",
                "YGB_TEMP_AUTH_BYPASS": "true",
                "YGB_HDD_ROOT": self.temp_dir.name,
            },
        )
        self.env_patcher.start()

        from backend.api import report_generator

        self.report_generator = report_generator
        self.report_generator._TABLES_CREATED = False
        self.report_generator.ReportExportLog.clear()

        app = FastAPI()
        app.include_router(self.report_generator.router)
        self.client = TestClient(app)

    def tearDown(self):
        self.client.close()
        self.report_generator._TABLES_CREATED = False
        self.report_generator.ReportExportLog.clear()
        self.env_patcher.stop()
        self.temp_dir.cleanup()

    def test_db_unavailable_response_sets_fallback_available_false(self):
        with patch("backend.api.report_generator.get_db_connection", return_value=None):
            self.report_generator._TABLES_CREATED = True
            response = self.client.post("/api/reports", json={"title": "Unavailable DB"})

        self.assertEqual(response.status_code, 503)
        payload = response.json()["detail"]
        self.assertEqual(payload["error"], "SERVICE_UNAVAILABLE")
        self.assertFalse(payload["fallback_available"])

    def test_successful_report_has_generated_at_and_export_record(self):
        response = self.client.post(
            "/api/reports",
            json={
                "title": "Group 8 report",
                "content": {"severity": "high"},
                "metadata": {"source": "group8-test"},
            },
        )

        self.assertEqual(response.status_code, 200)
        report = response.json()["report"]
        self.assertEqual(report["generator_version"], "1.0")
        self.assertIsNotNone(
            datetime.fromisoformat(report["generated_at"].replace("Z", "+00:00"))
        )
        self.assertEqual(len(self.report_generator.ReportExportLog), 1)

        export_record = self.report_generator.ReportExportLog[-1]
        self.assertEqual(export_record.report_id, report["id"])
        self.assertEqual(export_record.format, "json")
        self.assertGreater(export_record.export_size_bytes, 0)
        self.assertIsNotNone(
            datetime.fromisoformat(export_record.exported_at.replace("Z", "+00:00"))
        )


class TestGroup8SystemStatus(unittest.TestCase):
    @staticmethod
    def _run_status_with(sub_checks):
        from backend.api.system_status import aggregated_system_status

        with patch("backend.api.system_status._safe_call") as mock_safe:
            mock_safe.side_effect = lambda name, fn: sub_checks[name]
            return asyncio.run(aggregated_system_status())

    def test_all_available_subchecks_produce_healthy_overall_health(self):
        result = self._run_status_with(
            {
                "readiness": {"ready": True},
                "metrics": {"requests": 1},
                "training": {"status": "idle"},
                "voice": {"status": "idle"},
                "storage": {"storage_active": True},
                "canonical_status": {"schema_version": 2},
            }
        )

        self.assertEqual(result["overall_health"], "HEALTHY")
        self.assertIsNotNone(
            datetime.fromisoformat(result["last_checked"].replace("Z", "+00:00"))
        )

    def test_some_unavailable_subchecks_produce_degraded_overall_health(self):
        result = self._run_status_with(
            {
                "readiness": {"ready": True},
                "metrics": {"status": "UNAVAILABLE", "error": "metrics down"},
                "training": {"status": "idle"},
                "voice": {"status": "idle"},
                "storage": {"storage_active": True},
                "canonical_status": {"schema_version": 2},
            }
        )

        self.assertEqual(result["overall_health"], "DEGRADED")

    def test_majority_unavailable_subchecks_produce_critical_overall_health(self):
        result = self._run_status_with(
            {
                "readiness": {"status": "UNAVAILABLE", "error": "readiness down"},
                "metrics": {"status": "UNAVAILABLE", "error": "metrics down"},
                "training": {"status": "UNAVAILABLE", "error": "training down"},
                "voice": {"status": "UNAVAILABLE", "error": "voice down"},
                "storage": {"storage_active": True},
                "canonical_status": {"schema_version": 2},
            }
        )

        self.assertEqual(result["overall_health"], "CRITICAL")


class TestGroup8TrainingProgress(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.telemetry_path = os.path.join(self.temp_dir.name, "training_telemetry.json")
        with open(self.telemetry_path, "w", encoding="utf-8") as handle:
            json.dump(
                {
                    "wall_clock_unix": 1712448000,
                    "monotonic_start_time": 100.0,
                    "monotonic_timestamp": 150.0,
                    "training_duration_seconds": 50.0,
                    "samples_per_second": 10.0,
                    "epoch": 12,
                    "loss": 0.12,
                    "gpu_temperature": 65.5,
                },
                handle,
            )

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_history_available_sets_flag_and_returns_last_ten_snapshots(self):
        from backend.api.training_progress import get_training_progress
        from backend.training.incremental_trainer import AccuracySnapshot

        snapshots = [
            AccuracySnapshot(
                epoch=index,
                accuracy=0.80 + (index * 0.001),
                precision=0.75 + (index * 0.001),
                recall=0.70 + (index * 0.001),
                f1=0.72 + (index * 0.001),
                auc_roc=0.85 + (index * 0.001),
                taken_at=f"2026-04-07T00:{index:02d}:00+00:00",
            )
            for index in range(1, 13)
        ]
        fake_manager = SimpleNamespace(
            _g38_available=True,
            _trainer=SimpleNamespace(get_accuracy_history=lambda: snapshots),
        )

        with patch("backend.api.training_progress.TELEMETRY_PATH", self.telemetry_path):
            with patch(
                "backend.api.training_progress._get_training_state_manager",
                return_value=fake_manager,
            ):
                result = get_training_progress()

        self.assertTrue(result["includes_accuracy_history"])
        self.assertEqual(len(result["accuracy_history"]), 10)
        self.assertEqual(result["accuracy_history"][0]["epoch"], 3)
        self.assertEqual(result["accuracy_history"][-1]["epoch"], 12)

    def test_history_unavailable_sets_flag_false_without_crashing(self):
        from backend.api.training_progress import get_training_progress

        fake_manager = SimpleNamespace(_g38_available=False, _trainer=None)

        with patch("backend.api.training_progress.TELEMETRY_PATH", self.telemetry_path):
            with patch(
                "backend.api.training_progress._get_training_state_manager",
                return_value=fake_manager,
            ):
                result = get_training_progress()

        self.assertFalse(result["includes_accuracy_history"])
        self.assertEqual(result["accuracy_history"], [])
        self.assertEqual(result["status"], "training")
