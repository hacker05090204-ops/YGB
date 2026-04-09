from __future__ import annotations

import logging

import pytest

torch = pytest.importorskip("torch")

from impl_v1.phase49.governors import g37_pytorch_backend
from training_controller import TrainingControllerConfig
from training_core.execution_impl import (
    EARLY_STOPPING_PATIENCE,
    LABEL_SMOOTHING,
    MODEL_DROPOUT,
    OPTIMIZER_LR,
    OPTIMIZER_WEIGHT_DECAY,
    _create_training_stack,
    _log_overfit_status,
    _should_save_best_checkpoint,
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
