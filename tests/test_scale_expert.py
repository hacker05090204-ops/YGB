from __future__ import annotations

from pathlib import Path

import pytest

torch = pytest.importorskip("torch")

from backend.training.safetensors_store import CheckpointManager
from impl_v1.phase49.moe import EXPERT_FIELDS, MoEClassifier, MoEConfig
from impl_v1.training.checkpoints.checkpoint_hardening import HardenedCheckpointManager
from scripts.scale_expert import (
    load_checkpoint_metadata,
    resolve_phase16_scaling_stage,
    scale_expert_checkpoint,
)
from training.safetensors_io import CheckpointIntegrityError, load_safetensors


def _build_classifier(depth: int) -> MoEClassifier:
    torch.manual_seed(7)
    config = MoEConfig(
        d_model=8,
        n_experts=len(EXPERT_FIELDS),
        top_k=2,
        expert_hidden_mult=2,
        dropout=0.0,
        gate_noise=0.0,
    )
    setattr(config, "expert_hidden_dim", 12)
    setattr(config, "expert_depth", depth)
    return MoEClassifier(config, input_dim=4, output_dim=2)


def test_phase16_scaling_plan_boundaries():
    assert resolve_phase16_scaling_stage(1).target_label == "130M per expert"
    assert resolve_phase16_scaling_stage(45).target_label == "512M per expert"
    assert resolve_phase16_scaling_stage(120).target_label == "1B per expert"
    assert resolve_phase16_scaling_stage(220).target_label == "3B per expert"


def test_checkpoint_manager_load_requires_verified_sidecar(tmp_path):
    manager = CheckpointManager(tmp_path / "checkpoints")
    model = _build_classifier(depth=1)

    result = manager.save_expert_checkpoint(
        expert_id=0,
        field_name=EXPERT_FIELDS[0],
        state_dict=model.state_dict(),
        val_f1=0.81,
        metadata={"epoch": 2},
    )

    checkpoint_path = Path(result["checkpoint_path"])
    sidecar_path = Path(f"{checkpoint_path}.sha256")
    assert sidecar_path.exists()

    loaded = manager.load_best_checkpoint(
        expert_id=0,
        field_name=EXPERT_FIELDS[0],
    )
    assert torch.equal(loaded["input_proj.weight"], model.state_dict()["input_proj.weight"])

    sidecar_path.unlink()
    with pytest.raises(CheckpointIntegrityError):
        manager.load_best_checkpoint(
            expert_id=0,
            field_name=EXPERT_FIELDS[0],
        )


def test_scale_expert_checkpoint_doubles_depth_and_writes_verified_output(tmp_path):
    manager = CheckpointManager(tmp_path / "checkpoints")
    model = _build_classifier(depth=1)
    source_state = model.state_dict()
    save_result = manager.save_expert_checkpoint(
        expert_id=0,
        field_name=EXPERT_FIELDS[0],
        state_dict=source_state,
        val_f1=0.88,
        metadata={"epoch": 3, "top_k": 2, "dropout": 0.0, "gate_noise": 0.0},
    )

    input_path = Path(save_result["checkpoint_path"])
    output_path = tmp_path / "scaled_expert.safetensors"
    input_metadata = load_checkpoint_metadata(input_path)

    assert input_metadata["architecture"] == "MoEClassifier"
    assert input_metadata["expert_depth"] == 1

    result = scale_expert_checkpoint(
        input_path,
        output_path=output_path,
        training_day=45,
    )

    assert result.source_depth == 1
    assert result.scaled_depth == 2
    assert Path(result.output_path).exists()
    assert Path(f"{result.output_path}.sha256").exists()

    HardenedCheckpointManager._require_verified_file_hash(Path(result.output_path))
    scaled_metadata = load_checkpoint_metadata(result.output_path)
    scaled_state = load_safetensors(result.output_path)

    assert scaled_metadata["expert_depth"] == 2
    assert scaled_metadata["scaled_from_depth"] == 1
    assert scaled_metadata["phase16_stage_label"] == "Day 31-90"
    assert scaled_metadata["phase16_target_label"] == "512M per expert"
    assert torch.equal(
        scaled_state["moe.experts.0.fc1.weight"],
        source_state["moe.experts.0.fc1.weight"],
    )
    assert "moe.experts.0.depth_layers.0.fc1.weight" in scaled_state
    assert torch.count_nonzero(
        scaled_state["moe.experts.0.depth_layers.0.fc1.weight"]
    ).item() == 0
    assert torch.count_nonzero(
        scaled_state["moe.experts.0.depth_layers.0.fc2.weight"]
    ).item() == 0

    scaled_model = _build_classifier(depth=2)
    scaled_model.load_state_dict(scaled_state, strict=True)
