from __future__ import annotations

import json
import time
from pathlib import Path
from types import SimpleNamespace

import numpy as np
from fastapi import FastAPI
from fastapi.testclient import TestClient

import backend.api.runtime_api as runtime_api
from backend.training.auto_train_controller import (
    AutoTrainConfig,
    AutoTrainController,
)
from backend.training.incremental_trainer import AccuracySnapshot
from backend.training.safetensors_store import SafetensorsFeatureStore


def _write_feature_shards(root: Path, sample_count: int, *, positive_ratio: float = 0.5) -> None:
    store = SafetensorsFeatureStore(root)
    positive_count = int(round(sample_count * positive_ratio))
    negative_count = max(sample_count - positive_count, 0)
    labels = ([1] * positive_count) + ([0] * negative_count)
    for index, label in enumerate(labels):
        base_vector = np.linspace(0.01, 1.01, 256, dtype=np.float32) + np.float32(index)
        feature_row = base_vector.reshape(1, 256)
        store.write(
            f"sample_{index:04d}",
            feature_row,
            np.asarray([label], dtype=np.int64),
            metadata={"sample_index": index, "label": label},
        )


class _FakeTrainer:
    def __init__(
        self,
        root: Path,
        *,
        snapshot: AccuracySnapshot,
        result_status: str = "COMPLETED",
        touch_artifacts: bool = True,
    ) -> None:
        self.calls = 0
        self.model_path = root / "checkpoints" / "g38_model_checkpoint.safetensors"
        self.baseline_path = root / "checkpoints" / "baseline_accuracy.json"
        self.state_path = root / "checkpoints" / "training_state.json"
        self.model_path.parent.mkdir(parents=True, exist_ok=True)
        self.model_path.write_text("model-0", encoding="utf-8")
        self.baseline_path.write_text(json.dumps({"baseline": 0}), encoding="utf-8")
        self.state_path.write_text(json.dumps({"epoch_number": 0}), encoding="utf-8")
        self._snapshot = snapshot
        self._result_status = result_status
        self._touch_artifacts = touch_artifacts

    def run_incremental_epoch(self):
        self.calls += 1
        if self._touch_artifacts:
            self.model_path.write_text(f"model-{self.calls}", encoding="utf-8")
            self.baseline_path.write_text(
                json.dumps({"baseline": self.calls}),
                encoding="utf-8",
            )
        return SimpleNamespace(
            status=self._result_status,
            rollback=False,
            epoch_number=self.calls,
        )

    def get_accuracy_history(self):
        return [self._snapshot]


def _passing_snapshot() -> AccuracySnapshot:
    return AccuracySnapshot(
        epoch=1,
        accuracy=0.91,
        precision=0.85,
        recall=0.81,
        f1=0.83,
        auc_roc=0.92,
        taken_at="2026-04-07T00:00:00+00:00",
    )


def _blocked_snapshot() -> AccuracySnapshot:
    return AccuracySnapshot(
        epoch=1,
        accuracy=0.74,
        precision=0.68,
        recall=0.60,
        f1=0.63,
        auc_roc=0.75,
        taken_at="2026-04-07T00:00:00+00:00",
    )


def test_controller_skips_when_not_enough_new_samples(tmp_path):
    feature_root = tmp_path / "training" / "features_safetensors"
    _write_feature_shards(feature_root, 50, positive_ratio=0.5)
    trainer = _FakeTrainer(tmp_path, snapshot=_passing_snapshot())
    controller = AutoTrainController(
        AutoTrainConfig(
            feature_store_root=feature_root,
            checkpoints_root=tmp_path / "checkpoints",
            min_new_samples=100,
        ),
        trainer=trainer,
    )

    run = controller.check_and_train()

    assert run.status == "SKIPPED"
    assert run.new_samples == 50
    assert trainer.calls == 0


def test_controller_trains_when_enough_new_samples_exist(tmp_path):
    feature_root = tmp_path / "training" / "features_safetensors"
    _write_feature_shards(feature_root, 120, positive_ratio=0.5)
    trainer = _FakeTrainer(tmp_path, snapshot=_passing_snapshot())
    controller = AutoTrainController(
        AutoTrainConfig(
            feature_store_root=feature_root,
            checkpoints_root=tmp_path / "checkpoints",
            min_new_samples=100,
        ),
        trainer=trainer,
    )

    run = controller.check_and_train()

    assert run.status == "COMPLETED"
    assert run.total_samples == 120
    assert trainer.calls == 1


def test_controller_failed_quality_gate_returns_failed(tmp_path):
    feature_root = tmp_path / "training" / "features_safetensors"
    _write_feature_shards(feature_root, 120, positive_ratio=0.0)
    trainer = _FakeTrainer(tmp_path, snapshot=_passing_snapshot())
    controller = AutoTrainController(
        AutoTrainConfig(
            feature_store_root=feature_root,
            checkpoints_root=tmp_path / "checkpoints",
            min_new_samples=100,
        ),
        trainer=trainer,
    )

    run = controller.check_and_train()

    assert run.status == "FAILED"
    assert run.error == "dataset_quality_failed"
    assert trainer.calls == 0


