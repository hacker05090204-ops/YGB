from __future__ import annotations

from contextlib import nullcontext
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np
import pytest
import torch

from backend.ingestion.models import IngestedSample, make_sample, sample_to_dict
from backend.observability.metrics import metrics_registry
from backend.training import feature_extractor
from backend.training.data_watcher import DataWatcher
from backend.training.feature_extractor import build_vocabulary, extract as extract_features, get_text_embedding, load_vocabulary
from backend.training.incremental_trainer import EpochResult, IncrementalTrainer
from backend.training.state_manager import TrainingMetrics, TrainingPausedException, TrainingStateManager


class FakeStateManager:
    def __init__(self) -> None:
        self.emit_calls: list[dict[str, object]] = []

    def get_gpu_metrics(self, force_emit: bool = False):
        return {"gpu_usage_percent": 12.5, "gpu_memory_used_mb": 256.0}

    def emit_training_metrics(self, metrics, **kwargs):
        self.emit_calls.append({"metrics": metrics, "kwargs": kwargs})


class FakeObserver:
    def __init__(self, fail_start: bool = False) -> None:
        self.fail_start = fail_start
        self.scheduled = []
        self.started = False
        self.stopped = False
        self.joined = False

    def schedule(self, handler, path, recursive=True):
        self.scheduled.append((handler, path, recursive))

    def start(self):
        if self.fail_start:
            raise RuntimeError("observer failed")
        self.started = True

    def stop(self):
        self.stopped = True

    def join(self):
        self.joined = True

    def is_alive(self):
        return self.started and not self.stopped


class FakeScheduler:
    def __init__(self) -> None:
        self.jobs = []
        self.started = False
        self.shutdown_called = False

    def add_job(self, func, trigger):
        self.jobs.append((func, trigger))

    def start(self):
        self.started = True

    def shutdown(self, wait=False):
        self.shutdown_called = True


class FakeTrainer:
    def __init__(self) -> None:
        self.calls = 0

    def run_incremental_epoch(self):
        self.calls += 1
        return "ran"


@pytest.fixture(autouse=True)
def reset_metrics():
    metrics_registry.reset()
    yield


def _write_sample(root: Path, sample: IngestedSample) -> None:
    date_dir = root / sample.source / sample.ingested_at.date().isoformat()
    date_dir.mkdir(parents=True, exist_ok=True)
    (date_dir / f"{sample.sha256_hash}.json").write_text(json.dumps(sample_to_dict(sample), indent=2), encoding="utf-8")


def _sample_with_time(index: int, *, hours_ago: int = 0, positive: bool = True) -> IngestedSample:
    sample = make_sample(
        "nvd" if positive else "bugcrowd",
        f"sample text {index}",
        f"https://example.com/{index}",
        f"CVE-2026-{index:04d}" if positive else "",
        "HIGH" if positive else "INFO",
        ("tag",),
    )
    return IngestedSample(
        source=sample.source,
        raw_text=sample.raw_text,
        url=sample.url,
        cve_id=sample.cve_id,
        severity=sample.severity,
        tags=sample.tags,
        ingested_at=datetime.now(timezone.utc) - timedelta(hours=hours_ago),
        sha256_hash=sample.sha256_hash,
        token_count=sample.token_count,
        lang=sample.lang,
    )


def _feature_vector(sample: IngestedSample) -> torch.Tensor:
    vector = torch.zeros(512, dtype=torch.float32)
    vector[0] = 1.0 if sample.cve_id else 0.0
    vector[1] = 1.0 if sample.severity in {"CRITICAL", "HIGH", "MEDIUM"} else 0.0
    vector[2] = float(sample.token_count) / 10.0
    return vector


def test_feature_extractor_builds_vocab_and_extracts_features(monkeypatch, tmp_path):
    raw_root = tmp_path / "raw"
    vocab_path = tmp_path / "vocab" / "vocab_508.json"
    sample = make_sample("hackerone", "alpha beta alpha", "https://example.com", "", "HIGH", ("tag",))
    _write_sample(raw_root, sample)
    (raw_root / "dedup_index.json").write_text(json.dumps({"seen_hashes": []}), encoding="utf-8")
    second_sample = make_sample("nvd", "gamma delta epsilon", "https://example.com/2", "CVE-2026-9999", "CRITICAL", ("tag",))
    _write_sample(raw_root, second_sample)

    monkeypatch.setattr(feature_extractor, "RAW_DATA_ROOT", raw_root)
    monkeypatch.setattr(feature_extractor, "VOCAB_PATH", vocab_path)

    vocabulary = build_vocabulary(limit=1)
    vocab_path.unlink()
    loaded = load_vocabulary()
    embedding = get_text_embedding("alpha gamma")
    combined = extract_features(sample)

    assert len(vocabulary) == 508
    assert loaded[:2] == vocabulary[:2]
    assert embedding.shape[0] == 508
    assert combined.shape[0] == 512
    assert combined[-4:].tolist()[0] == 0.75


