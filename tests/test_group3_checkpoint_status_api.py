from __future__ import annotations

from pathlib import Path

import pytest

torch = pytest.importorskip("torch")

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.api import runtime_api
from backend.training.safetensors_store import CheckpointManager
from impl_v1.phase49.moe import EXPERT_FIELDS
from scripts.expert_task_queue import (
    STATUS_COMPLETED,
    claim_next_expert,
    initialize_status_file,
    release_expert,
)


def _state_dict(seed: float) -> dict[str, torch.Tensor]:
    return {
        "layer.weight": torch.tensor(
            [[seed, seed + 1.0], [seed + 2.0, seed + 3.0]],
            dtype=torch.float32,
        ),
        "layer.bias": torch.tensor([seed, -seed], dtype=torch.float32),
    }


def _expert_checkpoint_paths(root: Path, expert_id: int, field_name: str) -> list[Path]:
    return sorted(root.glob(f"expert_{expert_id:02d}_{field_name}_e*_f1*.safetensors"))


def test_checkpoint_manager_save_then_load_roundtrip(tmp_path):
    checkpoint_root = tmp_path / "checkpoints"
    manager = CheckpointManager(checkpoint_root)

    save_result = manager.save_expert_checkpoint(
        expert_id=0,
        field_name=EXPERT_FIELDS[0],
        state_dict=_state_dict(1.5),
        val_f1=0.81,
        metadata={"epoch": 2, "source": "unit-test"},
    )

    loaded_state = manager.load_best_checkpoint(
        expert_id=0,
        field_name=EXPERT_FIELDS[0],
    )
    status = manager.status(0, EXPERT_FIELDS[0])

    assert save_result["saved"] is True
    assert save_result["is_best"] is True
    assert (
        Path(save_result["checkpoint_path"]).name
        == f"expert_00_{EXPERT_FIELDS[0]}_e2_f10.8100.safetensors"
    )
    assert set(loaded_state) == {"layer.weight", "layer.bias"}
    assert torch.equal(loaded_state["layer.weight"], _state_dict(1.5)["layer.weight"])
    assert torch.equal(loaded_state["layer.bias"], _state_dict(1.5)["layer.bias"])
    assert status["best_val_f1"] == pytest.approx(0.81)
    assert status["checkpoints"][0]["metadata"]["epoch"] == 2
    assert status["checkpoints"][0]["metadata"]["source"] == "unit-test"


def test_checkpoint_manager_never_replaces_better_checkpoint_with_worse(tmp_path):
    checkpoint_root = tmp_path / "checkpoints"
    manager = CheckpointManager(checkpoint_root)
    field_name = EXPERT_FIELDS[0]

    best_result = manager.save_expert_checkpoint(
        expert_id=0,
        field_name=field_name,
        state_dict=_state_dict(10.0),
        val_f1=0.95,
    )
    manager.save_expert_checkpoint(
        expert_id=0,
        field_name=field_name,
        state_dict=_state_dict(20.0),
        val_f1=0.90,
    )
    manager.save_expert_checkpoint(
        expert_id=0,
        field_name=field_name,
        state_dict=_state_dict(30.0),
        val_f1=0.85,
    )

    worse_result = manager.save_expert_checkpoint(
        expert_id=0,
        field_name=field_name,
        state_dict=_state_dict(40.0),
        val_f1=0.80,
    )
    status = manager.status(0, field_name)
    loaded_best = manager.load_best_checkpoint(expert_id=0, field_name=field_name)

    assert worse_result["saved"] is False
    assert worse_result["checkpoint_path"] == ""
    assert status["best_val_f1"] == pytest.approx(0.95)
    assert status["best_checkpoint_path"] == best_result["checkpoint_path"]
    assert torch.equal(loaded_best["layer.weight"], _state_dict(10.0)["layer.weight"])


