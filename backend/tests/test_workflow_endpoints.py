from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

import backend.api.runtime_api as runtime_api


def test_workflow_trigger_endpoint_returns_run_id(monkeypatch):
    class _FakeWorkflowOrchestrator:
        def trigger_cycle(self, *, trigger: str = "api") -> dict[str, str]:
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

    response = client.post("/api/v1/workflow/trigger")

    payload = response.json()
    run_identifier = payload.get("run_id") or payload.get("cycle_id")

    assert response.status_code == 202
    assert payload["status"] == "triggered"
    assert payload["cycle_id"] == "WFC-NEXT"
    assert run_identifier == "WFC-NEXT"