def test_emit_training_metrics_computes_ece_and_drift(tmp_path):
    manager = TrainingStateManager()
    metrics_registry.reset()
    previous_distribution_dir = tmp_path / "checkpoints" / "dist_history"
    previous_distribution_dir.mkdir(parents=True, exist_ok=True)
    np.save(previous_distribution_dir / "epoch_0.npy", np.array([0.55, 0.45], dtype=float))

    with patch("backend.training.state_manager.PROJECT_ROOT", tmp_path):
        manager.emit_training_metrics(
            TrainingMetrics(status="training", elapsed_seconds=1.0, last_accuracy=0.8),
            calibration_labels=[0, 1, 1, 0, 1, 0, 1, 0, 1, 1],
            calibration_probabilities=[0.1, 0.9, 0.8, 0.2, 0.7, 0.4, 0.85, 0.3, 0.65, 0.95],
            distribution=[[0.6, 0.4], [0.58, 0.42]],
            epoch_number=10,
        )

    assert metrics_registry.get_gauge("ece") not in (None, 0.0)
    assert metrics_registry.get_gauge("drift_kl") not in (None, 0.0)


def test_emit_training_metrics_raises_when_drift_is_high(tmp_path):
    manager = TrainingStateManager()
    previous_distribution_dir = tmp_path / "checkpoints" / "dist_history"
    previous_distribution_dir.mkdir(parents=True, exist_ok=True)
    np.save(previous_distribution_dir / "epoch_0.npy", np.array([0.99, 0.01], dtype=float))

    with patch("backend.training.state_manager.PROJECT_ROOT", tmp_path):
        with pytest.raises(TrainingPausedException):
            manager.emit_training_metrics(
                TrainingMetrics(status="training", elapsed_seconds=1.0, last_accuracy=0.8),
                calibration_labels=[0, 1, 1, 0],
                calibration_probabilities=[0.1, 0.9, 0.8, 0.2],
                distribution=[[0.01, 0.99], [0.02, 0.98]],
                epoch_number=10,
            )


