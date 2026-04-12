from __future__ import annotations

from pathlib import Path

import pytest

torch = pytest.importorskip("torch")

from backend.training.safetensors_store import CheckpointManager
from impl_v1.phase49.moe import EXPERT_FIELDS


def _state_dict(seed: float) -> dict[str, torch.Tensor]:
    return {
        "layer.weight": torch.tensor(
            [[seed, seed + 1.0], [seed + 2.0, seed + 3.0]],
            dtype=torch.float32,
        ),
        "layer.bias": torch.tensor([seed, -seed], dtype=torch.float32),
    }


def test_checkpoint_saved_on_val_improvement(tmp_path):
    manager = CheckpointManager(tmp_path / "checkpoints")
    field_name = EXPERT_FIELDS[0]

    manager.save_expert_checkpoint(
        expert_id=0,
        field_name=field_name,
        state_dict=_state_dict(1.0),
        val_f1=0.75,
        metadata={"epoch": 1},
    )
    improved = manager.save_expert_checkpoint(
        expert_id=0,
        field_name=field_name,
        state_dict=_state_dict(2.0),
        val_f1=0.81,
        metadata={"epoch": 2},
    )
    status = manager.status(0, field_name)
    loaded_best = manager.load_best_checkpoint(expert_id=0, field_name=field_name)

    assert improved["saved"] is True
    assert improved["is_best"] is True
    assert Path(improved["checkpoint_path"]).exists()
    assert status["best_val_f1"] == pytest.approx(0.81)
    assert status["best_checkpoint_path"] == improved["checkpoint_path"]
    assert status["checkpoints"][0]["metadata"]["epoch"] == 2
    assert torch.equal(loaded_best["layer.weight"], _state_dict(2.0)["layer.weight"])


def test_checkpoint_not_overwritten_with_worse(tmp_path):
    manager = CheckpointManager(tmp_path / "checkpoints")
    field_name = EXPERT_FIELDS[0]

    best_result = manager.save_expert_checkpoint(
        expert_id=0,
        field_name=field_name,
        state_dict=_state_dict(10.0),
        val_f1=0.95,
        metadata={"epoch": 1},
    )
    manager.save_expert_checkpoint(
        expert_id=0,
        field_name=field_name,
        state_dict=_state_dict(20.0),
        val_f1=0.90,
        metadata={"epoch": 2},
    )
    manager.save_expert_checkpoint(
        expert_id=0,
        field_name=field_name,
        state_dict=_state_dict(30.0),
        val_f1=0.85,
        metadata={"epoch": 3},
    )

    worse_result = manager.save_expert_checkpoint(
        expert_id=0,
        field_name=field_name,
        state_dict=_state_dict(40.0),
        val_f1=0.80,
        metadata={"epoch": 4},
    )
    status = manager.status(0, field_name)
    loaded_best = manager.load_best_checkpoint(expert_id=0, field_name=field_name)

    assert worse_result["saved"] is False
    assert worse_result["checkpoint_path"] == ""
    assert status["best_val_f1"] == pytest.approx(0.95)
    assert status["best_checkpoint_path"] == best_result["checkpoint_path"]
    assert torch.equal(loaded_best["layer.weight"], _state_dict(10.0)["layer.weight"])

