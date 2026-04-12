from __future__ import annotations

import importlib
import logging

import numpy as np
import pytest

torch = pytest.importorskip("torch")

import training_controller
from impl_v1.phase49.moe import EXPERT_FIELDS
from training_core.execution_impl import (
    EARLY_STOPPING_PATIENCE,
    _log_overfit_status,
    _update_val_loss_plateau,
)


def test_moe_importable():
    module = importlib.import_module("impl_v1.phase49.moe")

    assert module.MoEClassifier.__name__ == "MoEClassifier"


def test_moe_has_23_experts():
    assert len(EXPERT_FIELDS) == 23
    assert len(EXPERT_FIELDS) == training_controller.N_EXPERTS


def test_overfitting_gap_warning(caplog):
    logger = logging.getLogger("tests.test_moe_training.warning")

    with caplog.at_level(logging.INFO, logger=logger.name):
        gap = _log_overfit_status(
            logger,
            epoch=2,
            total_epochs=10,
            train_loss=0.12,
            val_loss=0.44,
            train_f1=0.82,
            val_f1=0.62,
        )

    assert gap == pytest.approx(0.20)
    assert any(
        record.levelno == logging.WARNING
        and "overfitting detected" in record.message
        for record in caplog.records
    )


def test_overfitting_gap_critical(caplog):
    logger = logging.getLogger("tests.test_moe_training.critical")

    with caplog.at_level(logging.INFO, logger=logger.name):
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


def test_early_stopping():
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


def test_val_accuracy_only_in_report(monkeypatch):
    dataset_state = training_controller.DatasetState(
        hash="dataset-hash",
        sample_count=2,
        feature_dim=2,
        num_classes=2,
        entropy=1.0,
        trainable=True,
        manifest_path="secure_data/dataset_manifest.json",
        enforcement_passed=True,
        dataset_source="REAL_SAFETENSORS",
        verification_passed=True,
        verification_code="OK",
        verification_message="validated",
    )
    training_result = training_controller.TrainingResult(
        epochs_completed=2,
        final_loss=0.40,
        final_accuracy=0.99,
        best_accuracy=0.99,
        cluster_sps=12.5,
        merged_weight_hash="hash-123",
        drift_aborted=False,
        per_epoch=[],
        val_accuracy=0.61,
        val_f1=0.58,
        val_precision=0.57,
        val_recall=0.59,
        best_val_loss=0.39,
        checkpoint_path="checkpoints/expert_00_web_vulns_e2_f10.5800.safetensors",
        status="COMPLETED",
    )
    captured_writes: list[tuple[str, dict[str, object]]] = []

    monkeypatch.setattr(
        training_controller,
        "phase1_architecture_freeze",
        lambda config: {"frozen": True},
    )
    monkeypatch.setattr(
        training_controller,
        "phase2_dataset_finalization",
        lambda config: (
            dataset_state,
            np.asarray([[1.0, 2.0], [3.0, 4.0]], dtype=np.float32),
            np.asarray([0, 1], dtype=np.int64),
        ),
    )
    monkeypatch.setattr(
        training_controller,
        "phase3_training_execution",
        lambda config, X, y, dataset_hash: training_result,
    )
    monkeypatch.setattr(
        training_controller,
        "phase4_model_freeze",
        lambda config, result, dataset_hash: {"version_id": "v_test"},
    )
    monkeypatch.setattr(
        training_controller,
        "phase5_post_training",
        lambda config, result, dataset, model_freeze: {"ok": True},
    )
    monkeypatch.setattr(
        training_controller,
        "_atomic_write_json",
        lambda path, payload: captured_writes.append((str(path), dict(payload))),
    )

    final_report = training_controller.main(
        training_controller.TrainingControllerConfig(
            input_dim=2,
            hidden_dim=8,
            num_classes=2,
            num_epochs=1,
            world_size=1,
            rank=0,
        )
    )

    assert final_report["val_accuracy"] == pytest.approx(0.61)
    assert final_report["val_accuracy"] != pytest.approx(training_result.final_accuracy)
    assert "final_accuracy" not in final_report
    assert captured_writes[-1][1]["val_accuracy"] == pytest.approx(0.61)

