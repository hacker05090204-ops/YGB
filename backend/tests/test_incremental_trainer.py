from __future__ import annotations

from dataclasses import replace
import logging
from types import SimpleNamespace

import pytest
import torch

from backend.ingestion.models import make_sample
from backend.training.feature_extractor import CVEFeatureEngineer
from backend.training.incremental_trainer import IncrementalTrainer, TrainingLoopResult
from backend.training.rl_feedback import OutcomeSignal, RewardBuffer
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


def _quality_gate_samples(count: int):
    severities = ("CRITICAL", "HIGH", "MEDIUM", "LOW", "INFORMATIONAL")
    samples = []
    for index in range(count):
        severity = severities[index % len(severities)]
        raw_text = (
            f"{severity} vulnerability bulletin for CVE-2026-{1000 + index:04d} includes "
            "exploit analysis, vendor impact, remediation guidance, CVSS context, "
            "patch urgency, and operational response details."
        )
        tags = (
            ("rce", "kev", "exploit")
            if severity in {"CRITICAL", "HIGH", "MEDIUM"}
            else ("patch", "advisory")
        )
        samples.append(
            make_sample(
                "nvd",
                raw_text,
                f"https://example.com/{index}",
                f"CVE-2026-{1000 + index:04d}",
                severity,
                tags,
            )
        )
    return samples


def _stable_feature_vector(sample) -> torch.Tensor:
    suffix = int(str(sample.cve_id).rsplit("-", maxsplit=1)[-1])
    offset = float(suffix % 13) / 100.0
    return torch.linspace(
        0.01 + offset,
        1.01 + offset,
        CVEFeatureEngineer.FEATURE_DIM,
        dtype=torch.float32,
    )


def _passing_training_loop_result() -> TrainingLoopResult:
    return TrainingLoopResult(
        train_loss=0.12,
        eval_loss=0.08,
        accuracy=0.93,
        precision=0.91,
        recall=0.90,
        f1=0.905,
        auc_roc=0.95,
        positive_threshold=0.5,
        threshold_strategy="unit_test",
        predictions=[0, 1, 0, 1],
        labels=[0, 1, 0, 1],
        probability_rows=[
            [0.95, 0.05],
            [0.05, 0.95],
            [0.90, 0.10],
            [0.10, 0.90],
        ],
        hard_negative_indices=[],
        epochs_completed=1,
        early_stopped=False,
        metrics_report=None,
    )


def _allow_governance_gate(monkeypatch) -> None:
    monkeypatch.setattr(
        "backend.training.incremental_trainer.check_kill_switch",
        lambda: None,
    )
    monkeypatch.setattr(
        "backend.training.incremental_trainer.check_training_gate",
        lambda features, labels, n_classes, source_id="ingestion_pipeline": SimpleNamespace(
            checks_passed=9,
            checks_run=9,
            duration_ms=0.0,
        ),
    )


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


