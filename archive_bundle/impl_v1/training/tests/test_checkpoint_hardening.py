from __future__ import annotations

import json

import pytest
import torch

from impl_v1.training.checkpoints.checkpoint_hardening import (
    HardenedCheckpointManager,
)


def _build_runtime():
    torch.manual_seed(7)
    model = torch.nn.Sequential(
        torch.nn.Linear(4, 8),
        torch.nn.ReLU(),
        torch.nn.Linear(8, 2),
    )
    optimizer = torch.optim.Adam(model.parameters(), lr=1e-3)
    return model, optimizer


@pytest.fixture
def fake_safetensors(monkeypatch):
    import training.safetensors_io as safetensors_io

    def fake_save_safetensors(tensors, path, metadata=None, convert_fp16=False):
        materialized = {
            key: value.detach().cpu().clone()
            for key, value in tensors.items()
        }
        torch.save({"tensors": materialized, "metadata": metadata or {}}, path)
        file_hash = safetensors_io._compute_file_hash(path)
        tensor_hash = safetensors_io._compute_tensor_hash(materialized)
        return file_hash, tensor_hash

    def fake_load_safetensors(path, device="cpu", verify_hash=True):
        payload = torch.load(path, map_location=device)
        return payload["tensors"]

    monkeypatch.setattr(safetensors_io, "save_safetensors", fake_save_safetensors)
    monkeypatch.setattr(safetensors_io, "load_safetensors", fake_load_safetensors)
    return safetensors_io


def test_full_checkpoint_writes_artifacts_and_pointers(tmp_path, fake_safetensors):
    model, optimizer = _build_runtime()
    manager = HardenedCheckpointManager(tmp_path)
    rng_state = manager.capture_rng_state()

    ok, metadata = manager.save_checkpoint(
        model.state_dict(),
        epoch=2,
        step=12,
        global_step=12,
        metrics={"train_loss": 0.42, "val_loss": 0.37},
        optimizer_state=optimizer.state_dict(),
        rng_state=rng_state,
        training_state={"best_val_loss": 0.37},
        is_best=True,
    )

    assert ok is True
    checkpoint_dir = tmp_path / metadata.checkpoint_id
    assert (checkpoint_dir / "model_shard_0.safetensors").exists()
    assert (checkpoint_dir / "optimizer_0.pt").exists()
    assert (checkpoint_dir / "rng_state_0.pt").exists()
    assert (checkpoint_dir / "training_state.json").exists()
    assert (checkpoint_dir / "metadata.json").exists()
    assert manager.latest_checkpoint_id == metadata.checkpoint_id
    assert manager.best_checkpoint_id == metadata.checkpoint_id

    pointers = json.loads((tmp_path / "checkpoint_pointers.json").read_text(encoding="utf-8"))
    assert pointers["latest_checkpoint_id"] == metadata.checkpoint_id
    assert pointers["best_checkpoint_id"] == metadata.checkpoint_id


def test_resume_restores_model_optimizer_and_rng(tmp_path, fake_safetensors):
    model, optimizer = _build_runtime()
    manager = HardenedCheckpointManager(tmp_path)
    rng_state = manager.capture_rng_state()
    reference_state = {
        key: value.detach().clone()
        for key, value in model.state_dict().items()
    }

    manager.save_checkpoint(
        model.state_dict(),
        epoch=1,
        step=5,
        global_step=5,
        metrics={"train_loss": 0.9, "val_loss": 0.8},
        optimizer_state=optimizer.state_dict(),
        rng_state=rng_state,
        training_state={"best_val_loss": 0.8},
        is_best=True,
    )

    for parameter in model.parameters():
        with torch.no_grad():
            parameter.add_(5.0)
    optimizer.zero_grad(set_to_none=True)
    _ = torch.rand(3)

    resume = manager.resume_from_latest(model=model, optimizer=optimizer, device="cpu")

    assert resume.resumed is True
    assert resume.global_step == 5
    for key, value in model.state_dict().items():
        assert torch.equal(value, reference_state[key])
    assert torch.equal(torch.get_rng_state(), rng_state["torch"])


def test_async_save_completes_and_updates_manifest(tmp_path, fake_safetensors):
    model, optimizer = _build_runtime()
    manager = HardenedCheckpointManager(tmp_path)

    future = manager.save_checkpoint_async(
        model.state_dict(),
        epoch=3,
        step=21,
        global_step=21,
        metrics={"train_loss": 0.31, "val_loss": 0.29},
        optimizer_state=optimizer.state_dict(),
        rng_state=manager.capture_rng_state(),
        training_state={"best_val_loss": 0.29},
        is_best=False,
    )
    ok, metadata = future.result(timeout=30)

    assert ok is True
    manager.wait_for_pending_writes()
    manifest = json.loads((tmp_path / "checkpoint_manifest.json").read_text(encoding="utf-8"))
    assert metadata.checkpoint_id in manifest["checkpoints"]


def test_latest_valid_checkpoint_skips_incomplete_pointer_target(tmp_path, fake_safetensors):
    model, optimizer = _build_runtime()
    manager = HardenedCheckpointManager(tmp_path)
    _, metadata = manager.save_checkpoint(
        model.state_dict(),
        epoch=1,
        step=10,
        global_step=10,
        metrics={"train_loss": 0.5, "val_loss": 0.4},
        optimizer_state=optimizer.state_dict(),
        rng_state=manager.capture_rng_state(),
        training_state={"best_val_loss": 0.4},
        is_best=True,
    )

    incomplete_dir = tmp_path / "global_step_20"
    incomplete_dir.mkdir(parents=True, exist_ok=True)
    (incomplete_dir / "training_state.json").write_text("{}", encoding="utf-8")
    (tmp_path / "checkpoint_pointers.json").write_text(
        json.dumps(
            {
                "latest_checkpoint_id": "global_step_20",
                "best_checkpoint_id": metadata.checkpoint_id,
            }
        ),
        encoding="utf-8",
    )

    reloaded = HardenedCheckpointManager(tmp_path)
    assert reloaded.get_latest_valid_checkpoint() == metadata.checkpoint_id