def test_controller_only_promotes_when_readiness_thresholds_are_met(tmp_path):
    feature_root = tmp_path / "training" / "features_safetensors"
    _write_feature_shards(feature_root, 120, positive_ratio=0.5)
    trainer = _FakeTrainer(
        tmp_path,
        snapshot=_blocked_snapshot(),
        result_status="PROMOTION_BLOCKED",
        touch_artifacts=True,
    )
    controller = AutoTrainController(
        AutoTrainConfig(
            feature_store_root=feature_root,
            checkpoints_root=tmp_path / "checkpoints",
            min_new_samples=100,
        ),
        trainer=trainer,
    )

    run = controller.check_and_train()

    assert run.status == "PROMOTION_BLOCKED"
    assert run.promoted is False
    assert controller.get_status()["last_promoted_at"] is None


def test_scheduled_loop_starts_and_stops_cleanly(tmp_path):
    feature_root = tmp_path / "training" / "features_safetensors"
    trainer = _FakeTrainer(tmp_path, snapshot=_passing_snapshot(), touch_artifacts=False)
    controller = AutoTrainController(
        AutoTrainConfig(
            feature_store_root=feature_root,
            checkpoints_root=tmp_path / "checkpoints",
            check_interval_seconds=0.05,
            min_new_samples=100,
        ),
        trainer=trainer,
    )

    assert controller.start() is True
    time.sleep(0.12)
    assert controller.is_scheduled_running() is True
    assert controller.stop(timeout=1.0) is True
    assert controller.is_scheduled_running() is False


def test_get_last_run_returns_latest_entry(tmp_path):
    feature_root = tmp_path / "training" / "features_safetensors"
    _write_feature_shards(feature_root, 100, positive_ratio=0.5)
    trainer = _FakeTrainer(tmp_path, snapshot=_passing_snapshot())
    controller = AutoTrainController(
        AutoTrainConfig(
            feature_store_root=feature_root,
            checkpoints_root=tmp_path / "checkpoints",
            min_new_samples=50,
        ),
        trainer=trainer,
    )

    first_run = controller.check_and_train()
    _write_feature_shards(feature_root, 120, positive_ratio=0.5)
    second_run = controller.check_and_train()

    assert controller.get_last_run() == second_run
    assert first_run.run_id != second_run.run_id


def test_status_endpoint_returns_requested_shape(monkeypatch):
    class _FakeController:
        def get_status(self):
            return {
                "scheduled_running": True,
                "run_in_progress": False,
                "check_interval_seconds": 60.0,
                "next_check_at": "2026-04-07T00:01:00+00:00",
                "next_check_in_seconds": 12.5,
                "last_promoted_at": "2026-04-07T00:00:00+00:00",
                "total_runs": 2,
                "last_observed_shard_count": 10,
                "last_observed_total_samples": 120,
                "last_processed_total_samples": 120,
                "last_run": {
                    "run_id": "run-2",
                    "status": "COMPLETED",
                },
            }

    monkeypatch.setattr(runtime_api, "get_auto_train_controller", lambda: _FakeController())
    app = FastAPI()
    app.include_router(runtime_api.router)
    app.dependency_overrides[runtime_api.require_auth] = lambda: {"sub": "user-1"}
    client = TestClient(app)

    response = client.get("/api/v1/training/auto/status")

    assert response.status_code == 200
    payload = response.json()
    assert payload == {
        "status": "ok",
        "scheduled_running": True,
        "run_in_progress": False,
        "check_interval_seconds": 60.0,
        "next_check_at": "2026-04-07T00:01:00+00:00",
        "next_check_in_seconds": 12.5,
        "last_promoted_at": "2026-04-07T00:00:00+00:00",
        "total_runs": 2,
        "last_observed_shard_count": 10,
        "last_observed_total_samples": 120,
        "last_processed_total_samples": 120,
        "last_run": {
            "run_id": "run-2",
            "status": "COMPLETED",
        },
    }


def test_trigger_endpoint_returns_run_id_and_status_semantics(monkeypatch):
    class _FakeController:
        def __init__(self) -> None:
            self.calls = 0

        def trigger_check(self):
            self.calls += 1
            if self.calls == 1:
                return {"run_id": "run-1", "status": "triggered"}
            return {"run_id": "run-1", "status": "already_running"}

    fake_controller = _FakeController()
    monkeypatch.setattr(
        runtime_api,
        "get_auto_train_controller",
        lambda: fake_controller,
    )
    app = FastAPI()
    app.include_router(runtime_api.router)
    app.dependency_overrides[runtime_api.require_auth] = lambda: {"sub": "user-1"}
    client = TestClient(app)

    first_response = client.post("/api/v1/training/auto/trigger")
    second_response = client.post("/api/v1/training/auto/trigger")

    assert first_response.status_code == 202
    assert first_response.json() == {"run_id": "run-1", "status": "triggered"}
    assert second_response.status_code == 200
    assert second_response.json() == {
        "run_id": "run-1",
        "status": "already_running",
    }
