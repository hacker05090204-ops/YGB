from __future__ import annotations

import logging

import numpy as np
import pytest

torch = pytest.importorskip("torch")

import training_controller
from impl_v1.phase49.governors import g37_pytorch_backend
from training_controller import TrainingControllerConfig
from training_core.execution_impl import (
    DATA_SPLIT_SEED,
    EARLY_STOPPING_PATIENCE,
    LABEL_SMOOTHING,
    MODEL_DROPOUT,
    OPTIMIZER_LR,
    OPTIMIZER_WEIGHT_DECAY,
    _create_training_stack,
    _log_overfit_status,
    _should_save_best_checkpoint,
    _split_train_validation_test,
    _update_val_loss_plateau,
)


def test_overfit_gap_logs_critical_when_gap_exceeds_threshold(caplog):
    logger = logging.getLogger("training-overfit-guard-test")

    with caplog.at_level(logging.INFO, logger="training-overfit-guard-test"):
        gap = _log_overfit_status(
            logger,
            epoch=3,
            total_epochs=10,
            train_loss=0.10,
            val_loss=0.90,
            train_f1=0.91,
            val_f1=0.60,
        )

    assert gap == pytest.approx(0.31)
    assert any(
        record.levelno == logging.CRITICAL
        and "severe overfitting — check data" in record.message
        for record in caplog.records
    )


def test_checkpoint_selection_uses_val_f1_not_train_f1():
    assert (
        _should_save_best_checkpoint(
            0.80,
            train_f1=0.99,
            val_f1=0.79,
        )
        is False
    )
    assert (
        _should_save_best_checkpoint(
            0.80,
            train_f1=0.81,
            val_f1=0.82,
        )
        is True
    )


def test_bugclassifier_architecture_contains_dropout_layers():
    config = g37_pytorch_backend.create_model_config()
    model = g37_pytorch_backend.BugClassifier(config)

    dropout_modules = [
        module for module in model.modules() if isinstance(module, torch.nn.Dropout)
    ]

    assert dropout_modules
    assert all(module.p == pytest.approx(MODEL_DROPOUT) for module in dropout_modules)


def test_training_stack_enforces_label_smoothing_weight_decay_and_capacity(tmp_path):
    config = TrainingControllerConfig(
        input_dim=32,
        hidden_dim=64,
        num_classes=2,
        num_epochs=1,
        base_batch_size=16,
        base_lr=0.001,
        world_size=1,
        rank=0,
        use_amp=False,
        use_bf16=False,
        monitor_training=False,
        checkpoint_every_epoch=False,
        async_checkpoints=False,
        resume_if_available=False,
        checkpoint_dir=str(tmp_path / "checkpoints"),
        experiment_dir=str(tmp_path / "experiments"),
        model_dir=str(tmp_path / "models"),
        dataset_cache_dir=str(tmp_path / "dataset_cache"),
        tiered_checkpoint_storage=False,
        adaptive_batch_size=False,
        auto_batch_tuning=False,
        gradient_checkpointing=False,
        async_pipeline=False,
        use_flash_attention=False,
    )

    model, optimizer, criterion, effective_hidden_dim = _create_training_stack(
        config,
        total_samples=9_999,
        device=torch.device("cpu"),
        optim_module=torch.optim,
        nn_module=torch.nn,
    )

    assert criterion.label_smoothing == pytest.approx(LABEL_SMOOTHING)
    assert optimizer.param_groups[0]["lr"] == pytest.approx(OPTIMIZER_LR)
    assert optimizer.param_groups[0]["weight_decay"] == pytest.approx(
        OPTIMIZER_WEIGHT_DECAY
    )
    assert effective_hidden_dim == 32

    dropout_modules = [
        module for module in model.modules() if isinstance(module, torch.nn.Dropout)
    ]
    assert dropout_modules
    assert all(module.p == pytest.approx(MODEL_DROPOUT) for module in dropout_modules)


def test_split_train_validation_test_is_deterministic_and_uses_exact_global_sizes():
    X = np.arange(20, dtype=np.float32).reshape(20, 1)
    y = np.asarray([0] * 10 + [1] * 10, dtype=np.int64)

    first = _split_train_validation_test(X, y, seed=DATA_SPLIT_SEED)
    second = _split_train_validation_test(X, y, seed=DATA_SPLIT_SEED)

    assert [part.shape[0] for part in first[::2]] == [14, 3, 3]
    for first_part, second_part in zip(first, second):
        assert np.array_equal(first_part, second_part)

    all_feature_ids = np.concatenate([first[0].ravel(), first[2].ravel(), first[4].ravel()])
    assert sorted(all_feature_ids.tolist()) == list(range(20))
    assert set(first[0].ravel().tolist()).isdisjoint(first[2].ravel().tolist())
    assert set(first[0].ravel().tolist()).isdisjoint(first[4].ravel().tolist())
    assert set(first[2].ravel().tolist()).isdisjoint(first[4].ravel().tolist())


def test_active_moe_classifier_hidden_dim_reduces_by_half_for_small_datasets(monkeypatch):
    monkeypatch.setenv("YGB_USE_MOE", "true")
    config = TrainingControllerConfig(input_dim=32, hidden_dim=512, num_classes=2)

    small_model, small_hidden_dim = training_controller._build_configured_model(
        config=config,
        total_samples=9_999,
        effective_hidden_dim=256,
        device=torch.device("cpu"),
        nn_module=torch.nn,
    )
    large_model, large_hidden_dim = training_controller._build_configured_model(
        config=config,
        total_samples=10_000,
        effective_hidden_dim=512,
        device=torch.device("cpu"),
        nn_module=torch.nn,
    )

    assert small_model.config.d_model == 128
    assert small_hidden_dim == 128
    assert large_model.config.d_model == 256
    assert large_hidden_dim == 256


def test_early_stopping_triggers_on_validation_loss_plateau():
    best_val_loss = float("inf")
    plateau_count = 0
    should_stop = False

    for current_val_loss in (0.50, 0.50, 0.50, 0.50, 0.50, 0.50):
        best_val_loss, plateau_count, should_stop = _update_val_loss_plateau(
            best_val_loss,
            plateau_count,
            current_val_loss,
        )

    assert best_val_loss == pytest.approx(0.50)
    assert plateau_count == EARLY_STOPPING_PATIENCE
    assert should_stop is True
