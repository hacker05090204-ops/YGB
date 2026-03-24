from __future__ import annotations

import os
from dataclasses import dataclass
from typing import List, Optional


@dataclass
class TrainingControllerConfig:
    leader_node: str = "RTX2050"
    follower_node: str = "RTX3050"
    rank: int = 0
    world_size: int = 2
    backend: str = "nccl"
    master_addr: str = "127.0.0.1"
    master_port: int = 29500
    input_dim: int = 256
    hidden_dim: int = 512
    num_classes: int = 2
    num_epochs: int = 5
    base_batch_size: int = 512
    base_lr: float = 0.001
    gradient_clip: float = 1.0
    seed: int = 42
    use_amp: bool = True
    use_bf16: bool = True
    cosine_lr: bool = True
    checkpoint_every_epoch: bool = True
    keep_epoch_checkpoints: int = 5
    resume_if_available: bool = True
    async_checkpoints: bool = True
    checkpoint_version: int = 2
    deepspeed_enabled: bool = False
    zero_stage: int = 2
    gradient_checkpointing: bool = True
    async_pipeline: bool = True
    adaptive_batch_size: bool = True
    monitor_training: bool = True
    gradient_accumulation_steps: int = 2
    min_local_batch: int = 32
    max_local_batch: int = 2048
    prefetch_batches: int = 4
    ram_cache_batches: int = 4
    dataset_cache_dir: str = os.path.join("secure_data", "dataset_cache")
    dataset_cache_to_disk: bool = True
    auto_batch_tuning: bool = True
    auto_lr_tuning: bool = True
    min_lr: float = 1e-5
    max_lr: float = 0.005
    target_gpu_utilization: float = 90.0
    target_memory_utilization: float = 82.0
    checkpoint_workers: int = 4
    tiered_checkpoint_storage: bool = True
    checkpoint_storage_dir: str = os.path.join(
        "secure_data", "tiered_checkpoint_storage"
    )
    use_flash_attention: bool = True
    attention_heads: int = 4
    token_dim: int = 32
    ddp_bucket_cap_mb: int = 64
    comm_bucket_size: int = 50_000_000
    prefetch_bucket_size: int = 5_000_000
    num_samples: int = 8000
    checkpoint_dir: str = os.path.join("secure_data", "checkpoints")
    model_dir: str = os.path.join("secure_data", "model_versions")
    experiment_dir: str = os.path.join("secure_data", "experiments")


@dataclass
class DatasetState:
    hash: str
    sample_count: int
    feature_dim: int
    num_classes: int
    entropy: float
    trainable: bool
    manifest_path: str
    enforcement_passed: bool
    dataset_source: str = ""
    verification_passed: bool = False
    verification_code: str = ""
    verification_message: str = ""


@dataclass
class TrainingResult:
    epochs_completed: int
    final_loss: float
    final_accuracy: float
    best_accuracy: float
    cluster_sps: float
    merged_weight_hash: str
    drift_aborted: bool
    per_epoch: List[dict]
    resumed_from_checkpoint: bool = False
    start_epoch: int = 0
    latest_checkpoint_meta_path: str = ""
    best_checkpoint_meta_path: str = ""


@dataclass
class CheckpointBundle:
    name: str
    dir_path: str
    model_path: str
    state_path: str
    meta_path: str
    model_shards: Optional[List[str]] = None
    optimizer_state_path: str = ""
    scheduler_state_path: str = ""