def test_incremental_trainer_load_new_samples_filters_by_last_training_time(monkeypatch, tmp_path):
    fake_state = FakeStateManager()
    raw_root = tmp_path / "raw"
    model_path = tmp_path / "checkpoints" / "model.safetensors"
    state_path = tmp_path / "checkpoints" / "training_state.json"
    baseline_path = tmp_path / "checkpoints" / "baseline_accuracy.json"
    old_sample = _sample_with_time(1, hours_ago=2)
    new_sample = _sample_with_time(2, hours_ago=0)
    _write_sample(raw_root, old_sample)
    _write_sample(raw_root, new_sample)
    (raw_root / "dedup_index.json").write_text(json.dumps({"seen_hashes": []}), encoding="utf-8")
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(json.dumps({"last_training_time": (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat(), "epoch_number": 0, "best_eval_loss": None, "no_improve_count": 0}), encoding="utf-8")
    baseline_path.write_text(json.dumps({"baseline_accuracy": 0.0}), encoding="utf-8")
    monkeypatch.setattr("backend.training.incremental_trainer.get_training_state_manager", lambda: fake_state)

    trainer = IncrementalTrainer(model_path=model_path, state_path=state_path, baseline_path=baseline_path, raw_data_root=raw_root, num_workers=0)
    loaded = trainer.load_new_samples()
    assert [sample.sha256_hash for sample in loaded] == [new_sample.sha256_hash]


def test_incremental_trainer_build_dataset_splits_90_10(monkeypatch, tmp_path):
    fake_state = FakeStateManager()
    model_path = tmp_path / "checkpoints" / "model.safetensors"
    state_path = tmp_path / "checkpoints" / "training_state.json"
    baseline_path = tmp_path / "checkpoints" / "baseline_accuracy.json"
    monkeypatch.setattr("backend.training.incremental_trainer.get_training_state_manager", lambda: fake_state)
    monkeypatch.setattr("backend.training.incremental_trainer.extract", _feature_vector)

    trainer = IncrementalTrainer(model_path=model_path, state_path=state_path, baseline_path=baseline_path, raw_data_root=tmp_path / "raw", num_workers=0)
    samples = [_sample_with_time(index, positive=index % 2 == 0) for index in range(50)]
    train_loader, eval_loader = trainer.build_dataset(samples)

    assert len(train_loader.dataset) == 45
    assert len(eval_loader.dataset) == 5


def test_incremental_trainer_raises_when_classifier_unavailable(monkeypatch, tmp_path):
    fake_state = FakeStateManager()
    monkeypatch.setattr("backend.training.incremental_trainer.get_training_state_manager", lambda: fake_state)
    monkeypatch.setattr("backend.training.incremental_trainer.BugClassifier", None)

    with pytest.raises(RuntimeError, match="BugClassifier runtime unavailable"):
        IncrementalTrainer(
            model_path=tmp_path / "checkpoints" / "model.safetensors",
            state_path=tmp_path / "checkpoints" / "training_state.json",
            baseline_path=tmp_path / "checkpoints" / "baseline_accuracy.json",
            raw_data_root=tmp_path / "raw",
            num_workers=0,
        )


def test_incremental_trainer_loads_existing_checkpoint(monkeypatch, tmp_path):
    fake_state = FakeStateManager()
    model_path = tmp_path / "checkpoints" / "model.safetensors"
    model_path.parent.mkdir(parents=True, exist_ok=True)
    model_path.write_bytes(b"checkpoint")
    monkeypatch.setattr("backend.training.incremental_trainer.get_training_state_manager", lambda: fake_state)
    monkeypatch.setattr("backend.training.incremental_trainer.load_safetensors", lambda *args, **kwargs: {})

    trainer = IncrementalTrainer(
        model_path=model_path,
        state_path=tmp_path / "checkpoints" / "training_state.json",
        baseline_path=tmp_path / "checkpoints" / "baseline_accuracy.json",
        raw_data_root=tmp_path / "raw",
        num_workers=0,
    )

    assert isinstance(trainer.model, torch.nn.Module)


def test_incremental_trainer_build_dataset_guard(monkeypatch, tmp_path):
    fake_state = FakeStateManager()
    monkeypatch.setattr("backend.training.incremental_trainer.get_training_state_manager", lambda: fake_state)
    monkeypatch.setattr("backend.training.incremental_trainer.extract", _feature_vector)
    monkeypatch.setattr("backend.training.incremental_trainer.can_ai_execute", lambda: (True, "blocked"))
    trainer = IncrementalTrainer(
        model_path=tmp_path / "checkpoints" / "model.safetensors",
        state_path=tmp_path / "checkpoints" / "training_state.json",
        baseline_path=tmp_path / "checkpoints" / "baseline_accuracy.json",
        raw_data_root=tmp_path / "raw",
        num_workers=1,
    )

    with pytest.raises(RuntimeError, match="GUARD"):
        trainer.build_dataset([_sample_with_time(index, positive=index % 2 == 0) for index in range(10)])


def test_incremental_trainer_run_epoch_emits_metrics(monkeypatch, tmp_path):
    fake_state = FakeStateManager()
    model_path = tmp_path / "checkpoints" / "model.safetensors"
    state_path = tmp_path / "checkpoints" / "training_state.json"
    baseline_path = tmp_path / "checkpoints" / "baseline_accuracy.json"
    monkeypatch.setattr("backend.training.incremental_trainer.get_training_state_manager", lambda: fake_state)
    monkeypatch.setattr("backend.training.incremental_trainer.extract", _feature_vector)

    trainer = IncrementalTrainer(model_path=model_path, state_path=state_path, baseline_path=baseline_path, raw_data_root=tmp_path / "raw", num_workers=0)
    trainer.load_new_samples = lambda: [_sample_with_time(index, positive=index % 2 == 0) for index in range(50)]

    result = trainer.run_incremental_epoch()

    assert isinstance(result, EpochResult)
    assert result.samples_processed == 50
    assert metrics_registry.get_gauge("model_precision") is not None
    assert metrics_registry.get_gauge("training_epoch_number") == 1.0
    assert fake_state.emit_calls


def test_incremental_trainer_persists_threshold_artifact(monkeypatch, tmp_path):
    fake_state = FakeStateManager()
    model_path = tmp_path / "checkpoints" / "model.safetensors"
    state_path = tmp_path / "checkpoints" / "training_state.json"
    baseline_path = tmp_path / "checkpoints" / "baseline_accuracy.json"
    monkeypatch.setattr("backend.training.incremental_trainer.get_training_state_manager", lambda: fake_state)
    monkeypatch.setattr("backend.training.incremental_trainer.extract", _feature_vector)

    trainer = IncrementalTrainer(
        model_path=model_path,
        state_path=state_path,
        baseline_path=baseline_path,
        raw_data_root=tmp_path / "raw",
        num_workers=0,
    )
    trainer.load_new_samples = lambda: [_sample_with_time(index, positive=index % 2 == 0) for index in range(50)]

    result = trainer.run_incremental_epoch()
    payload = json.loads(baseline_path.read_text(encoding="utf-8"))

    assert payload["baseline_accuracy"] == pytest.approx(result.accuracy)
    assert payload["checkpoint_accuracy"] == pytest.approx(result.accuracy)
    assert 0.0 <= payload["positive_threshold"] <= 1.0
    assert payload["checkpoint_precision"] == pytest.approx(result.precision)


def test_incremental_trainer_run_epoch_cpu_branches(monkeypatch, tmp_path):
    fake_state = FakeStateManager()
    model_path = tmp_path / "checkpoints" / "model.safetensors"
    state_path = tmp_path / "checkpoints" / "training_state.json"
    baseline_path = tmp_path / "checkpoints" / "baseline_accuracy.json"
    monkeypatch.setattr("backend.training.incremental_trainer.get_training_state_manager", lambda: fake_state)
    monkeypatch.setattr("backend.training.incremental_trainer.accuracy_score", lambda *args, **kwargs: 0.8)
    monkeypatch.setattr("backend.training.incremental_trainer.precision_score", lambda *args, **kwargs: 0.8)
    monkeypatch.setattr("backend.training.incremental_trainer.recall_score", lambda *args, **kwargs: 0.8)
    monkeypatch.setattr("backend.training.incremental_trainer.f1_score", lambda *args, **kwargs: 0.8)

    trainer = IncrementalTrainer(model_path=model_path, state_path=state_path, baseline_path=baseline_path, raw_data_root=tmp_path / "raw", num_workers=0)
    trainer.load_new_samples = lambda: [_sample_with_time(index, positive=index % 2 == 0) for index in range(60)]

    train_features = torch.randn(50, 512, dtype=torch.float32)
    train_labels = torch.tensor([index % 2 for index in range(50)], dtype=torch.long)
    eval_features = torch.randn(8, 512, dtype=torch.float32)
    eval_labels = torch.tensor([index % 2 for index in range(8)], dtype=torch.long)
    trainer.build_dataset = lambda samples: (
        torch.utils.data.DataLoader(torch.utils.data.TensorDataset(train_features, train_labels), batch_size=1, shuffle=False),
        torch.utils.data.DataLoader(torch.utils.data.TensorDataset(eval_features, eval_labels), batch_size=2, shuffle=False),
    )

    result = trainer.run_incremental_epoch()

    assert result.rollback is False
    assert metrics_registry.get_gauge("training_epoch_number") == 1.0


def test_incremental_trainer_run_epoch_cuda_scaler_branch(monkeypatch, tmp_path):
    class FakeScaler:
        def scale(self, loss):
            return loss

        def unscale_(self, optimizer):
            return None

        def step(self, optimizer):
            optimizer.step()

        def update(self):
            return None

    fake_state = FakeStateManager()
    monkeypatch.setattr("backend.training.incremental_trainer.get_training_state_manager", lambda: fake_state)
    monkeypatch.setattr("backend.training.incremental_trainer.accuracy_score", lambda *args, **kwargs: 0.85)
    monkeypatch.setattr("backend.training.incremental_trainer.precision_score", lambda *args, **kwargs: 0.85)
    monkeypatch.setattr("backend.training.incremental_trainer.recall_score", lambda *args, **kwargs: 0.85)
    monkeypatch.setattr("backend.training.incremental_trainer.f1_score", lambda *args, **kwargs: 0.85)
    monkeypatch.setattr("backend.training.incremental_trainer.torch.amp.GradScaler", lambda *args, **kwargs: FakeScaler())
    monkeypatch.setattr("backend.training.incremental_trainer.torch.amp.autocast", lambda *args, **kwargs: nullcontext())
    monkeypatch.setattr(torch.Tensor, "to", lambda self, *args, **kwargs: self, raising=False)

    trainer = IncrementalTrainer(
        model_path=tmp_path / "checkpoints" / "model.safetensors",
        state_path=tmp_path / "checkpoints" / "training_state.json",
        baseline_path=tmp_path / "checkpoints" / "baseline_accuracy.json",
        raw_data_root=tmp_path / "raw",
        num_workers=0,
    )
    trainer.device = SimpleNamespace(type="cuda")
    trainer.load_new_samples = lambda: [_sample_with_time(index, positive=index % 2 == 0) for index in range(12)]
    train_features = torch.randn(4, 512, dtype=torch.float32)
    train_labels = torch.tensor([0, 1, 0, 1], dtype=torch.long)
    eval_features = torch.randn(4, 512, dtype=torch.float32)
    eval_labels = torch.tensor([0, 1, 0, 1], dtype=torch.long)
    trainer.build_dataset = lambda samples: (
        torch.utils.data.DataLoader(torch.utils.data.TensorDataset(train_features, train_labels), batch_size=1, shuffle=False),
        torch.utils.data.DataLoader(torch.utils.data.TensorDataset(eval_features, eval_labels), batch_size=2, shuffle=False),
    )

    result = trainer.run_incremental_epoch()

    assert result.rollback is False
    assert result.epoch_number == 1


def test_incremental_trainer_optimizer_helpers_cover_cpu_and_scaler(monkeypatch, tmp_path):
    class FakeScaler:
        def __init__(self) -> None:
            self.unscaled = False
            self.stepped = False
            self.updated = False

        def scale(self, loss):
            return loss

        def unscale_(self, optimizer):
            self.unscaled = True

        def step(self, optimizer):
            self.stepped = True
            optimizer.step()

        def update(self):
            self.updated = True

    fake_state = FakeStateManager()
    monkeypatch.setattr("backend.training.incremental_trainer.get_training_state_manager", lambda: fake_state)
    trainer = IncrementalTrainer(
        model_path=tmp_path / "checkpoints" / "model.safetensors",
        state_path=tmp_path / "checkpoints" / "training_state.json",
        baseline_path=tmp_path / "checkpoints" / "baseline_accuracy.json",
        raw_data_root=tmp_path / "raw",
        num_workers=0,
    )
    model_device = trainer.device if isinstance(trainer.device, torch.device) else torch.device(trainer.device.type)

    cpu_optimizer = torch.optim.SGD(trainer.model.parameters(), lr=0.01)
    cpu_loss = trainer.model(torch.randn(2, 512, dtype=torch.float32, device=model_device)).sum()
    trainer._backward_pass(cpu_loss, None)
    trainer._step_optimizer(cpu_optimizer, None)

    scaler = FakeScaler()
    scaled_optimizer = torch.optim.SGD(trainer.model.parameters(), lr=0.01)
    scaled_loss = trainer.model(torch.randn(2, 512, dtype=torch.float32, device=model_device)).sum()
    trainer._backward_pass(scaled_loss, scaler)
    trainer._step_optimizer(scaled_optimizer, scaler)

    assert scaler.unscaled is True
    assert scaler.stepped is True
    assert scaler.updated is True


def test_incremental_trainer_circuit_breaker_rolls_back(monkeypatch, tmp_path):
    fake_state = FakeStateManager()
    model_path = tmp_path / "checkpoints" / "model.safetensors"
    state_path = tmp_path / "checkpoints" / "training_state.json"
    baseline_path = tmp_path / "checkpoints" / "baseline_accuracy.json"
    baseline_path.parent.mkdir(parents=True, exist_ok=True)
    baseline_path.write_text(json.dumps({"baseline_accuracy": 0.95}), encoding="utf-8")
    monkeypatch.setattr("backend.training.incremental_trainer.get_training_state_manager", lambda: fake_state)
    monkeypatch.setattr("backend.training.incremental_trainer.extract", _feature_vector)
    monkeypatch.setattr(
        "backend.training.incremental_trainer.calibrate_positive_threshold",
        lambda labels, probabilities, fallback_threshold=0.5: {
            "threshold": float(fallback_threshold),
            "predictions": [0 for _ in labels],
            "accuracy": 0.0,
            "precision": 0.0,
            "recall": 0.0,
            "f1": 0.0,
            "strategy": "forced_rollback_for_test",
        },
    )

    trainer = IncrementalTrainer(model_path=model_path, state_path=state_path, baseline_path=baseline_path, raw_data_root=tmp_path / "raw", num_workers=0)
    trainer.load_new_samples = lambda: [_sample_with_time(index, positive=index % 2 == 0) for index in range(50)]

    result = trainer.run_incremental_epoch()

    assert result.rollback is True
    assert metrics_registry.get_counter("training_rollback") == 1.0


def test_incremental_trainer_early_stopping(monkeypatch, tmp_path):
    fake_state = FakeStateManager()
    model_path = tmp_path / "checkpoints" / "model.safetensors"
    state_path = tmp_path / "checkpoints" / "training_state.json"
    baseline_path = tmp_path / "checkpoints" / "baseline_accuracy.json"
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(json.dumps({"last_training_time": datetime.fromtimestamp(0, timezone.utc).isoformat(), "epoch_number": 2, "best_eval_loss": 0.0, "no_improve_count": 2}), encoding="utf-8")
    baseline_path.write_text(json.dumps({"baseline_accuracy": 0.0}), encoding="utf-8")
    monkeypatch.setattr("backend.training.incremental_trainer.get_training_state_manager", lambda: fake_state)
    monkeypatch.setattr("backend.training.incremental_trainer.extract", _feature_vector)

    trainer = IncrementalTrainer(model_path=model_path, state_path=state_path, baseline_path=baseline_path, raw_data_root=tmp_path / "raw", num_workers=0)
    trainer.load_new_samples = lambda: [_sample_with_time(index, positive=index % 2 == 0) for index in range(50)]

    result = trainer.run_incremental_epoch()
    assert result.early_stopped is True


def test_incremental_trainer_insufficient_samples(monkeypatch, tmp_path):
    fake_state = FakeStateManager()
    monkeypatch.setattr("backend.training.incremental_trainer.get_training_state_manager", lambda: fake_state)
    trainer = IncrementalTrainer(
        model_path=tmp_path / "checkpoints" / "model.safetensors",
        state_path=tmp_path / "checkpoints" / "training_state.json",
        baseline_path=tmp_path / "checkpoints" / "baseline_accuracy.json",
        raw_data_root=tmp_path / "raw",
        num_workers=0,
    )
    trainer.load_new_samples = lambda: [_sample_with_time(index) for index in range(5)]
    result = trainer.run_incremental_epoch()
    assert result.samples_processed == 5
    assert result.rollback is False


def test_data_watcher_triggers_on_file_count_and_time(monkeypatch, tmp_path):
    trainer = FakeTrainer()
    observer = FakeObserver()
    watcher = DataWatcher(
        watch_path=str(tmp_path),
        trainer=trainer,
        state_path=str(tmp_path / "training_state.json"),
        observer_factory=lambda: observer,
        scheduler_factory=FakeScheduler,
    )

    watcher.on_created(SimpleNamespace(is_directory=False, src_path="one.json"))
    assert watcher.new_file_count == 1

    watcher.new_file_count = 501
    watcher._check_trigger()
    assert trainer.calls == 1
    assert metrics_registry.get_counter("data_watcher_trigger_count") == 1.0

    watcher.last_trigger_time = datetime.now(timezone.utc) - timedelta(hours=7)
    watcher._check_trigger()
    assert trainer.calls == 2


def test_data_watcher_scheduler_fallback_and_stop(tmp_path):
    trainer = FakeTrainer()
    observer = FakeObserver(fail_start=True)
    scheduler = FakeScheduler()
    watcher = DataWatcher(
        watch_path=str(tmp_path),
        trainer=trainer,
        state_path=str(tmp_path / "training_state.json"),
        observer_factory=lambda: observer,
        scheduler_factory=lambda: scheduler,
    )
    watcher.start()
    watcher.stop()

    assert scheduler.started is True
    assert scheduler.shutdown_called is True


def test_data_watcher_loads_last_trigger_time_and_stops_live_observer(tmp_path):
    trainer = FakeTrainer()
    observer = FakeObserver()
    last_training_time = datetime.now(timezone.utc) - timedelta(hours=2)
    state_path = tmp_path / "training_state.json"
    state_path.write_text(json.dumps({"last_training_time": last_training_time.isoformat()}), encoding="utf-8")
    watcher = DataWatcher(
        watch_path=str(tmp_path),
        trainer=trainer,
        state_path=str(state_path),
        observer_factory=lambda: observer,
        scheduler_factory=FakeScheduler,
    )

    assert watcher.last_trigger_time == last_training_time
    watcher.start()
    watcher.stop()

    assert observer.stopped is True
    assert observer.joined is True
