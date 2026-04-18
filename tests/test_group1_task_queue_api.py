from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.api import task_queue_api
from backend.distributed.intelligent_scheduler import can_handle, get_priority_order
from scripts.expert_task_queue import ExpertTaskQueue, STATUS_CLAIMED, STATUS_COMPLETED


def _build_client(status_path: Path, monkeypatch) -> TestClient:
    monkeypatch.setenv("YGB_EXPERT_STATUS_PATH", str(status_path))
    app = FastAPI()
    app.include_router(task_queue_api.router)
    app.dependency_overrides[task_queue_api.require_auth] = (
        lambda: {"sub": "pytest-user", "role": "admin"}
    )
    return TestClient(app)


def test_task_queue_api_claim_heartbeat_release_and_status(tmp_path, monkeypatch):
    status_path = tmp_path / "experts_status.json"
    queue = ExpertTaskQueue(status_path=status_path)
    queue.initialize_status_file()
    client = _build_client(status_path, monkeypatch)

    status_response = client.get("/api/v1/tasks/status")
    assert status_response.status_code == 200
    status_payload = status_response.json()
    assert status_payload["status"] == "ok"
    assert status_payload["summary"]["available"] == len(status_payload["experts"])

    claim_response = client.post(
        "/api/v1/tasks/claim",
        json={"worker_id": "worker-1", "claim_timeout_seconds": 60.0},
    )
    assert claim_response.status_code == 200
    claim_payload = claim_response.json()
    assert claim_payload["status"] == "ok"
    assert claim_payload["claimed"] is True
    claimed = claim_payload["task"]
    assert claimed["status"] == STATUS_CLAIMED
    assert claimed["claimed_by"] == "worker-1"

    heartbeat_response = client.post(
        "/api/v1/tasks/heartbeat",
        json={
            "expert_id": claimed["expert_id"],
            "worker_id": "worker-1",
            "claim_timeout_seconds": 120.0,
        },
    )
    assert heartbeat_response.status_code == 200
    heartbeat_payload = heartbeat_response.json()
    assert heartbeat_payload["task"]["status"] == STATUS_CLAIMED
    assert float(heartbeat_payload["task"]["claim_expires_at_epoch"]) > float(
        claimed["claim_expires_at_epoch"]
    )

    release_response = client.post(
        "/api/v1/tasks/release",
        json={
            "expert_id": claimed["expert_id"],
            "worker_id": "worker-1",
            "status": STATUS_COMPLETED,
            "val_f1": 0.91,
            "val_precision": 0.89,
            "val_recall": 0.93,
            "checkpoint_path": "checkpoints/expert_00.safetensors",
        },
    )
    assert release_response.status_code == 200
    release_payload = release_response.json()
    assert release_payload["task"]["status"] == STATUS_COMPLETED
    assert release_payload["task"]["claimed_by"] is None

    final_status = client.get("/api/v1/tasks/status")
    assert final_status.status_code == 200
    final_payload = final_status.json()
    assert final_payload["summary"]["completed"] == 1
    assert final_payload["summary"]["claimed"] == 0
    released_record = next(
        item
        for item in final_payload["experts"]
        if int(item["expert_id"]) == int(claimed["expert_id"])
    )
    assert released_record["status"] == STATUS_COMPLETED
    assert released_record["checkpoint_path"] == "checkpoints/expert_00.safetensors"


def test_task_queue_api_returns_empty_claim_when_queue_is_full(tmp_path, monkeypatch):
    status_path = tmp_path / "experts_status.json"
    queue = ExpertTaskQueue(status_path=status_path)
    state = queue.initialize_status_file()
    for expert_index in range(len(state["experts"])):
        claimed = queue.claim_next_expert(
            f"worker-{expert_index}",
            claim_timeout_seconds=60.0,
        )
        assert claimed is not None

    client = _build_client(status_path, monkeypatch)
    response = client.post("/api/v1/tasks/claim", json={"worker_id": "late-worker"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["claimed"] is False
    assert payload["task"] is None
    assert payload["summary"]["available"] == 0
    assert payload["summary"]["claimed"] == payload["summary"]["total"]


def test_intelligent_scheduler_is_vram_aware():
    assert can_handle("xss", 2.5) is True
    assert can_handle("hardware", 2.5) is False
    assert can_handle(
        "hardware",
        {"available_vram_gb": 12.0, "gpu_utilization": 72.0, "healthy": True},
    ) is True

    low_vram_order = get_priority_order(2.5)
    high_vram_order = get_priority_order(12.0)

    assert low_vram_order[0] in {"xss", "idor", "csrf", "web_vulns", "api_testing"}
    assert set(low_vram_order) == set(high_vram_order)
    assert low_vram_order.index("hardware") > low_vram_order.index("xss")
    assert high_vram_order.index("hardware") < low_vram_order.index("hardware")


def test_api_server_registers_task_queue_router():
    contents = Path("api/server.py").read_text(encoding="utf-8")

    assert "backend.api.task_queue_api" in contents
    assert "app.include_router(task_queue_api_router)" in contents
