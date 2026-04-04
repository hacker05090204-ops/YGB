import json
from pathlib import Path

import numpy as np

from impl_v1.training.distributed.deepspeed_runtime import DeepSpeedRuntime, DeepSpeedRuntimeConfig
from impl_v1.training.distributed.streaming_dataset import ShardedStreamingDataset, StreamingDatasetConfig
from impl_v1.training.distributed.training_monitor import TrainingMonitor
from training_controller import TrainingControllerConfig, phase3_training_execution


def test_deepspeed_runtime_build_config_enables_fp16_fallback():
    runtime = DeepSpeedRuntime(
        DeepSpeedRuntimeConfig(
            enabled=True,
            zero_stage=3,
            bf16=False,
            fp16=True,
            gradient_accumulation_steps=4,
            train_micro_batch_size_per_gpu=8,
            reduce_bucket_size=1234,
            allgather_bucket_size=4321,
            stage3_prefetch_bucket_size=321,
        )
    )

    config = runtime.build_config(train_batch_size=256)

    assert config["train_micro_batch_size_per_gpu"] == 8
    assert config["gradient_accumulation_steps"] == 4
    assert config["bf16"]["enabled"] is False
    assert config["fp16"]["enabled"] is True
    assert config["zero_optimization"]["stage"] == 3
    assert config["zero_optimization"]["reduce_bucket_size"] == 1234
    assert config["zero_optimization"]["allgather_bucket_size"] == 4321
    assert config["activation_checkpointing"]["partition_activations"] is True


def test_streaming_dataset_prefetch_and_cache(tmp_path):
    X = np.arange(120, dtype=np.float32).reshape(30, 4)
    y = np.arange(30, dtype=np.int64)
    config = StreamingDatasetConfig(
        batch_size=5,
        shuffle=False,
        prefetch_batches=2,
        cache_in_ram=True,
        max_ram_cache_shards=4,
        cache_dir=str(tmp_path),
        cache_to_disk=True,
    )

    first_pass = list(ShardedStreamingDataset(X, y, config))
    second_pass = list(ShardedStreamingDataset(X, y, config))

    assert len(first_pass) == len(second_pass)
    for (first_x, first_y), (second_x, second_y) in zip(first_pass, second_pass):
        assert np.array_equal(first_x, second_x)
        assert np.array_equal(first_y, second_y)

    stats = ShardedStreamingDataset.cache_stats()
    assert stats["cache_misses"] >= 1
    assert stats["ram_hits"] + stats["disk_hits"] >= 1
    assert list(Path(tmp_path).glob("*.npz"))


def test_training_monitor_records_runtime_snapshot(tmp_path):
    dashboard_path = tmp_path / "dashboard.json"
    monitor = TrainingMonitor(str(dashboard_path), flush_interval_seconds=3600.0)

    monitor.record_throughput(step=1, epoch=1, samples_per_second=1024.5, batch_size=32)
    monitor.record_runtime(
        step=1,
        epoch=1,
        batch_size=32,
        learning_rate=0.001,
        gradient_accumulation=2,
        samples_per_second=1024.5,
        step_time_ms=4.2,
        data_time_ms=1.3,
    )
    monitor.record_gpu()
    snapshot = monitor.latest_snapshot()
    monitor.flush()

    payload = json.loads(dashboard_path.read_text(encoding="utf-8"))
    assert snapshot["batch_size"] == 32.0
    assert snapshot["learning_rate"] == 0.001
    assert payload["latest_metrics"]["gradient_accumulation"] == 2.0
    assert len(payload["runtime"]) == 1


def test_phase3_training_execution_cpu_smoke(tmp_path):
    rng = np.random.default_rng(7)
    X = rng.normal(size=(96, 32)).astype(np.float32)
    y = rng.integers(0, 2, size=96, dtype=np.int64)

    config = TrainingControllerConfig(
        input_dim=32,
        hidden_dim=64,
        num_classes=2,
        num_epochs=1,
        base_batch_size=32,
        base_lr=0.001,
        world_size=1,
        rank=0,
        use_amp=False,
        use_bf16=False,
        deepspeed_enabled=False,
        monitor_training=False,
        checkpoint_every_epoch=True,
        async_checkpoints=False,
        resume_if_available=False,
        checkpoint_dir=str(tmp_path / "checkpoints"),
        experiment_dir=str(tmp_path / "experiments"),
        model_dir=str(tmp_path / "models"),
        dataset_cache_dir=str(tmp_path / "dataset_cache"),
        tiered_checkpoint_storage=False,
        min_local_batch=8,
        max_local_batch=64,
        prefetch_batches=1,
        use_flash_attention=False,
    )

    result = phase3_training_execution(config, X, y, "dataset-hash")

    assert result.epochs_completed == 1
    assert result.latest_checkpoint_meta_path
    assert Path(result.latest_checkpoint_meta_path).exists()
    assert result.per_epoch[0]["precision_mode"] == "fp32"
    assert result.per_epoch[0]["gradient_accumulation_steps"] >= 1