def test_checkpoint_manager_cleanup_keeps_exactly_top_three(tmp_path):
    checkpoint_root = tmp_path / "checkpoints"
    manager = CheckpointManager(checkpoint_root)
    field_name = EXPERT_FIELDS[0]

    manager.save_expert_checkpoint(
        expert_id=0,
        field_name=field_name,
        state_dict=_state_dict(1.0),
        val_f1=0.70,
    )
    manager.save_expert_checkpoint(
        expert_id=0,
        field_name=field_name,
        state_dict=_state_dict(2.0),
        val_f1=0.80,
    )
    manager.save_expert_checkpoint(
        expert_id=0,
        field_name=field_name,
        state_dict=_state_dict(3.0),
        val_f1=0.75,
    )
    manager.save_expert_checkpoint(
        expert_id=0,
        field_name=field_name,
        state_dict=_state_dict(4.0),
        val_f1=0.85,
    )

    retained_files = _expert_checkpoint_paths(checkpoint_root, 0, field_name)
    status = manager.status(0, field_name)

    assert len(retained_files) == 3
    assert len(status["checkpoints"]) == 3
    assert [item["val_f1"] for item in status["checkpoints"]] == [0.85, 0.8, 0.75]
    assert all("0.700000" not in item["checkpoint_path"] for item in status["checkpoints"])


def test_checkpoint_manager_get_all_expert_status_returns_23_entries(tmp_path):
    manager = CheckpointManager(tmp_path / "checkpoints")

    statuses = manager.get_all_expert_status()

    assert len(statuses) == 23
    assert [item["expert_id"] for item in statuses] == list(range(23))
    assert [item["field_name"] for item in statuses] == list(EXPERT_FIELDS)


def test_checkpoint_manager_extracts_f1_from_legacy_and_group3_filenames():
    assert CheckpointManager._extract_f1("expert_0_web_vulns_0.750.safetensors") == pytest.approx(0.75)
    assert (
        CheckpointManager._extract_f1(
            "expert_0_web_vulns_f1_0.812500_20260410T001500000000Z.safetensors"
        )
        == pytest.approx(0.8125)
    )
    assert (
        CheckpointManager._extract_f1("expert_00_web_vulns_e3_f10.8125.safetensors")
        == pytest.approx(0.8125)
    )
    assert CheckpointManager._extract_f1("expert_0_web_vulns_latest.safetensors") is None


def test_training_expert_status_endpoint_combines_checkpoint_and_queue_state(
    tmp_path,
    monkeypatch,
):
    status_path = tmp_path / "experts_status.json"
    checkpoint_root = tmp_path / "checkpoints"

    initialize_status_file(status_path)
    claimed = claim_next_expert(
        "worker-1",
        status_path=status_path,
        claim_timeout_seconds=60.0,
    )
    assert claimed is not None
    assert int(claimed["expert_id"]) == 0

    second_claim = claim_next_expert(
        "worker-2",
        status_path=status_path,
        claim_timeout_seconds=60.0,
    )
    assert second_claim is not None
    assert int(second_claim["expert_id"]) == 1
    release_expert(
        1,
        status_path=status_path,
        worker_id="worker-2",
        status=STATUS_COMPLETED,
        val_f1=0.42,
        checkpoint_path="",
    )

    manager = CheckpointManager(checkpoint_root)
    manager.save_expert_checkpoint(
        expert_id=0,
        field_name=EXPERT_FIELDS[0],
        state_dict=_state_dict(5.0),
        val_f1=0.88,
        metadata={"epoch": 3},
    )

    monkeypatch.setattr(runtime_api, "EXPERT_STATUS_PATH", str(status_path))
    monkeypatch.setattr(runtime_api, "EXPERT_CHECKPOINT_ROOT", str(checkpoint_root))

    app = FastAPI()
    app.include_router(runtime_api.router)
    app.dependency_overrides[runtime_api.require_auth] = (
        lambda: {"sub": "pytest-user", "role": "admin"}
    )
    client = TestClient(app)

    response = client.get("/api/v1/training/experts/status")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["updated_at"]
    assert len(payload["experts"]) == 23

    first = payload["experts"][0]
    second = payload["experts"][1]

    assert first == {
        "expert_id": 0,
        "field_name": EXPERT_FIELDS[0],
        "queue_status": "CLAIMED",
        "has_checkpoint": True,
        "best_val_f1": pytest.approx(0.88),
        "claimed_by": "worker-1",
    }
    assert second["expert_id"] == 1
    assert second["field_name"] == EXPERT_FIELDS[1]
    assert second["queue_status"] == "COMPLETED"
    assert second["has_checkpoint"] is False
    assert second["best_val_f1"] == pytest.approx(0.42)
    assert second["claimed_by"] is None
