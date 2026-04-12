from __future__ import annotations

from dataclasses import replace

import pytest
import torch

from backend.ingestion.models import make_sample
from backend.training.feature_extractor import CVEFeatureEngineer
from backend.training.incremental_trainer import IncrementalTrainer
from backend.training.training_optimizer import WarmupCosineScheduler


class _FakeStateManager:
    def get_gpu_metrics(self, force_emit: bool = False):
        return {"gpu_usage_percent": 0.0, "gpu_memory_used_mb": 0.0}

    def emit_training_metrics(self, metrics, **kwargs):
        return None


class _ZeroEwcAdaptiveLearner:
    def __init__(self) -> None:
        self.attached_model = None

    def attach_model(self, model: torch.nn.Module) -> None:
        self.attached_model = model

    def get_ewc_loss(self) -> torch.Tensor:
        return torch.tensor(0.0, dtype=torch.float32)


def test_incremental_trainer_applies_gradient_clipping(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "backend.training.incremental_trainer.get_training_state_manager",
        lambda: _FakeStateManager(),
    )
    trainer = IncrementalTrainer(
        model_path=tmp_path / "checkpoints" / "model.safetensors",
        state_path=tmp_path / "checkpoints" / "training_state.json",
        baseline_path=tmp_path / "checkpoints" / "baseline_accuracy.json",
        raw_data_root=tmp_path / "raw",
        num_workers=0,
    )
    trainer.device = torch.device("cpu")
    trainer.model = trainer.model.to(trainer.device)
    trainer.adaptive_learner = _ZeroEwcAdaptiveLearner()

    features = torch.randn(4, 512, dtype=torch.float32)
    labels = torch.tensor([0, 1, 0, 1], dtype=torch.long)
    train_loader = torch.utils.data.DataLoader(
        torch.utils.data.TensorDataset(features, labels),
        batch_size=2,
        shuffle=False,
    )
    optimizer = torch.optim.SGD(trainer.model.parameters(), lr=0.01)
    scheduler = WarmupCosineScheduler(
        optimizer,
        total_steps=len(train_loader),
        warmup_steps=0,
        min_lr=0.0,
    )
    criterion = torch.nn.CrossEntropyLoss(reduction="none")
    optimiser_config = replace(
        trainer.optimizer_config,
        max_epochs=1,
        accumulation_steps=1,
        gradient_clip_norm=0.5,
        use_amp=False,
    )

    clip_calls: list[float] = []
    original_clip = torch.nn.utils.clip_grad_norm_

    def _recording_clip(parameters, max_norm, *args, **kwargs):
        clip_calls.append(float(max_norm))
        return original_clip(parameters, max_norm, *args, **kwargs)

    monkeypatch.setattr(
        "backend.training.incremental_trainer.torch.nn.utils.clip_grad_norm_",
        _recording_clip,
    )

    loss = trainer.train(
        train_loader,
        optimizer,
        scheduler,
        criterion,
        None,
        optimiser_config=optimiser_config,
    )

    assert isinstance(loss, float)
    assert loss >= 0.0
    assert clip_calls
    assert all(call == pytest.approx(0.5) for call in clip_calls)
    assert trainer.adaptive_learner.attached_model is trainer.model


def test_cve_feature_engineer_emits_267_dimensions_and_rce_signal(tmp_path):
    sample = make_sample(
        "nvd",
        "Critical remote code execution exploit with CVSS 9.8 actively exploited in the wild and patch immediately.",
        "https://example.com/rce",
        "CVE-2026-4242",
        "CRITICAL",
        ("rce", "kev"),
    )
    engineer = CVEFeatureEngineer(
        raw_data_root=tmp_path / "raw",
        vocab_path=tmp_path / "vocab" / "vocab_256.json",
    )

    features = engineer.extract(sample)

    assert features.shape == (267,)
    assert features[engineer.signal_index("critical_severity_cue")].item() == pytest.approx(1.0)
    assert features[engineer.signal_index("exploit_cue")].item() == pytest.approx(1.0)
    assert features[engineer.signal_index("rce_cue")].item() == pytest.approx(1.0)
    assert features[
        engineer.signal_index("known_exploited_or_patch_urgency_cue")
    ].item() == pytest.approx(1.0)