def test_incremental_trainer_run_epoch_uses_native_reward_buffer_weights(
    monkeypatch,
    tmp_path,
    caplog,
):
    _allow_governance_gate(monkeypatch)
    reward_buffer = RewardBuffer(path=tmp_path / "rl_reward_buffer.json")
    monkeypatch.setattr(
        "backend.training.incremental_trainer.get_training_state_manager",
        lambda: _FakeStateManager(),
    )
    monkeypatch.setattr(
        "backend.training.incremental_trainer.get_reward_buffer",
        lambda: reward_buffer,
    )
    monkeypatch.setattr(
        "backend.training.runtime_status_validator.validate_promotion_readiness",
        lambda snapshot: True,
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
    trainer.feature_engineer.extract = _stable_feature_vector
    trainer._save_model_state = lambda *args, **kwargs: None
    trainer._save_named_checkpoint = lambda *args, **kwargs: tmp_path / "noop.pt"
    trainer._persist_checkpoint_metrics = lambda **kwargs: None

    samples = _quality_gate_samples(100)
    for sample in samples[:20]:
        reward_buffer.add(
            OutcomeSignal(
                sample_id=sample.sha256_hash,
                cve_id=sample.cve_id,
                predicted_severity=sample.severity,
                outcome="kev_exploit_confirmed",
                reward=1.0,
                source="cisa_kev",
            )
        )

    captured: dict[str, object] = {}

    def _fake_train(
        train_loader,
        optimizer,
        scheduler,
        criterion,
        scaler,
        *,
        sample_weights=None,
        **kwargs,
    ):
        captured["sample_weights"] = (
            sample_weights.copy() if sample_weights is not None else None
        )
        return _passing_training_loop_result()

    trainer.train = _fake_train
    trainer.load_new_samples = lambda: samples

    with caplog.at_level(logging.INFO, logger="ygb.training.incremental_trainer"):
        result = trainer.run_incremental_epoch()

    assert result.rollback is False
    assert captured["sample_weights"] is not None
    assert float(captured["sample_weights"].max()) > 1.0
    assert "incremental_rl_reward_weights matched_samples=" in caplog.text
    assert "incremental_rl_weighting matched_samples=" in caplog.text
    assert "matched_rows=" in caplog.text


def test_incremental_trainer_run_epoch_uses_cve_fallback_reward_weights(
    monkeypatch,
    tmp_path,
    caplog,
):
    _allow_governance_gate(monkeypatch)
    reward_buffer = RewardBuffer(path=tmp_path / "rl_reward_buffer.json")
    monkeypatch.setattr(
        "backend.training.incremental_trainer.get_training_state_manager",
        lambda: _FakeStateManager(),
    )
    monkeypatch.setattr(
        "backend.training.incremental_trainer.get_reward_buffer",
        lambda: reward_buffer,
    )
    monkeypatch.setattr(
        "backend.training.runtime_status_validator.validate_promotion_readiness",
        lambda snapshot: True,
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
    trainer.feature_engineer.extract = _stable_feature_vector
    trainer._save_model_state = lambda *args, **kwargs: None
    trainer._save_named_checkpoint = lambda *args, **kwargs: tmp_path / "noop.pt"
    trainer._persist_checkpoint_metrics = lambda **kwargs: None

    samples = _quality_gate_samples(100)
    for sample in samples[:10]:
        reward_buffer.add(
            OutcomeSignal(
                sample_id=f"external::{sample.cve_id}",
                cve_id=sample.cve_id,
                predicted_severity=sample.severity,
                outcome="kev_exploit_confirmed",
                reward=1.0,
                source="cisa_kev",
            )
        )

    captured: dict[str, object] = {}

    def _fake_train(
        train_loader,
        optimizer,
        scheduler,
        criterion,
        scaler,
        *,
        sample_weights=None,
        **kwargs,
    ):
        captured["sample_weights"] = (
            sample_weights.copy() if sample_weights is not None else None
        )
        return _passing_training_loop_result()

    trainer.train = _fake_train
    trainer.load_new_samples = lambda: samples

    with caplog.at_level(logging.INFO, logger="ygb.training.incremental_trainer"):
        trainer.run_incremental_epoch()

    assert captured["sample_weights"] is not None
    assert float(captured["sample_weights"].max()) > 1.0
    assert "matched_cve_fallback=" in caplog.text


def test_incremental_trainer_native_reward_weights_do_not_double_count_external_dict(
    monkeypatch,
    tmp_path,
    caplog,
):
    _allow_governance_gate(monkeypatch)
    reward_buffer = RewardBuffer(path=tmp_path / "rl_reward_buffer.json")
    monkeypatch.setattr(
        "backend.training.incremental_trainer.get_training_state_manager",
        lambda: _FakeStateManager(),
    )
    monkeypatch.setattr(
        "backend.training.incremental_trainer.get_reward_buffer",
        lambda: reward_buffer,
    )
    monkeypatch.setattr(
        "backend.training.runtime_status_validator.validate_promotion_readiness",
        lambda snapshot: True,
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
    trainer.feature_engineer.extract = _stable_feature_vector
    trainer._save_model_state = lambda *args, **kwargs: None
    trainer._save_named_checkpoint = lambda *args, **kwargs: tmp_path / "noop.pt"
    trainer._persist_checkpoint_metrics = lambda **kwargs: None

    samples = _quality_gate_samples(100)
    external_weights: dict[str, float] = {}
    for sample in samples[:20]:
        reward_buffer.add(
            OutcomeSignal(
                sample_id=sample.sha256_hash,
                cve_id=sample.cve_id,
                predicted_severity=sample.severity,
                outcome="kev_exploit_confirmed",
                reward=1.0,
                source="cisa_kev",
            )
        )
        external_weights[sample.sha256_hash] = 2.0

    captured: dict[str, object] = {}

    def _fake_train(
        train_loader,
        optimizer,
        scheduler,
        criterion,
        scaler,
        *,
        sample_weights=None,
        **kwargs,
    ):
        captured["sample_weights"] = (
            sample_weights.copy() if sample_weights is not None else None
        )
        return _passing_training_loop_result()

    trainer.train = _fake_train
    trainer.load_new_samples = lambda: samples

    with caplog.at_level(logging.INFO, logger="ygb.training.incremental_trainer"):
        trainer.run_incremental_epoch(sample_weights=external_weights)

    assert captured["sample_weights"] is not None
    assert float(captured["sample_weights"].max()) == pytest.approx(2.0)
    assert "merge_strategy=external_dict_overrides" in caplog.text


def test_incremental_trainer_build_dataset_uses_weighted_random_sampler_when_weights_exist(
    monkeypatch,
    tmp_path,
):
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
    trainer.feature_engineer.extract = _stable_feature_vector

    samples = _quality_gate_samples(100)
    weighted_sample = samples[0]
    train_loader, _ = trainer.build_dataset(
        samples,
        include_train_dataset_indices=True,
        sample_weights={weighted_sample.cve_id: 3.0},
    )

    assert isinstance(train_loader.sampler, torch.utils.data.WeightedRandomSampler)
    assert float(torch.as_tensor(train_loader.sampler.weights).max().item()) == pytest.approx(3.0)


def test_incremental_trainer_run_epoch_logs_effective_label_smoothing(
    monkeypatch,
    tmp_path,
    caplog,
):
    _allow_governance_gate(monkeypatch)
    monkeypatch.setattr(
        "backend.training.incremental_trainer.get_training_state_manager",
        lambda: _FakeStateManager(),
    )
    monkeypatch.setattr(
        "backend.training.incremental_trainer.get_reward_buffer",
        lambda: RewardBuffer(path=tmp_path / "empty_rl_reward_buffer.json"),
    )
    monkeypatch.setattr(
        "backend.training.runtime_status_validator.validate_promotion_readiness",
        lambda snapshot: True,
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
    trainer.feature_engineer.extract = _stable_feature_vector
    trainer.optimizer_config = replace(trainer.optimizer_config, label_smoothing=0.2)
    trainer._save_model_state = lambda *args, **kwargs: None
    trainer._save_named_checkpoint = lambda *args, **kwargs: tmp_path / "noop.pt"
    trainer._persist_checkpoint_metrics = lambda **kwargs: None

    captured: dict[str, object] = {}

    def _fake_train(
        train_loader,
        optimizer,
        scheduler,
        criterion,
        scaler,
        *,
        sample_weights=None,
        **kwargs,
    ):
        captured["label_smoothing"] = float(getattr(criterion, "label_smoothing"))
        return _passing_training_loop_result()

    trainer.train = _fake_train
    trainer.load_new_samples = lambda: _quality_gate_samples(100)

    with caplog.at_level(logging.INFO, logger="ygb.training.incremental_trainer"):
        trainer.run_incremental_epoch()

    assert captured["label_smoothing"] == pytest.approx(0.2)
    assert "incremental_label_smoothing_configured" in caplog.text
    assert "label_smoothing=0.200000" in caplog.text


def test_incremental_trainer_run_epoch_invokes_hard_training_gate(
    monkeypatch,
    tmp_path,
):
    monkeypatch.setattr(
        "backend.training.incremental_trainer.get_training_state_manager",
        lambda: _FakeStateManager(),
    )
    monkeypatch.setattr(
        "backend.training.incremental_trainer.get_reward_buffer",
        lambda: RewardBuffer(path=tmp_path / "empty_rl_reward_buffer.json"),
    )
    monkeypatch.setattr(
        "backend.training.runtime_status_validator.validate_promotion_readiness",
        lambda snapshot: True,
    )
    monkeypatch.setattr(
        "backend.training.incremental_trainer.check_kill_switch",
        lambda: None,
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
    trainer.feature_engineer.extract = _stable_feature_vector
    trainer._save_model_state = lambda *args, **kwargs: None
    trainer._save_named_checkpoint = lambda *args, **kwargs: tmp_path / "noop.pt"
    trainer._persist_checkpoint_metrics = lambda **kwargs: None

    samples = _quality_gate_samples(100)
    captured: dict[str, object] = {}

    def _fake_gate(features, labels, n_classes, source_id="ingestion_pipeline"):
        captured["feature_shape"] = tuple(features.shape)
        captured["label_count"] = int(labels.shape[0])
        captured["n_classes"] = int(n_classes)
        captured["source_id"] = str(source_id)
        return SimpleNamespace(checks_passed=9, checks_run=9, duration_ms=1.0)

    def _fake_train(*args, **kwargs):
        return _passing_training_loop_result()

    monkeypatch.setattr(
        "backend.training.incremental_trainer.check_training_gate",
        _fake_gate,
    )
    trainer.train = _fake_train
    trainer.load_new_samples = lambda: samples

    result = trainer.run_incremental_epoch()

    assert result.rollback is False
    assert captured["feature_shape"] == (100, 512)
    assert captured["label_count"] == 100
    assert captured["n_classes"] == 2
    assert captured["source_id"] == "ingestion_pipeline"


def test_incremental_trainer_checks_kill_switch_each_training_batch(
    monkeypatch,
    tmp_path,
):
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
    kill_checks = {"count": 0}

    def _record_kill_switch() -> None:
        kill_checks["count"] += 1

    monkeypatch.setattr(
        "backend.training.incremental_trainer.check_kill_switch",
        _record_kill_switch,
    )

    trainer._train_single_epoch(
        train_loader,
        optimizer,
        scheduler,
        criterion,
        None,
        accumulation_steps=1,
        gradient_clip_norm=1.0,
        amp_enabled=False,
    )

    assert kill_checks["count"] == len(train_loader)
