from __future__ import annotations

from contextlib import nullcontext
from dataclasses import replace
import json
import logging
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
from backend.training.incremental_trainer import (
    AccuracyHistory,
    AccuracySnapshot,
    DatasetQualityError,
    DatasetQualityGate,
    EpochResult,
    IncrementalTrainer,
    _StreamingFeatureDataset,
)
from backend.training.state_manager import TrainingMetrics, TrainingPausedException, TrainingStateManager
from backend.training.training_optimizer import (
    EarlyStopping,
    HardNegativeMiner,
    WarmupCosineScheduler,
)


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


def _quality_gate_sample(
    index: int,
    *,
    hours_ago: int = 0,
    severity: str | None = None,
) -> IngestedSample:
    severities = ("CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO")
    selected_severity = severity or severities[index % len(severities)]
    description = (
        f"Detailed vulnerability report {index} with reproducible exploit evidence, "
        "affected service context, remediation guidance, analyst verification, and "
        "public exploit telemetry preserved for backend hardening validation."
    )
    sample = make_sample(
        "nvd",
        description,
        f"https://example.com/vuln/{index}",
        f"CVE-2026-{index:05d}",
        selected_severity,
        ("exploit", "verified"),
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


def _quality_gate_samples(count: int) -> list[IngestedSample]:
    return [_quality_gate_sample(index) for index in range(count)]


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
    samples = _quality_gate_samples(100)
    train_loader, eval_loader = trainer.build_dataset(samples)

    assert len(train_loader.dataset) == 90
    assert len(eval_loader.dataset) == 10


def test_incremental_trainer_build_dataset_rejects_too_few_samples(monkeypatch, tmp_path):
    fake_state = FakeStateManager()
    monkeypatch.setattr("backend.training.incremental_trainer.get_training_state_manager", lambda: fake_state)
    monkeypatch.setattr("backend.training.incremental_trainer.extract", _feature_vector)

    trainer = IncrementalTrainer(
        model_path=tmp_path / "checkpoints" / "model.safetensors",
        state_path=tmp_path / "checkpoints" / "training_state.json",
        baseline_path=tmp_path / "checkpoints" / "baseline_accuracy.json",
        raw_data_root=tmp_path / "raw",
        num_workers=0,
    )

    with pytest.raises(DatasetQualityError, match="sample_count_below_min"):
        trainer.build_dataset(_quality_gate_samples(99))


def test_incremental_trainer_build_dataset_rejects_imbalanced_severity(monkeypatch, tmp_path):
    fake_state = FakeStateManager()
    monkeypatch.setattr("backend.training.incremental_trainer.get_training_state_manager", lambda: fake_state)
    monkeypatch.setattr("backend.training.incremental_trainer.extract", _feature_vector)

    trainer = IncrementalTrainer(
        model_path=tmp_path / "checkpoints" / "model.safetensors",
        state_path=tmp_path / "checkpoints" / "training_state.json",
        baseline_path=tmp_path / "checkpoints" / "baseline_accuracy.json",
        raw_data_root=tmp_path / "raw",
        num_workers=0,
    )

    with pytest.raises(DatasetQualityError, match="severity_distribution_below_min"):
        trainer.build_dataset(
            [_quality_gate_sample(index, severity="HIGH") for index in range(100)]
        )


def test_dataset_quality_report_fields_correct_for_known_inputs():
    severities = ["CRITICAL", "HIGH", "MEDIUM", "LOW", "INFORMATIONAL"] * 20
    samples = [
        {
            "cve_id": f"CVE-2026-{index:05d}",
            "severity": severities[index],
            "quality_score": 0.5,
            "raw_text": f"validated sample {index}",
        }
        for index in range(100)
    ]

    report = DatasetQualityGate().validate(samples)

    assert report.passed is True
    assert report.sample_count == 100
    assert report.mean_quality_score == pytest.approx(0.5)
    assert report.unique_cves == 100
    assert report.severity_distribution == {
        "CRITICAL": pytest.approx(0.2),
        "HIGH": pytest.approx(0.2),
        "MEDIUM": pytest.approx(0.2),
        "LOW": pytest.approx(0.2),
        "INFORMATIONAL": pytest.approx(0.2),
    }
    assert report.failed_reasons == []


def test_dataset_quality_gate_passes_realistic_cve_distribution():
    severities = (
        ["HIGH"] * 40
        + ["MEDIUM"] * 35
        + ["CRITICAL"] * 15
        + ["LOW"] * 8
        + ["INFORMATIONAL"] * 2
    )
    samples = [
        {
            "cve_id": f"CVE-2026-{index:05d}",
            "severity": severity,
            "quality_score": 0.6,
            "raw_text": f"realistic sample {index}",
        }
        for index, severity in enumerate(severities)
    ]

    report = DatasetQualityGate().validate(samples)

    assert report.passed is True
    assert report.failed_reasons == []


def test_accuracy_snapshot_fields_correct():
    snapshot = AccuracySnapshot(
        epoch=4,
        accuracy=0.81,
        precision=0.79,
        recall=0.77,
        f1=0.78,
        auc_roc=0.88,
        taken_at="2026-04-07T10:00:00+00:00",
    )

    assert snapshot.epoch == 4
    assert snapshot.accuracy == pytest.approx(0.81)
    assert snapshot.precision == pytest.approx(0.79)
    assert snapshot.recall == pytest.approx(0.77)
    assert snapshot.f1 == pytest.approx(0.78)
    assert snapshot.auc_roc == pytest.approx(0.88)
    assert snapshot.taken_at == "2026-04-07T10:00:00+00:00"


def test_accuracy_history_get_best_returns_correct_snapshot():
    history = AccuracyHistory()
    first = AccuracySnapshot(
        epoch=1,
        accuracy=0.78,
        precision=0.76,
        recall=0.74,
        f1=0.75,
        auc_roc=0.82,
        taken_at="2026-04-07T10:00:00+00:00",
    )
    second = AccuracySnapshot(
        epoch=2,
        accuracy=0.84,
        precision=0.83,
        recall=0.81,
        f1=0.82,
        auc_roc=0.89,
        taken_at="2026-04-07T10:05:00+00:00",
    )
    history.add(first)
    history.add(second)

    assert history.get_best() == second
    assert history.get_last() == second


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


def test_incremental_trainer_load_evaluation_samples_uses_dataset_index_cache(monkeypatch, tmp_path):
    fake_state = FakeStateManager()
    raw_root = tmp_path / "raw"
    sample = _sample_with_time(7)
    _write_sample(raw_root, sample)
    monkeypatch.setattr("backend.training.incremental_trainer.get_training_state_manager", lambda: fake_state)

    trainer = IncrementalTrainer(
        model_path=tmp_path / "checkpoints" / "model.safetensors",
        state_path=tmp_path / "checkpoints" / "training_state.json",
        baseline_path=tmp_path / "checkpoints" / "baseline_accuracy.json",
        raw_data_root=raw_root,
        num_workers=0,
    )

    samples, source = trainer.load_evaluation_samples(max_samples=10)
    assert source == "data_raw"
    assert len(samples) == 1
    assert trainer.dataset_index_path.exists()

    def _unexpected_read(*args, **kwargs):
        raise AssertionError("raw sample file should not be re-read when dataset index cache is warm")

    monkeypatch.setattr(Path, "read_text", _unexpected_read)
    cached_samples, cached_source = trainer.load_evaluation_samples(max_samples=10)
    assert cached_source == "data_raw"
    assert len(cached_samples) == 1


def test_incremental_trainer_rejects_invalid_legacy_bridge_row(monkeypatch, tmp_path):
    fake_state = FakeStateManager()
    monkeypatch.setattr("backend.training.incremental_trainer.get_training_state_manager", lambda: fake_state)

    trainer = IncrementalTrainer(
        model_path=tmp_path / "checkpoints" / "model.safetensors",
        state_path=tmp_path / "checkpoints" / "training_state.json",
        baseline_path=tmp_path / "checkpoints" / "baseline_accuracy.json",
        raw_data_root=tmp_path / "raw",
        num_workers=0,
    )

    rows = [
        {
            "endpoint": "not-a-cve",
            "parameters": "x",
            "exploit_vector": "y",
            "impact": "CVSS:9.0|HIGH",
            "source_tag": "nvd",
            "ingested_at": datetime.now(timezone.utc).isoformat(),
            "sha256_hash": "a" * 64,
        }
    ]

    monkeypatch.setattr(
        "backend.training.incremental_trainer.get_bridge_state",
        lambda: SimpleNamespace(read_samples=lambda max_samples=0: rows),
    )

    samples = trainer._load_bridge_samples(max_samples=10)
    assert samples == []


def test_incremental_trainer_normalizes_and_persists_feature_stats(monkeypatch, tmp_path):
    fake_state = FakeStateManager()
    monkeypatch.setattr("backend.training.incremental_trainer.get_training_state_manager", lambda: fake_state)
    monkeypatch.setattr(
        "backend.training.incremental_trainer.extract",
        lambda sample: torch.arange(512, dtype=torch.float32),
    )

    trainer = IncrementalTrainer(
        model_path=tmp_path / "checkpoints" / "model.safetensors",
        state_path=tmp_path / "checkpoints" / "training_state.json",
        baseline_path=tmp_path / "checkpoints" / "baseline_accuracy.json",
        raw_data_root=tmp_path / "raw",
        num_workers=0,
    )
    sample = _sample_with_time(11)

    feature = trainer._load_or_compute_feature(sample)
    cache_path = trainer._feature_cache_path(sample)
    legacy_stats_path = trainer.feature_cache_root / f"{sample.sha256_hash}.stats.json"
    cached_features, cached_labels, cached_metadata = trainer.feature_store.read(sample.sha256_hash)

    assert cache_path.exists()
    assert legacy_stats_path.exists() is False
    assert cached_features.shape == (1, 256)
    assert cached_labels.tolist() == [trainer._label_for_sample(sample)]
    assert cached_metadata["stats"]["safe_std"] > 0.0
    assert abs(float(feature.mean().item())) < 1e-3
    assert 0.5 < float(feature.std(unbiased=False).item()) < 1.5


def test_incremental_trainer_invalid_feature_counts_and_raises(monkeypatch, tmp_path):
    fake_state = FakeStateManager()
    monkeypatch.setattr("backend.training.incremental_trainer.get_training_state_manager", lambda: fake_state)
    monkeypatch.setattr(
        "backend.training.incremental_trainer.extract",
        lambda sample: torch.zeros(512, dtype=torch.float32),
    )

    trainer = IncrementalTrainer(
        model_path=tmp_path / "checkpoints" / "model.safetensors",
        state_path=tmp_path / "checkpoints" / "training_state.json",
        baseline_path=tmp_path / "checkpoints" / "baseline_accuracy.json",
        raw_data_root=tmp_path / "raw",
        num_workers=0,
    )
    sample = _sample_with_time(12)
    dataset = _StreamingFeatureDataset(trainer, [sample], [0])

    with pytest.raises(RuntimeError, match="invalid feature tensor"):
        _ = dataset[0]

    assert trainer._invalid_sample_count == 1


def test_incremental_trainer_rejects_all_same_value_tensor(caplog):
    with caplog.at_level(logging.WARNING):
        is_valid, reason = IncrementalTrainer._validate_feature_tensor(
            torch.ones(512, dtype=torch.float32)
        )

    assert is_valid is False
    assert reason == "all_same_value"
    assert "feature_tensor_all_same_value_rejected" in caplog.text


def test_incremental_trainer_benchmark_returns_metric_dict(monkeypatch, tmp_path):
    fake_state = FakeStateManager()
    monkeypatch.setattr("backend.training.incremental_trainer.get_training_state_manager", lambda: fake_state)
    monkeypatch.setattr("backend.training.incremental_trainer.extract", _feature_vector)

    trainer = IncrementalTrainer(
        model_path=tmp_path / "checkpoints" / "model.safetensors",
        state_path=tmp_path / "checkpoints" / "training_state.json",
        baseline_path=tmp_path / "checkpoints" / "baseline_accuracy.json",
        raw_data_root=tmp_path / "raw",
        num_workers=0,
    )
    trainer.load_evaluation_samples = lambda max_samples=1500: (
        [_sample_with_time(index, positive=index % 2 == 0) for index in range(20)],
        "data_raw",
    )

    result = trainer.benchmark_current_model(max_samples=20)

    for key in ("loss", "precision_at_5", "precision_at_10", "mrr", "f1"):
        assert key in result
        assert float(result[key]) >= 0.0


def test_incremental_trainer_refresh_dataset_index_uses_invalidation_source(monkeypatch, tmp_path):
    fake_state = FakeStateManager()
    monkeypatch.setattr("backend.training.incremental_trainer.get_training_state_manager", lambda: fake_state)

    raw_root = tmp_path / "raw"
    source_dir = raw_root / "nvd"
    source_dir.mkdir(parents=True, exist_ok=True)
    sample_dir = source_dir / datetime.now(timezone.utc).date().isoformat()
    sample_dir.mkdir(parents=True, exist_ok=True)
    sample = _sample_with_time(21)
    sample_path = sample_dir / f"{sample.sha256_hash}.json"
    sample_path.write_text(json.dumps(sample_to_dict(sample), indent=2), encoding="utf-8")

    trainer = IncrementalTrainer(
        model_path=tmp_path / "checkpoints" / "model.safetensors",
        state_path=tmp_path / "checkpoints" / "training_state.json",
        baseline_path=tmp_path / "checkpoints" / "baseline_accuracy.json",
        raw_data_root=raw_root,
        num_workers=0,
    )

    class _SingleDirInvalidationSource:
        def get_changed_dirs(self):
            return {sample_dir}

    indexed = trainer._refresh_dataset_index(
        invalidation_source=_SingleDirInvalidationSource()
    )
    assert len(indexed) == 1


def test_incremental_trainer_run_epoch_emits_metrics(monkeypatch, tmp_path):
    fake_state = FakeStateManager()
    model_path = tmp_path / "checkpoints" / "model.safetensors"
    state_path = tmp_path / "checkpoints" / "training_state.json"
    baseline_path = tmp_path / "checkpoints" / "baseline_accuracy.json"
    monkeypatch.setattr("backend.training.incremental_trainer.get_training_state_manager", lambda: fake_state)
    monkeypatch.setattr("backend.training.incremental_trainer.extract", _feature_vector)

    trainer = IncrementalTrainer(model_path=model_path, state_path=state_path, baseline_path=baseline_path, raw_data_root=tmp_path / "raw", num_workers=0)
    trainer.load_new_samples = lambda: _quality_gate_samples(100)

    result = trainer.run_incremental_epoch()

    assert isinstance(result, EpochResult)
    assert result.samples_processed == 100
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
    trainer.load_new_samples = lambda: _quality_gate_samples(100)

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
    monkeypatch.setattr("backend.training.incremental_trainer.torch.cuda.amp.GradScaler", lambda *args, **kwargs: FakeScaler())
    monkeypatch.setattr("backend.training.incremental_trainer.torch.cuda.amp.autocast", lambda *args, **kwargs: nullcontext())
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


def test_incremental_trainer_train_uses_sample_weights_in_loss(monkeypatch, tmp_path):
    class FixedLogitModel(torch.nn.Module):
        def __init__(self) -> None:
            super().__init__()
            self.bias = torch.nn.Parameter(torch.zeros(2, dtype=torch.float32))

        def forward(self, features: torch.Tensor) -> torch.Tensor:
            return features + self.bias

    fake_state = FakeStateManager()
    monkeypatch.setattr(
        "backend.training.incremental_trainer.get_training_state_manager",
        lambda: fake_state,
    )
    trainer = IncrementalTrainer(
        model_path=tmp_path / "checkpoints" / "model.safetensors",
        state_path=tmp_path / "checkpoints" / "training_state.json",
        baseline_path=tmp_path / "checkpoints" / "baseline_accuracy.json",
        raw_data_root=tmp_path / "raw",
        num_workers=0,
    )
    trainer.model = FixedLogitModel()
    trainer.device = torch.device("cpu")

    features = torch.tensor([[2.0, 0.0], [0.0, 2.0]], dtype=torch.float32)
    labels = torch.tensor([0, 0], dtype=torch.long)
    dataset_indices = torch.tensor([0, 1], dtype=torch.long)
    train_loader = torch.utils.data.DataLoader(
        torch.utils.data.TensorDataset(features, labels, dataset_indices),
        batch_size=2,
        shuffle=False,
    )
    criterion = torch.nn.CrossEntropyLoss(reduction="none")
    base_losses = criterion(features, labels)

    weighted_loss = trainer.train(
        train_loader,
        torch.optim.SGD(trainer.model.parameters(), lr=0.0),
        torch.optim.lr_scheduler.LambdaLR(
            torch.optim.SGD(trainer.model.parameters(), lr=0.0),
            lr_lambda=lambda _: 1.0,
        ),
        criterion,
        None,
        sample_weights=[1.0, 3.0],
    )
    unweighted_loss = trainer.train(
        train_loader,
        torch.optim.SGD(trainer.model.parameters(), lr=0.0),
        torch.optim.lr_scheduler.LambdaLR(
            torch.optim.SGD(trainer.model.parameters(), lr=0.0),
            lr_lambda=lambda _: 1.0,
        ),
        criterion,
        None,
        sample_weights=None,
    )

    expected_weighted_loss = float(
        ((base_losses * torch.tensor([1.0, 3.0])).sum() / 4.0).item()
    )
    expected_unweighted_loss = float(base_losses.mean().item())

    assert weighted_loss == pytest.approx(expected_weighted_loss)
    assert unweighted_loss == pytest.approx(expected_unweighted_loss)
    assert weighted_loss > unweighted_loss


def test_incremental_trainer_train_adds_ewc_loss(monkeypatch, tmp_path, caplog):
    class FixedLogitModel(torch.nn.Module):
        def __init__(self) -> None:
            super().__init__()
            self.bias = torch.nn.Parameter(torch.zeros(2, dtype=torch.float32))

        def forward(self, features: torch.Tensor) -> torch.Tensor:
            return features + self.bias

    class _StubAdaptiveLearner:
        def __init__(self) -> None:
            self.attached_model = None

        def attach_model(self, model: torch.nn.Module) -> None:
            self.attached_model = model

        def get_ewc_loss(self) -> torch.Tensor:
            return torch.tensor(0.25, dtype=torch.float32)

    fake_state = FakeStateManager()
    monkeypatch.setattr(
        "backend.training.incremental_trainer.get_training_state_manager",
        lambda: fake_state,
    )
    trainer = IncrementalTrainer(
        model_path=tmp_path / "checkpoints" / "model.safetensors",
        state_path=tmp_path / "checkpoints" / "training_state.json",
        baseline_path=tmp_path / "checkpoints" / "baseline_accuracy.json",
        raw_data_root=tmp_path / "raw",
        num_workers=0,
    )
    trainer.model = FixedLogitModel()
    trainer.device = torch.device("cpu")
    trainer.adaptive_learner = _StubAdaptiveLearner()

    features = torch.tensor([[2.0, 0.0], [0.0, 2.0]], dtype=torch.float32)
    labels = torch.tensor([0, 0], dtype=torch.long)
    train_loader = torch.utils.data.DataLoader(
        torch.utils.data.TensorDataset(features, labels),
        batch_size=2,
        shuffle=False,
    )
    criterion = torch.nn.CrossEntropyLoss(reduction="none")
    optimizer = torch.optim.SGD(trainer.model.parameters(), lr=0.0)
    scheduler = torch.optim.lr_scheduler.LambdaLR(
        optimizer,
        lr_lambda=lambda _: 1.0,
    )
    base_losses = criterion(features, labels)

    with caplog.at_level(logging.DEBUG, logger="ygb.training.incremental_trainer"):
        total_loss = trainer.train(
            train_loader,
            optimizer,
            scheduler,
            criterion,
            None,
            sample_weights=None,
        )

    assert total_loss == pytest.approx(float(base_losses.mean().item() + 0.25))
    assert trainer.adaptive_learner.attached_model is trainer.model
    assert any("mean_ewc_loss" in record.getMessage() for record in caplog.records)


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
    trainer.load_new_samples = lambda: _quality_gate_samples(100)

    result = trainer.run_incremental_epoch()

    assert result.rollback is True
    assert metrics_registry.get_counter("training_rollback") == 1.0


def test_incremental_trainer_rolls_back_when_f1_drops_more_than_threshold(monkeypatch, tmp_path):
    fake_state = FakeStateManager()
    model_path = tmp_path / "checkpoints" / "model.safetensors"
    state_path = tmp_path / "checkpoints" / "training_state.json"
    baseline_path = tmp_path / "checkpoints" / "baseline_accuracy.json"
    monkeypatch.setattr(
        "backend.training.incremental_trainer.get_training_state_manager",
        lambda: fake_state,
    )
    monkeypatch.setattr("backend.training.incremental_trainer.extract", _feature_vector)

    metric_templates = [
        {
            "threshold": 0.5,
            "accuracy": 0.80,
            "precision": 0.80,
            "recall": 0.80,
            "f1": 0.80,
            "strategy": "epoch_one",
        },
        {
            "threshold": 0.5,
            "accuracy": 0.79,
            "precision": 0.78,
            "recall": 0.64,
            "f1": 0.70,
            "strategy": "epoch_two",
        },
    ]

    def _fake_calibrate(labels, probabilities, fallback_threshold=0.5):
        template = metric_templates.pop(0)
        return {
            "threshold": float(template["threshold"]),
            "predictions": [1 if index % 2 == 0 else 0 for index in range(len(labels))],
            "accuracy": float(template["accuracy"]),
            "precision": float(template["precision"]),
            "recall": float(template["recall"]),
            "f1": float(template["f1"]),
            "strategy": str(template["strategy"]),
        }

    monkeypatch.setattr(
        "backend.training.incremental_trainer.calibrate_positive_threshold",
        _fake_calibrate,
    )

    trainer = IncrementalTrainer(
        model_path=model_path,
        state_path=state_path,
        baseline_path=baseline_path,
        raw_data_root=tmp_path / "raw",
        num_workers=0,
    )
    trainer.optimizer_config = replace(trainer.optimizer_config, max_epochs=1)
    trainer.load_new_samples = lambda: _quality_gate_samples(100)
    rollback_calls: list[str] = []
    trainer._load_best_checkpoint = lambda: rollback_calls.append("rollback")

    first_result = trainer.run_incremental_epoch()
    second_result = trainer.run_incremental_epoch()

    assert first_result.rollback is False
    assert second_result.rollback is True
    assert rollback_calls == ["rollback"]
    assert metrics_registry.get_counter("training_rollback") == 1.0
    assert trainer.get_accuracy_history()[-1].f1 == pytest.approx(0.70)


def test_incremental_trainer_blocks_promotion_when_f1_below_threshold(monkeypatch, tmp_path):
    fake_state = FakeStateManager()
    model_path = tmp_path / "checkpoints" / "model.safetensors"
    state_path = tmp_path / "checkpoints" / "training_state.json"
    baseline_path = tmp_path / "checkpoints" / "baseline_accuracy.json"
    monkeypatch.setattr(
        "backend.training.incremental_trainer.get_training_state_manager",
        lambda: fake_state,
    )
    monkeypatch.setattr("backend.training.incremental_trainer.extract", _feature_vector)
    monkeypatch.setattr(
        "backend.training.incremental_trainer.calibrate_positive_threshold",
        lambda labels, probabilities, fallback_threshold=0.5: {
            "threshold": float(fallback_threshold),
            "predictions": [1 if index % 2 == 0 else 0 for index in range(len(labels))],
            "accuracy": 0.80,
            "precision": 0.76,
            "recall": 0.72,
            "f1": 0.74,
            "strategy": "blocked_low_accuracy",
        },
    )

    trainer = IncrementalTrainer(
        model_path=model_path,
        state_path=state_path,
        baseline_path=baseline_path,
        raw_data_root=tmp_path / "raw",
        num_workers=0,
    )
    trainer.load_new_samples = lambda: _quality_gate_samples(100)

    result = trainer.run_incremental_epoch()
    payload = json.loads(baseline_path.read_text(encoding="utf-8"))

    assert result.status == "BLOCKED_LOW_ACCURACY"
    assert result.rollback is False
    assert payload["checkpoint_f1"] == pytest.approx(0.0)
    assert payload["baseline_accuracy"] == pytest.approx(0.0)


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
    trainer.load_new_samples = lambda: _quality_gate_samples(100)

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


def test_warmup_cosine_scheduler_warmup_then_decay():
    parameter = torch.nn.Parameter(torch.tensor([1.0], dtype=torch.float32))
    optimizer = torch.optim.SGD([parameter], lr=0.1)
    scheduler = WarmupCosineScheduler(
        optimizer,
        total_steps=6,
        warmup_steps=2,
        min_lr=0.001,
        warmup_start_factor=0.1,
    )

    learning_rates = [optimizer.param_groups[0]["lr"]]
    for _ in range(6):
        optimizer.step()
        scheduler.step()
        learning_rates.append(optimizer.param_groups[0]["lr"])

    assert learning_rates[0] < learning_rates[1] < learning_rates[2]
    assert learning_rates[2] > learning_rates[3] > learning_rates[4]
    assert learning_rates[-1] >= 0.001


def test_early_stopping_triggers_after_patience_exhaustion():
    early_stopper = EarlyStopping(patience=2, min_delta=0.0)

    assert early_stopper.step(1.0) is False
    assert early_stopper.step(1.0) is False
    assert early_stopper.step(1.0) is True


def test_hard_negative_miner_returns_expected_hard_indices():
    miner = HardNegativeMiner(max_hard_examples=2)

    hard_indices = miner.mine(
        losses=[0.10, 1.10, 0.25, 0.90],
        labels=[0, 0, 1, 0],
        positive_probabilities=[0.05, 0.95, 0.80, 0.70],
        dataset_indices=[10, 11, 12, 13],
    )

    assert hard_indices == [11, 13]


def test_incremental_trainer_train_logs_val_loss_and_uses_validation_split(
    monkeypatch,
    tmp_path,
    caplog,
):
    fake_state = FakeStateManager()
    monkeypatch.setattr(
        "backend.training.incremental_trainer.get_training_state_manager",
        lambda: fake_state,
    )
    monkeypatch.setattr("backend.training.incremental_trainer.extract", _feature_vector)

    trainer = IncrementalTrainer(
        model_path=tmp_path / "checkpoints" / "model.safetensors",
        state_path=tmp_path / "checkpoints" / "training_state.json",
        baseline_path=tmp_path / "checkpoints" / "baseline_accuracy.json",
        raw_data_root=tmp_path / "raw",
        num_workers=0,
    )
    samples = _quality_gate_samples(100)
    train_loader, val_loader = trainer.build_dataset(
        samples,
        include_train_dataset_indices=True,
    )
    config = replace(
        trainer.optimizer_config,
        max_epochs=1,
        use_amp=False,
    )
    optimizer = torch.optim.AdamW(
        trainer.model.parameters(),
        lr=config.learning_rate,
        weight_decay=0.01,
    )
    scheduler = WarmupCosineScheduler(
        optimizer,
        total_steps=1,
        warmup_steps=1,
        min_lr=config.min_learning_rate,
        warmup_start_factor=config.warmup_start_factor,
    )

    with caplog.at_level(logging.INFO, logger="ygb.training.incremental_trainer"):
        summary = trainer.train(
            train_loader,
            optimizer,
            scheduler,
            torch.nn.CrossEntropyLoss(reduction="none"),
            None,
            sample_weights=None,
            val_loader=val_loader,
            eval_criterion=torch.nn.CrossEntropyLoss(),
            optimiser_config=config,
            return_history=True,
        )

    assert len(train_loader.dataset) == 90
    assert len(val_loader.dataset) == 10
    assert summary.eval_loss >= 0.0
    assert "val_loss=" in caplog.text


def test_incremental_trainer_validation_split_is_deterministic(monkeypatch, tmp_path):
    fake_state = FakeStateManager()
    monkeypatch.setattr(
        "backend.training.incremental_trainer.get_training_state_manager",
        lambda: fake_state,
    )
    monkeypatch.setattr("backend.training.incremental_trainer.extract", _feature_vector)

    trainer = IncrementalTrainer(
        model_path=tmp_path / "checkpoints" / "model.safetensors",
        state_path=tmp_path / "checkpoints" / "training_state.json",
        baseline_path=tmp_path / "checkpoints" / "baseline_accuracy.json",
        raw_data_root=tmp_path / "raw",
        num_workers=0,
    )
    samples = _quality_gate_samples(100)

    train_loader_a, val_loader_a = trainer.build_dataset(
        samples,
        include_train_dataset_indices=True,
    )
    train_loader_b, val_loader_b = trainer.build_dataset(
        samples,
        include_train_dataset_indices=True,
    )

    assert list(train_loader_a.dataset.sample_indices) == list(train_loader_b.dataset.sample_indices)
    assert list(val_loader_a.dataset.sample_indices) == list(val_loader_b.dataset.sample_indices)


def test_incremental_trainer_epoch_log_contains_all_required_fields(monkeypatch, tmp_path, caplog):
    fake_state = FakeStateManager()
    monkeypatch.setattr(
        "backend.training.incremental_trainer.get_training_state_manager",
        lambda: fake_state,
    )
    monkeypatch.setattr("backend.training.incremental_trainer.extract", _feature_vector)

    trainer = IncrementalTrainer(
        model_path=tmp_path / "checkpoints" / "model.safetensors",
        state_path=tmp_path / "checkpoints" / "training_state.json",
        baseline_path=tmp_path / "checkpoints" / "baseline_accuracy.json",
        raw_data_root=tmp_path / "raw",
        num_workers=0,
    )
    samples = _quality_gate_samples(100)
    train_loader, val_loader = trainer.build_dataset(
        samples,
        include_train_dataset_indices=True,
    )
    config = replace(
        trainer.optimizer_config,
        max_epochs=1,
        use_amp=False,
    )
    optimizer = torch.optim.AdamW(
        trainer.model.parameters(),
        lr=config.learning_rate,
        weight_decay=0.01,
    )
    scheduler = WarmupCosineScheduler(
        optimizer,
        total_steps=1,
        warmup_steps=1,
        min_lr=config.min_learning_rate,
        warmup_start_factor=config.warmup_start_factor,
    )

    with caplog.at_level(logging.INFO, logger="ygb.training.incremental_trainer"):
        trainer.train(
            train_loader,
            optimizer,
            scheduler,
            torch.nn.CrossEntropyLoss(reduction="none"),
            None,
            sample_weights=None,
            val_loader=val_loader,
            eval_criterion=torch.nn.CrossEntropyLoss(),
            optimiser_config=config,
            return_history=True,
        )

    epoch_logs = [
        record.getMessage()
        for record in caplog.records
        if "epoch 1/1 | lr=" in record.getMessage()
    ]
    assert epoch_logs
    log_line = epoch_logs[-1]
    for token in ("train_loss=", "val_loss=", "f1=", "precision=", "recall=", "ewc_loss="):
        assert token in log_line


def test_incremental_trainer_saves_deterministic_checkpoint_name(monkeypatch, tmp_path):
    fake_state = FakeStateManager()
    monkeypatch.setattr(
        "backend.training.incremental_trainer.get_training_state_manager",
        lambda: fake_state,
    )
    monkeypatch.setattr("backend.training.incremental_trainer.extract", _feature_vector)

    trainer = IncrementalTrainer(
        model_path=tmp_path / "checkpoints" / "model.safetensors",
        state_path=tmp_path / "checkpoints" / "training_state.json",
        baseline_path=tmp_path / "checkpoints" / "baseline_accuracy.json",
        raw_data_root=tmp_path / "raw",
        num_workers=0,
    )
    trainer.load_new_samples = lambda: _quality_gate_samples(100)

    result = trainer.run_incremental_epoch()

    expected = trainer.model_path.parent / f"checkpoint_{trainer.model_path.stem}_{result.epoch_number}_{result.f1:.3f}.pt"
    assert expected.exists()


def test_incremental_trainer_train_early_stops_before_max_epochs_when_val_loss_is_flat(
    monkeypatch,
    tmp_path,
):
    fake_state = FakeStateManager()
    monkeypatch.setattr(
        "backend.training.incremental_trainer.get_training_state_manager",
        lambda: fake_state,
    )
    monkeypatch.setattr("backend.training.incremental_trainer.extract", _feature_vector)

    trainer = IncrementalTrainer(
        model_path=tmp_path / "checkpoints" / "model.safetensors",
        state_path=tmp_path / "checkpoints" / "training_state.json",
        baseline_path=tmp_path / "checkpoints" / "baseline_accuracy.json",
        raw_data_root=tmp_path / "raw",
        num_workers=0,
    )
    samples = _quality_gate_samples(100)
    train_loader, val_loader = trainer.build_dataset(
        samples,
        include_train_dataset_indices=True,
    )
    config = replace(
        trainer.optimizer_config,
        learning_rate=0.0,
        min_learning_rate=0.0,
        max_epochs=5,
        patience=1,
        use_amp=False,
    )
    optimizer = torch.optim.AdamW(
        trainer.model.parameters(),
        lr=config.learning_rate,
        weight_decay=0.01,
    )
    scheduler = WarmupCosineScheduler(
        optimizer,
        total_steps=config.max_epochs,
        warmup_steps=1,
        min_lr=config.min_learning_rate,
        warmup_start_factor=1.0,
    )

    summary = trainer.train(
        train_loader,
        optimizer,
        scheduler,
        torch.nn.CrossEntropyLoss(reduction="none"),
        None,
        sample_weights=None,
        val_loader=val_loader,
        eval_criterion=torch.nn.CrossEntropyLoss(),
        optimiser_config=config,
        return_history=True,
    )

    assert summary.early_stopped is True
    assert summary.epochs_completed < config.max_epochs


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
