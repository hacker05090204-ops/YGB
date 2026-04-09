from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

import backend.api.runtime_api as runtime_api
import backend.startup.pipeline_bootstrap as pipeline_bootstrap_module
from backend.reporting.report_engine import ReportEngine
from backend.tasks.industrial_agent import AutonomousWorkflowOrchestrator


def test_workflow_orchestrator_runs_cycle_and_persists_status(tmp_path):
    class _FakeGrabber:
        def run_cycle(self):
            return SimpleNamespace(
                cycle_id="grabber-001",
                sources_attempted=2,
                sources_succeeded=2,
                samples_fetched=3,
                samples_accepted=2,
                samples_rejected=1,
                bridge_published=2,
                errors=[],
            )

    class _FakeController:
        def check_and_train(self, *, trigger="manual"):
            return SimpleNamespace(
                run_id="train-001",
                status="COMPLETED",
                promoted=False,
                trigger=trigger,
            )

    orchestrator = AutonomousWorkflowOrchestrator(
        root=tmp_path / "workflow",
        autograbber=_FakeGrabber(),
        auto_train_controller=_FakeController(),
        report_engine=ReportEngine(output_dir=tmp_path / "reports"),
        worker_status_loader=lambda: {
            "bridge_count": 2,
            "bridge_verified_count": 2,
            "last_batch": {
                "batch_id": "CBI-000001",
                "ingested": 2,
                "mode": "autograbber",
            },
        },
        bridge_samples_loader=lambda max_samples=0: [
            {
                "sha256_hash": "sha-1",
                "endpoint": "CVE-2026-3100",
                "exploit_vector": (
                    "Server-side request forgery in the metadata proxy allows remote "
                    "access to internal cloud credentials and downstream secrets."
                ),
                "impact": "CRITICAL|CVSS:9.8",
                "source_tag": "nvd",
                "ingestion_batch_id": "CBI-000001",
            },
            {
                "sha256_hash": "sha-2",
                "endpoint": "CVE-2026-3101",
                "exploit_vector": (
                    "Broken object-level authorization on the administrative API exposes "
                    "tenant data and cross-account mutation paths without additional checks."
                ),
                "impact": "HIGH|CVSS:8.1",
                "source_tag": "cisa",
                "ingestion_batch_id": "CBI-000001",
            },
        ],
    )

    result = orchestrator.run_cycle(trigger="manual")

    assert result.status == "COMPLETED"
    assert result.ingest_cycle_id == "grabber-001"
    assert result.bridge_batch_id == "CBI-000001"
    assert result.training_run_id == "train-001"
    assert result.report_generated is True
    assert result.report_findings == 2
    assert result.report_path is not None
    assert Path(result.report_path).exists()

    status_payload = json.loads((tmp_path / "workflow" / "status.json").read_text(encoding="utf-8"))
    history_payload = json.loads((tmp_path / "workflow" / "history.json").read_text(encoding="utf-8"))

    assert status_payload["run_in_progress"] is False
    assert status_payload["last_cycle"]["cycle_id"] == result.cycle_id
    assert status_payload["history_size"] == 1
    assert len(history_payload) == 1
    assert history_payload[0]["report_generated"] is True


def test_workflow_runtime_api_endpoints_return_expected_payloads(monkeypatch):
    class _FakeWorkflowOrchestrator:
        def get_status(self):
            return {
                "initialized": True,
                "run_in_progress": False,
                "active_cycle_id": None,
                "history_size": 1,
                "last_cycle": {
                    "cycle_id": "WFC-EXAMPLE",
                    "status": "COMPLETED",
                    "report_generated": True,
                },
            }

        def get_history(self, *, limit=None):
            return [
                {
                    "cycle_id": "WFC-EXAMPLE",
                    "status": "COMPLETED",
                    "report_generated": True,
                }
            ][: limit or 1]

        def trigger_cycle(self, *, trigger="api"):
            return {
                "cycle_id": "WFC-NEXT",
                "status": "triggered",
            }

    monkeypatch.setattr(
        runtime_api,
        "get_workflow_orchestrator",
        lambda: _FakeWorkflowOrchestrator(),
    )

    app = FastAPI()
    app.include_router(runtime_api.router)
    app.dependency_overrides[runtime_api.require_auth] = lambda: {"sub": "user-1"}
    client = TestClient(app)

    status_response = client.get("/api/v1/workflow/status")
    history_response = client.get("/api/v1/workflow/history?limit=1")
    trigger_response = client.post("/api/v1/workflow/trigger")

    assert status_response.status_code == 200
    assert status_response.json() == {
        "status": "ok",
        "initialized": True,
        "run_in_progress": False,
        "active_cycle_id": None,
        "history_size": 1,
        "last_cycle": {
            "cycle_id": "WFC-EXAMPLE",
            "status": "COMPLETED",
            "report_generated": True,
        },
    }
    assert history_response.status_code == 200
    assert history_response.json() == {
        "status": "ok",
        "history": [
            {
                "cycle_id": "WFC-EXAMPLE",
                "status": "COMPLETED",
                "report_generated": True,
            }
        ],
    }
    assert trigger_response.status_code == 202
    assert trigger_response.json() == {
        "cycle_id": "WFC-NEXT",
        "status": "triggered",
    }


def test_bootstrap_pipeline_initializes_workflow_orchestrator(monkeypatch):
    created: dict[str, object] = {}
    workflow_call: dict[str, object] = {}
    scheduled_threads: list[object] = []

    class _FakeGrabber:
        def __init__(self, config):
            self.config = config
            self.start_calls = 0

        def start_scheduled(self):
            self.start_calls += 1

        def stop(self):
            return None

    class _FakeController:
        def __init__(self):
            self.running = False
            self.config = SimpleNamespace(check_interval_seconds=60.0)

        def start(self):
            self.running = True
            return True

        def is_scheduled_running(self):
            return self.running

    class _FakeThread:
        def __init__(self, *args, **kwargs):
            self.args = args
            self.kwargs = kwargs
            self.started = False

        def start(self):
            self.started = True

    def _thread_factory(*args, **kwargs):
        thread = _FakeThread(*args, **kwargs)
        scheduled_threads.append(thread)
        return thread

    def _initialize_autograbber(config):
        grabber = _FakeGrabber(config)
        created["grabber"] = grabber
        return grabber

    controller = _FakeController()

    def _initialize_workflow_orchestrator(**kwargs):
        workflow_call.update(kwargs)
        return SimpleNamespace(get_status=lambda: {"history_size": 0})

    monkeypatch.setattr(
        pipeline_bootstrap_module,
        "initialize_autograbber",
        _initialize_autograbber,
    )
    monkeypatch.setattr(
        pipeline_bootstrap_module,
        "get_auto_train_controller",
        lambda: controller,
    )
    monkeypatch.setattr(
        pipeline_bootstrap_module,
        "initialize_workflow_orchestrator",
        _initialize_workflow_orchestrator,
    )
    monkeypatch.setattr(
        pipeline_bootstrap_module,
        "seed_system_status_cache",
        lambda: True,
    )
    monkeypatch.setattr(pipeline_bootstrap_module.threading, "Thread", _thread_factory)

    result = pipeline_bootstrap_module.bootstrap_pipeline()

    assert result.autograbber is created["grabber"]
    assert workflow_call["autograbber"] is created["grabber"]
    assert workflow_call["auto_train_controller"] is controller
    assert scheduled_threads
