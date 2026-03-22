from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest
import torch

from impl_v1.phase49.governors import g37_pytorch_backend
from training.safetensors_io import load_safetensors, save_safetensors


def _load_migration_module():
    module_path = Path("scripts/migrate_checkpoint_to_v2.py")
    spec = importlib.util.spec_from_file_location("migrate_checkpoint_to_v2", module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_bugclassifier_v2_structure():
    config = g37_pytorch_backend.create_model_config()
    model = g37_pytorch_backend.BugClassifier(config)
    output = model(torch.randn(2, 512))

    assert config.input_dim == 512
    assert config.hidden_dims == (1024, 512, 256, 128)
    assert output.shape == (2, 2)
    assert any(isinstance(module, g37_pytorch_backend.ResidualBlock) for module in model.modules())
    assert any(isinstance(module, torch.nn.LayerNorm) for module in model.modules())
    assert any(isinstance(module, torch.nn.GELU) for module in model.modules())


def test_checkpoint_migration_to_v2(tmp_path):
    migration_module = _load_migration_module()
    model = g37_pytorch_backend.BugClassifier(g37_pytorch_backend.create_model_config())
    original_state = model.state_dict()
    input_path = tmp_path / "legacy.safetensors"
    output_path = tmp_path / "migrated.safetensors"
    partial_state = dict(list(original_state.items())[:3])
    save_safetensors(partial_state, str(input_path), metadata={"epoch_number": "0"})

    result = migration_module.migrate_checkpoint(str(input_path), str(output_path))
    migrated_state = load_safetensors(str(output_path), device="cpu")

    assert output_path.exists()
    assert result["mapped_keys"]
    assert result["unmapped_keys"]
    assert set(migrated_state.keys()) == set(original_state.keys())
