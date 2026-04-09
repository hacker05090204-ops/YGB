from __future__ import annotations

import hashlib
import math
import os
import random
import time
from contextlib import nullcontext
from typing import Any, Callable, Dict, List, Optional, Tuple

import numpy as np

from impl_v1.training.core.checkpoint_manager import (
    load_latest_training_checkpoint,
    save_training_checkpoint,
)
from impl_v1.training.core.controller_common import (
    autotune_local_batch,
    build_optimizer,
    clamp_int,
    cuda_memory_utilization,
    ensure_dir,
    get_rng_state,
    prune_epoch_checkpoints,
    safe_grad_norm,
    set_rng_state,
)
from impl_v1.training.core.controller_types import TrainingResult
from impl_v1.training.distributed.hash_utils import hash_model_weights


DATA_SPLIT_SEED = 42
TRAIN_SPLIT_RATIO = 0.70
VAL_SPLIT_RATIO = 0.15
TEST_SPLIT_RATIO = 0.15
MODEL_DROPOUT = 0.3
OPTIMIZER_LR = 2e-4
OPTIMIZER_WEIGHT_DECAY = 1e-4
LABEL_SMOOTHING = 0.1
EARLY_STOPPING_PATIENCE = 5
OVERFIT_WARNING_GAP = 0.15
OVERFIT_CRITICAL_GAP = 0.25


def _class_distribution(labels: np.ndarray) -> Dict[int, int]:
    values, counts = np.unique(labels, return_counts=True)
    return {int(value): int(count) for value, count in zip(values, counts)}


def _split_counts(total: int) -> Tuple[int, int, int]:
    raw_counts = (
        total * TRAIN_SPLIT_RATIO,
        total * VAL_SPLIT_RATIO,
        total * TEST_SPLIT_RATIO,
    )
    counts = [int(math.floor(value)) for value in raw_counts]
    remainder = total - sum(counts)
    order = sorted(
        range(len(raw_counts)),
        key=lambda idx: (raw_counts[idx] - counts[idx], -idx),
        reverse=True,
    )
    for idx in order[:remainder]:
        counts[idx] += 1
    return counts[0], counts[1], counts[2]


def _split_train_validation_test(
    X: np.ndarray,
    y: np.ndarray,
    *,
    seed: int = DATA_SPLIT_SEED,
) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    rng = np.random.default_rng(seed)
    train_indices: List[int] = []
    val_indices: List[int] = []
    test_indices: List[int] = []

    for label in np.unique(y):
        label_indices = np.flatnonzero(y == label)
        rng.shuffle(label_indices)
        train_count, val_count, test_count = _split_counts(int(label_indices.size))
        train_end = train_count
        val_end = train_end + val_count
        train_indices.extend(label_indices[:train_end].tolist())
        val_indices.extend(label_indices[train_end:val_end].tolist())
        test_indices.extend(label_indices[val_end : val_end + test_count].tolist())

    for bucket in (train_indices, val_indices, test_indices):
        rng.shuffle(bucket)

    if not train_indices or not val_indices or not test_indices:
        raise RuntimeError("Dataset split produced an empty train/val/test partition")

    train_idx = np.asarray(train_indices, dtype=np.int64)
    val_idx = np.asarray(val_indices, dtype=np.int64)
    test_idx = np.asarray(test_indices, dtype=np.int64)
    return (
        X[train_idx],
        y[train_idx],
        X[val_idx],
        y[val_idx],
        X[test_idx],
        y[test_idx],
    )


def _macro_classification_metrics(
    y_true: np.ndarray,
    y_pred: np.ndarray,
    num_classes: int,
) -> Dict[str, float]:
    if y_true.size == 0:
        return {
            "accuracy": 0.0,
            "precision": 0.0,
            "recall": 0.0,
            "f1": 0.0,
        }

    labels = list(range(max(int(num_classes), 1)))
    precision_total = 0.0
    recall_total = 0.0
    f1_total = 0.0

    for label in labels:
        true_mask = y_true == label
        pred_mask = y_pred == label
        tp = int(np.logical_and(true_mask, pred_mask).sum())
        fp = int(np.logical_and(~true_mask, pred_mask).sum())
        fn = int(np.logical_and(true_mask, ~pred_mask).sum())

        precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1 = (
            (2.0 * precision * recall) / (precision + recall)
            if (precision + recall) > 0.0
            else 0.0
        )
        precision_total += precision
        recall_total += recall
        f1_total += f1

    divisor = float(len(labels)) if labels else 1.0
    return {
        "accuracy": float(np.mean(y_true == y_pred)),
        "precision": precision_total / divisor,
        "recall": recall_total / divisor,
        "f1": f1_total / divisor,
    }


def _evaluate_split(
    model,
    features: np.ndarray,
    labels: np.ndarray,
    criterion,
    device,
    batch_size: int,
    num_classes: int,
    torch_module,
) -> Dict[str, float]:
    if labels.size == 0:
        raise RuntimeError("Validation split is empty")

    model.eval()
    total_loss = 0.0
    total = 0
    all_true: List[np.ndarray] = []
    all_pred: List[np.ndarray] = []

    with torch_module.no_grad():
        for start in range(0, int(labels.size), max(1, int(batch_size))):
            stop = min(start + max(1, int(batch_size)), int(labels.size))
            batch_x = torch_module.from_numpy(features[start:stop]).to(
                device, non_blocking=True
            )
            batch_y = torch_module.from_numpy(labels[start:stop]).to(
                device, non_blocking=True
            )
            logits = model(batch_x)
            loss = criterion(logits, batch_y)
            predictions = logits.argmax(dim=1)

            batch_total = int(batch_y.size(0))
            total += batch_total
            total_loss += float(loss.item()) * batch_total
            all_true.append(batch_y.detach().cpu().numpy())
            all_pred.append(predictions.detach().cpu().numpy())

    y_true = np.concatenate(all_true) if all_true else np.empty((0,), dtype=np.int64)
    y_pred = np.concatenate(all_pred) if all_pred else np.empty((0,), dtype=np.int64)
    metrics = _macro_classification_metrics(y_true, y_pred, num_classes)
    metrics["loss"] = total_loss / max(total, 1)
    return metrics


def _create_training_stack(
    config,
    *,
    total_samples: int,
    device,
    optim_module,
    nn_module,
    model_factory: Optional[Callable[..., Tuple[Any, int]]] = None,
):
    from impl_v1.training.distributed.optimized_layers import OptimizedTrainingModel

    effective_hidden_dim = int(config.hidden_dim)
    if total_samples < 10_000:
        effective_hidden_dim = max(1, int(config.hidden_dim) // 2)

    if model_factory is None:
        model = OptimizedTrainingModel(
            input_dim=config.input_dim,
            hidden_dim=effective_hidden_dim,
            num_classes=config.num_classes,
            attention_heads=config.attention_heads,
            token_dim=config.token_dim,
            use_flash_attention=config.use_flash_attention,
            gradient_checkpointing=config.gradient_checkpointing,
            dropout=MODEL_DROPOUT,
        ).to(device)
    else:
        model, effective_hidden_dim = model_factory(
            config=config,
            total_samples=total_samples,
            effective_hidden_dim=effective_hidden_dim,
            device=device,
            nn_module=nn_module,
        )
    optimizer = build_optimizer(optim_module, model.parameters(), OPTIMIZER_LR, device)
    criterion = nn_module.CrossEntropyLoss(label_smoothing=LABEL_SMOOTHING)
    return model, optimizer, criterion, effective_hidden_dim


def _compute_training_objective_loss(model_module, logits, targets, criterion, torch_module):
    primary_loss = criterion(logits, targets)
    aux_loss = getattr(model_module, "aux_loss", None)
    aux_loss_coeff = float(
        getattr(getattr(model_module, "config", None), "aux_loss_coeff", 0.0) or 0.0
    )

    if aux_loss is None or not isinstance(aux_loss, torch_module.Tensor):
        return primary_loss, primary_loss, 0.0

    aux_loss_tensor = aux_loss.to(primary_loss.device)
    if aux_loss_tensor.ndim != 0:
        return primary_loss, primary_loss, 0.0
    if not bool(torch_module.isfinite(aux_loss_tensor).all().item()):
        return primary_loss, primary_loss, 0.0
    if aux_loss_coeff <= 0.0:
        return primary_loss, primary_loss, 0.0

    return (
        primary_loss + (aux_loss_coeff * aux_loss_tensor),
        primary_loss,
        float(aux_loss_tensor.detach().item()),
    )


def _update_val_loss_plateau(
    best_val_loss: float,
    plateau_count: int,
    current_val_loss: float,
    *,
    patience: int = EARLY_STOPPING_PATIENCE,
    min_delta: float = 1e-8,
) -> Tuple[float, int, bool]:
    if current_val_loss < (best_val_loss - min_delta):
        return current_val_loss, 0, False
    next_count = plateau_count + 1
    return best_val_loss, next_count, next_count >= patience


def _should_save_best_checkpoint(
    best_val_f1: float,
    *,
    train_f1: float,
    val_f1: float,
    min_delta: float = 1e-8,
) -> bool:
    del train_f1
    return val_f1 > (best_val_f1 + min_delta)


def _log_overfit_status(
    logger,
    *,
    epoch: int,
    total_epochs: int,
    train_loss: float,
    val_loss: float,
    train_f1: float,
    val_f1: float,
) -> float:
    overfit_gap = float(train_f1 - val_f1)
    logger.info(
        "  Epoch %s/%s | train_loss=%.6f | val_loss=%.6f | train_f1=%.4f | "
        "val_f1=%.4f | overfit_gap=(train_f1-val_f1)=%.4f",
        epoch,
        total_epochs,
        train_loss,
        val_loss,
        train_f1,
        val_f1,
        overfit_gap,
    )
    if overfit_gap > OVERFIT_CRITICAL_GAP:
        logger.critical(
            "severe overfitting — check data (epoch=%s, overfit_gap=%.4f)",
            epoch,
            overfit_gap,
        )
    elif overfit_gap > OVERFIT_WARNING_GAP:
        logger.warning(
            "overfitting detected (epoch=%s, overfit_gap=%.4f)",
            epoch,
            overfit_gap,
        )
    return overfit_gap


def run_phase3_training_execution(
    config,
    X: np.ndarray,
    y: np.ndarray,
    dataset_hash: str,
    logger,
    model_factory: Optional[Callable[..., Tuple[Any, int]]] = None,
) -> TrainingResult:
    import torch
    import torch.nn as nn
    import torch.optim as optim

    from impl_v1.training.distributed.advanced_checkpointing import (
        AsyncDistributedCheckpointManager,
    )
    from impl_v1.training.distributed.deepspeed_runtime import (
        DeepSpeedRuntime,
        DeepSpeedRuntimeConfig,
    )
    from impl_v1.training.distributed.fault_tolerant_resume import (
        ClusterFaultMonitor,
        FaultTolerantResumeManager,
    )
    from impl_v1.training.distributed.streaming_dataset import (
        ShardedStreamingDataset,
        StreamingDatasetConfig,
    )
    from impl_v1.training.distributed.training_monitor import TrainingMonitor
    from impl_v1.unified.performance import PerformanceIntelligence
    from impl_v1.training.distributed.drift_guard import DriftGuard

    logger.info("\n" + "=" * 58)
    logger.info("PHASE 3 - TRAINING EXECUTION")
    logger.info("=" * 58)

    ensure_dir(config.checkpoint_dir)
    ensure_dir(config.experiment_dir)
    ensure_dir(config.dataset_cache_dir)

    dist = None
    distributed_active = False
    rank = 0
    world_size = 1
    try:
        import torch.distributed as dist  # type: ignore

        distributed_active = bool(dist.is_available() and dist.is_initialized())
        if distributed_active:
            rank = dist.get_rank()
            world_size = dist.get_world_size()
    except Exception:
        dist = None
        distributed_active = False

    effective_world_size = max(1, world_size if distributed_active else 1)
    device = torch.device(f"cuda:{rank}" if torch.cuda.is_available() else "cpu")

    random.seed(config.seed)
    np.random.seed(config.seed)
    torch.manual_seed(config.seed)
    if torch.cuda.is_available():
        try:
            torch.cuda.set_device(device)
        except Exception:
            pass
        torch.cuda.manual_seed_all(config.seed)
        torch.backends.cuda.matmul.allow_tf32 = False
        torch.backends.cudnn.allow_tf32 = False
        torch.backends.cudnn.deterministic = True
        torch.backends.cudnn.benchmark = False
        try:
            torch.cuda.reset_peak_memory_stats(device)
        except Exception:
            pass
    os.environ.setdefault("CUBLAS_WORKSPACE_CONFIG", ":4096:8")
    try:
        torch.use_deterministic_algorithms(True, warn_only=True)
    except Exception:
        pass
    try:
        torch.set_float32_matmul_precision("high")
    except Exception:
        pass

    X_data = np.ascontiguousarray(X, dtype=np.float32)
    y_data = np.ascontiguousarray(y, dtype=np.int64)

    train_X, train_y, val_X, val_y, test_X, test_y = _split_train_validation_test(
        X_data,
        y_data,
        seed=DATA_SPLIT_SEED,
    )
    total_samples = int(X_data.shape[0])
    logger.info(f"  split_seed: {DATA_SPLIT_SEED}")
    logger.info(
        "  split_sizes: train=%s | val=%s | test=%s",
        int(train_y.size),
        int(val_y.size),
        int(test_y.size),
    )
    logger.info(f"  train_class_distribution: {_class_distribution(train_y)}")
    logger.info(f"  val_class_distribution: {_class_distribution(val_y)}")
    logger.info(f"  test_class_distribution: {_class_distribution(test_y)}")
    logger.info("  test split reserved and never used during training")

    model, optimizer, criterion, effective_hidden_dim = _create_training_stack(
        config,
        total_samples=total_samples,
        device=device,
        optim_module=optim,
        nn_module=nn,
        model_factory=model_factory,
    )
    requires_unused_parameter_detection = bool(
        getattr(model, "requires_unused_parameter_detection", False)
    )
    if effective_hidden_dim != int(config.hidden_dim):
        logger.info(
            "  model_capacity: hidden_dim reduced from %s to %s because total_samples=%s < 10000",
            int(config.hidden_dim),
            effective_hidden_dim,
            total_samples,
        )
    else:
        logger.info(
            "  model_capacity: hidden_dim=%s (total_samples=%s)",
            effective_hidden_dim,
            total_samples,
        )
    scheduler = (
        optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=max(config.num_epochs, 1))
        if config.cosine_lr
        else None
    )

    bf16_enabled = bool(
        config.use_bf16
        and torch.cuda.is_available()
        and hasattr(torch.cuda, "is_bf16_supported")
        and torch.cuda.is_bf16_supported()
    )
    use_amp = bool(config.use_amp and torch.cuda.is_available() and not bf16_enabled)
    precision_mode = "bf16" if bf16_enabled else ("fp16" if use_amp else "fp32")
    scaler = torch.amp.GradScaler("cuda") if use_amp else None

    stored_optimal_batch = 0
    if config.adaptive_batch_size:
        try:
            from impl_v1.training.config.adaptive_batch import (
                BATCH_CONFIG_PATH,
                load_batch_config,
            )

            if os.path.exists(BATCH_CONFIG_PATH):
                stored_optimal_batch = int(load_batch_config())
        except Exception:
            stored_optimal_batch = 0

    global_batch_target = max(config.base_batch_size, stored_optimal_batch or 0)
    local_batch = max(
        config.min_local_batch, global_batch_target // effective_world_size
    )
    load_balance_factor = 1.0
    if torch.cuda.is_available():
        try:
            props = torch.cuda.get_device_properties(device)
            total_mem_gb = props.total_memory / (1024**3)
            if total_mem_gb < 6:
                local_batch = min(local_batch, 128)
            elif total_mem_gb < 10:
                local_batch = min(local_batch, 256)
            if distributed_active and dist is not None:
                local_capacity = float(
                    total_mem_gb * max(props.multi_processor_count, 1)
                )
                capacities: List[float] = [0.0 for _ in range(effective_world_size)]
                dist.all_gather_object(capacities, local_capacity)
                average_capacity = sum(float(item) for item in capacities) / max(
                    len(capacities), 1
                )
                load_balance_factor = max(
                    0.5, min(1.75, local_capacity / max(average_capacity, 1e-6))
                )
                local_batch = int(round(local_batch * load_balance_factor))
        except Exception:
            pass

    local_batch = clamp_int(local_batch, config.min_local_batch, config.max_local_batch)
    gradient_accumulation_steps = max(
        1,
        int(
            max(
                config.gradient_accumulation_steps,
                math.ceil(
                    global_batch_target / max(1, local_batch * effective_world_size)
                ),
            )
        ),
    )

    if distributed_active and not config.deepspeed_enabled:
        from torch.nn.parallel import DistributedDataParallel as DDP

        ddp_kwargs = {
            "find_unused_parameters": requires_unused_parameter_detection,
            "gradient_as_bucket_view": True,
            "bucket_cap_mb": max(16, int(config.ddp_bucket_cap_mb)),
            "static_graph": not config.gradient_checkpointing,
        }
        if device.type == "cuda":
            model = DDP(
                model,
                device_ids=[device.index],
                output_device=device.index,
                **ddp_kwargs,
            )
        else:
            model = DDP(model, **ddp_kwargs)

    train_module = model.module if hasattr(model, "module") else model
    ds_runtime = DeepSpeedRuntime(
        DeepSpeedRuntimeConfig(
            enabled=config.deepspeed_enabled,
            zero_stage=config.zero_stage,
            bf16=bf16_enabled,
            fp16=use_amp,
            gradient_accumulation_steps=gradient_accumulation_steps,
            gradient_clipping=config.gradient_clip,
            train_micro_batch_size_per_gpu=local_batch,
            reduce_bucket_size=config.comm_bucket_size,
            allgather_bucket_size=config.comm_bucket_size,
            stage3_prefetch_bucket_size=config.prefetch_bucket_size,
            logging_steps=10,
        )
    )
    using_deepspeed_engine = bool(config.deepspeed_enabled and ds_runtime.available)
    engine, optimizer, _, scheduler = ds_runtime.initialize(
        model=model,
        optimizer=optimizer,
        scheduler=scheduler,
        model_parameters=train_module.parameters(),
        train_batch_size=local_batch
        * effective_world_size
        * gradient_accumulation_steps,
    )

    guard = DriftGuard()
    ckpt_manager = AsyncDistributedCheckpointManager(
        config.checkpoint_dir,
        max_workers=max(2, int(config.checkpoint_workers)),
        tiered_storage_root=(
            config.checkpoint_storage_dir if config.tiered_checkpoint_storage else ""
        ),
    )
    resume_manager = FaultTolerantResumeManager(ckpt_manager)
    monitor = (
        TrainingMonitor(
            os.path.join(config.experiment_dir, "training_dashboard.json"),
            flush_interval_seconds=2.0,
        )
        if config.monitor_training
        else None
    )
    fault_monitor = (
        ClusterFaultMonitor()
        if distributed_active and effective_world_size > 1
        else None
    )
    performance_tuner = PerformanceIntelligence()
    checkpoint_futures: List[Any] = []
    latest_checkpoint_future: Any = None
    best_checkpoint_future: Any = None

    if fault_monitor is not None:
        fault_monitor.register_nodes([f"rank-{i}" for i in range(effective_world_size)])
        fault_monitor.start(current_epoch=0)

    logger.info(f"  device: {device}")
    logger.info(f"  precision_mode: {precision_mode}")
    logger.info(
        f"  flash_attention: {getattr(train_module, 'flash_attention_enabled', False)}"
    )
    logger.info(f"  cosine_lr: {config.cosine_lr}")
    logger.info(f"  deepspeed_requested: {config.deepspeed_enabled}")
    logger.info(f"  deepspeed_active: {using_deepspeed_engine}")
    logger.info(f"  zero_stage: {config.zero_stage}")
    logger.info(f"  gradient_clip: {config.gradient_clip}")
    logger.info(f"  local_batch: {local_batch}")
    logger.info(f"  effective_world_size: {effective_world_size}")
    logger.info(f"  gradient_accumulation_steps: {gradient_accumulation_steps}")
    logger.info(f"  async_pipeline: {config.async_pipeline}")

    per_epoch: List[dict] = []
    best_acc = 0.0
    best_val_f1 = float("-inf")
    best_val_loss = float("inf")
    val_loss_plateau_count = 0
    best_metrics = {
        "val_accuracy": 0.0,
        "val_precision": 0.0,
        "val_recall": 0.0,
        "val_f1": 0.0,
    }
    drift_aborted = False
    resumed_from_checkpoint = False
    start_epoch = 0
    latest_checkpoint_meta_path = ""
    best_checkpoint_meta_path = ""
    t_training_start = time.perf_counter()
    latest_sps = 0.0

    if config.resume_if_available:
        decision = resume_manager.recover(rank=rank)
        if decision.checkpoint is not None:
            try:
                training_state = decision.checkpoint.optimizer_state
                if training_state.get("dataset_hash") != dataset_hash:
                    raise RuntimeError("Checkpoint dataset hash mismatch")
                model.load_state_dict(decision.checkpoint.model_state)
                optimizer_state = (
                    training_state.get("optimizer_state_dict")
                    or training_state.get("optimizer_state")
                    or {}
                )
                if optimizer_state:
                    optimizer.load_state_dict(optimizer_state)
                scheduler_state = (
                    decision.checkpoint.scheduler_state
                    or training_state.get("scheduler_state_dict")
                    or {}
                )
                if scheduler is not None and scheduler_state:
                    scheduler.load_state_dict(scheduler_state)
                scaler_state = training_state.get("scaler_state_dict")
                if scaler is not None and scaler_state:
                    scaler.load_state_dict(scaler_state)
                set_rng_state(torch, training_state.get("rng_state", {}))
                start_epoch = int(training_state.get("epoch", 0))
                best_acc = float(training_state.get("best_accuracy", 0.0) or 0.0)
                best_val_f1 = float(training_state.get("best_val_f1", 0.0) or 0.0)
                best_val_loss_raw = training_state.get("best_val_loss")
                best_val_loss = (
                    float(best_val_loss_raw)
                    if best_val_loss_raw is not None
                    else float("inf")
                )
                val_loss_plateau_count = int(
                    training_state.get("val_loss_plateau_count", 0) or 0
                )
                best_metrics = {
                    "val_accuracy": float(
                        training_state.get("best_val_accuracy", best_acc) or best_acc
                    ),
                    "val_precision": float(
                        training_state.get("best_val_precision", 0.0) or 0.0
                    ),
                    "val_recall": float(
                        training_state.get("best_val_recall", 0.0) or 0.0
                    ),
                    "val_f1": float(
                        training_state.get("best_val_f1", 0.0) or 0.0
                    ),
                }
                per_epoch = list(training_state.get("per_epoch", []))
                latest_checkpoint_meta_path = str(
                    training_state.get("latest_checkpoint_meta_path", "")
                )
                best_checkpoint_meta_path = str(
                    training_state.get("best_checkpoint_meta_path", "")
                )
                resumed_from_checkpoint = start_epoch > 0
                best_val_loss_text = (
                    f"{best_val_loss:.6f}" if math.isfinite(best_val_loss) else "inf"
                )
                logger.info(
                    "  resumed from checkpoint: epoch=%s, best_val_f1=%.4f, best_val_loss=%s",
                    start_epoch,
                    best_val_f1,
                    best_val_loss_text,
                )
            except Exception as exc:
                logger.warning(f"  resume skipped: {exc}")

    def _forward_pass(batch_x: torch.Tensor) -> torch.Tensor:
        module_length = len(train_module) if hasattr(train_module, "__len__") else 0
        if (
            config.gradient_checkpointing
            and train_module.training
            and module_length >= 2
        ):
            from torch.utils.checkpoint import checkpoint_sequential

            segments = min(3, module_length)
            return checkpoint_sequential(
                train_module, segments=segments, input=batch_x, use_reentrant=False
            )
        return train_module(batch_x)

    def _device_batches(source_iter):
        if not config.async_pipeline or device.type != "cuda":
            for batch_x_np, batch_y_np in source_iter:
                yield (
                    torch.from_numpy(batch_x_np).to(device, non_blocking=True),
                    torch.from_numpy(batch_y_np).to(device, non_blocking=True),
                )
            return

        preload_stream = torch.cuda.Stream(device=device)
        pending = None

        def _stage(batch_x_np, batch_y_np):
            with torch.cuda.stream(preload_stream):
                next_x = torch.from_numpy(batch_x_np).to(device, non_blocking=True)
                next_y = torch.from_numpy(batch_y_np).to(device, non_blocking=True)
            return next_x, next_y

        source_iter = iter(source_iter)
        for batch_x_np, batch_y_np in source_iter:
            if pending is None:
                pending = _stage(batch_x_np, batch_y_np)
                continue
            preload_stream.synchronize()
            current = pending
            pending = _stage(batch_x_np, batch_y_np)
            yield current
        if pending is not None:
            preload_stream.synchronize()
            yield pending

    for epoch in range(start_epoch, config.num_epochs):
        stream = ShardedStreamingDataset(
            train_X,
            train_y,
            StreamingDatasetConfig(
                batch_size=local_batch,
                rank=rank,
                world_size=max(effective_world_size, 1),
                shuffle=True,
                seed=config.seed + epoch,
                prefetch_batches=config.prefetch_batches,
                cache_in_ram=True,
                max_ram_cache_shards=max(1, int(config.ram_cache_batches)),
                cache_dir=(
                    config.dataset_cache_dir if config.dataset_cache_to_disk else None
                ),
                cache_to_disk=bool(config.dataset_cache_to_disk),
            ),
        )

        engine.train()
        total_loss = 0.0
        correct = 0
        processed = 0
        max_grad = 0.0
        step = 0
        epoch_aux_loss_total = 0.0
        train_true_batches: List[np.ndarray] = []
        train_pred_batches: List[np.ndarray] = []
        optimizer.zero_grad(set_to_none=True)
        t0 = time.perf_counter()

        for batch_x, batch_y in _device_batches(stream):
            step += 1
            if fault_monitor is not None:
                fault_monitor.heartbeat(f"rank-{rank}")

            sync_now = step % gradient_accumulation_steps == 0
            sync_context = nullcontext()
            if (
                distributed_active
                and not using_deepspeed_engine
                and hasattr(model, "no_sync")
                and not sync_now
            ):
                sync_context = model.no_sync()

            with sync_context:
                if bf16_enabled:
                    with torch.autocast(device_type=device.type, dtype=torch.bfloat16):
                        out = _forward_pass(batch_x)
                        objective_loss, reported_loss, aux_loss_value = (
                            _compute_training_objective_loss(
                                train_module,
                                out,
                                batch_y,
                                criterion,
                                torch,
                            )
                        )
                elif use_amp:
                    with torch.autocast(device_type=device.type, dtype=torch.float16):
                        out = _forward_pass(batch_x)
                        objective_loss, reported_loss, aux_loss_value = (
                            _compute_training_objective_loss(
                                train_module,
                                out,
                                batch_y,
                                criterion,
                                torch,
                            )
                        )
                else:
                    out = _forward_pass(batch_x)
                    objective_loss, reported_loss, aux_loss_value = (
                        _compute_training_objective_loss(
                            train_module,
                            out,
                            batch_y,
                            criterion,
                            torch,
                        )
                    )

                loss_for_update = objective_loss / gradient_accumulation_steps
                if using_deepspeed_engine:
                    engine.backward(loss_for_update)
                elif scaler is not None:
                    scaler.scale(loss_for_update).backward()
                else:
                    loss_for_update.backward()

            if sync_now:
                if using_deepspeed_engine:
                    grad_norm = safe_grad_norm(torch, train_module.parameters())
                    max_grad = max(max_grad, grad_norm)
                    engine.step()
                elif scaler is not None:
                    scaler.unscale_(optimizer)
                    grad_norm = safe_grad_norm(torch, train_module.parameters())
                    max_grad = max(max_grad, grad_norm)
                    torch.nn.utils.clip_grad_norm_(
                        train_module.parameters(), config.gradient_clip
                    )
                    scaler.step(optimizer)
                    scaler.update()
                else:
                    grad_norm = safe_grad_norm(torch, train_module.parameters())
                    max_grad = max(max_grad, grad_norm)
                    torch.nn.utils.clip_grad_norm_(
                        train_module.parameters(), config.gradient_clip
                    )
                    optimizer.step()
                optimizer.zero_grad(set_to_none=True)

            pred = out.argmax(dim=1)
            batch_size = batch_y.size(0)
            correct += int((pred == batch_y).sum().item())
            processed += batch_size
            total_loss += float(reported_loss.item()) * batch_size
            epoch_aux_loss_total += aux_loss_value * batch_size
            train_true_batches.append(batch_y.detach().cpu().numpy())
            train_pred_batches.append(pred.detach().cpu().numpy())

            if monitor is not None:
                monitor.record_throughput(batch_size, time.perf_counter())
                monitor.record_runtime(
                    loss=float(reported_loss.item()),
                    accuracy=(correct / max(processed, 1)),
                )
                if (
                    torch.cuda.is_available()
                    and step % 5 == 0
                    and hasattr(performance_tuner, "sample_gpu_utilization")
                ):
                    monitor.record_gpu(
                        utilization=performance_tuner.sample_gpu_utilization(device),
                        memory_allocated_mb=(
                            torch.cuda.memory_allocated(device) / (1024**2)
                        ),
                        memory_reserved_mb=(
                            torch.cuda.memory_reserved(device) / (1024**2)
                        ),
                    )

        if processed == 0:
            raise RuntimeError("No samples processed during training epoch")

        if step % gradient_accumulation_steps != 0:
            if using_deepspeed_engine:
                grad_norm = safe_grad_norm(torch, train_module.parameters())
                max_grad = max(max_grad, grad_norm)
                engine.step()
            elif scaler is not None:
                scaler.unscale_(optimizer)
                grad_norm = safe_grad_norm(torch, train_module.parameters())
                max_grad = max(max_grad, grad_norm)
                torch.nn.utils.clip_grad_norm_(
                    train_module.parameters(), config.gradient_clip
                )
                scaler.step(optimizer)
                scaler.update()
            else:
                grad_norm = safe_grad_norm(torch, train_module.parameters())
                max_grad = max(max_grad, grad_norm)
                torch.nn.utils.clip_grad_norm_(
                    train_module.parameters(), config.gradient_clip
                )
                optimizer.step()
            optimizer.zero_grad(set_to_none=True)

        avg_loss = total_loss / processed
        latest_sps = processed / max(time.perf_counter() - t0, 1e-6)
        train_targets = (
            np.concatenate(train_true_batches)
            if train_true_batches
            else np.empty((0,), dtype=np.int64)
        )
        train_predictions = (
            np.concatenate(train_pred_batches)
            if train_pred_batches
            else np.empty((0,), dtype=np.int64)
        )
        train_metrics = _macro_classification_metrics(
            train_targets,
            train_predictions,
            config.num_classes,
        )
        train_metrics["loss"] = avg_loss
        evaluation_model = engine if using_deepspeed_engine else model
        val_metrics = _evaluate_split(
            evaluation_model,
            val_X,
            val_y,
            criterion,
            device,
            local_batch,
            config.num_classes,
            torch,
        )

        if scheduler is not None:
            scheduler.step()
        gpu_util = (
            performance_tuner.sample_gpu_utilization(device)
            if torch.cuda.is_available()
            and hasattr(performance_tuner, "sample_gpu_utilization")
            else 0.0
        )
        gpu_mem_util = (
            cuda_memory_utilization(torch, device) if torch.cuda.is_available() else 0.0
        )
        if (
            config.auto_batch_tuning
            and torch.cuda.is_available()
            and epoch < config.num_epochs - 1
        ):
            local_batch, gradient_accumulation_steps, tuning = autotune_local_batch(
                current_batch=local_batch,
                gradient_accumulation=gradient_accumulation_steps,
                optimizer=optimizer,
                performance_tuner=performance_tuner,
                latest_sps=latest_sps,
                elapsed=max(time.perf_counter() - t0, 1e-6),
                world_size=effective_world_size,
                zero_stage=config.zero_stage,
                gpu_utilization=gpu_util,
                memory_utilization=gpu_mem_util,
                min_batch=config.min_local_batch,
                max_batch=config.max_local_batch,
                min_lr=config.min_lr,
                max_lr=config.max_lr,
            )
        else:
            tuning = {}

        hash_local = hash_model_weights(train_module)
        if distributed_active and dist is not None:
            hashes: List[str] = ["" for _ in range(effective_world_size)]
            dist.all_gather_object(hashes, hash_local)
            merged_hash = hashlib.sha256("".join(hashes).encode()).hexdigest()[:16]
            cluster_sps = latest_sps * effective_world_size
        else:
            hashes = [hash_local]
            merged_hash = hash_local
            cluster_sps = latest_sps

        overfit_gap = _log_overfit_status(
            logger,
            epoch=epoch + 1,
            total_epochs=config.num_epochs,
            train_loss=float(train_metrics["loss"]),
            val_loss=float(val_metrics["loss"]),
            train_f1=float(train_metrics["f1"]),
            val_f1=float(val_metrics["f1"]),
        )
        logger.info(
            "  epoch_runtime | val_accuracy=%.4f | sps=%.1f | grad=%.4f | lr=%.6f",
            float(val_metrics["accuracy"]),
            cluster_sps,
            max_grad,
            float(optimizer.param_groups[0].get("lr", OPTIMIZER_LR)),
        )
        if epoch_aux_loss_total > 0.0:
            logger.info(
                "  moe_aux_loss=%.6f",
                epoch_aux_loss_total / max(processed, 1),
            )

        best_val_loss, val_loss_plateau_count, should_stop_early = _update_val_loss_plateau(
            best_val_loss,
            val_loss_plateau_count,
            float(val_metrics["loss"]),
        )
        should_save_best = _should_save_best_checkpoint(
            best_val_f1,
            train_f1=float(train_metrics["f1"]),
            val_f1=float(val_metrics["f1"]),
        )
        if should_save_best:
            best_val_f1 = float(val_metrics["f1"])
            best_acc = float(val_metrics["accuracy"])
            best_metrics = {
                "val_accuracy": float(val_metrics["accuracy"]),
                "val_precision": float(val_metrics["precision"]),
                "val_recall": float(val_metrics["recall"]),
                "val_f1": float(val_metrics["f1"]),
            }

        guard.check_epoch(
            epoch=epoch + 1,
            accuracy=float(val_metrics["accuracy"]),
            loss=float(val_metrics["loss"]),
            gradient_norm=max_grad,
        )
        drift = guard.get_report()
        per_epoch.append(
            {
                "epoch": epoch + 1,
                "loss": float(val_metrics["loss"]),
                "accuracy": float(val_metrics["accuracy"]),
                "train_loss": float(train_metrics["loss"]),
                "val_loss": float(val_metrics["loss"]),
                "train_accuracy": float(train_metrics["accuracy"]),
                "val_accuracy": float(val_metrics["accuracy"]),
                "train_precision": float(train_metrics["precision"]),
                "val_precision": float(val_metrics["precision"]),
                "train_recall": float(train_metrics["recall"]),
                "val_recall": float(val_metrics["recall"]),
                "train_f1": float(train_metrics["f1"]),
                "val_f1": float(val_metrics["f1"]),
                "overfit_gap": overfit_gap,
                "precision_mode": precision_mode,
                "cluster_sps": cluster_sps,
                "weight_hash": merged_hash,
                "grad_norm": max_grad,
                "moe_aux_loss": epoch_aux_loss_total / max(processed, 1),
                "batch_size": local_batch,
                "gradient_accumulation_steps": gradient_accumulation_steps,
                "gpu_utilization": gpu_util,
                "gpu_memory_utilization": gpu_mem_util,
                "lr": optimizer.param_groups[0].get("lr", OPTIMIZER_LR),
                "load_balance_factor": round(load_balance_factor, 4),
                "effective_hidden_dim": effective_hidden_dim,
                "tuning": tuning,
            }
        )

        if monitor is not None:
            monitor.log_epoch(
                epoch=epoch + 1,
                loss=float(val_metrics["loss"]),
                accuracy=float(val_metrics["accuracy"]),
                gpu_utilization=gpu_util,
                gpu_memory_utilization=gpu_mem_util,
                batch_size=local_batch,
                learning_rate=float(
                    optimizer.param_groups[0].get("lr", OPTIMIZER_LR)
                ),
                gradient_accumulation=gradient_accumulation_steps,
                cluster_sps=cluster_sps,
            )

        if drift.should_abort:
            logger.error(f"  ABORT: Drift threshold exceeded at epoch {epoch + 1}")
            drift_aborted = True
            break

        model_state = {
            key: tensor.detach().cpu()
            for key, tensor in train_module.state_dict().items()
        }
        training_state = {
            "epoch": epoch + 1,
            "dataset_hash": dataset_hash,
            "accuracy": float(val_metrics["accuracy"]),
            "best_accuracy": best_acc,
            "loss": float(val_metrics["loss"]),
            "train_loss": float(train_metrics["loss"]),
            "train_accuracy": float(train_metrics["accuracy"]),
            "train_precision": float(train_metrics["precision"]),
            "train_recall": float(train_metrics["recall"]),
            "train_f1": float(train_metrics["f1"]),
            "val_accuracy": float(val_metrics["accuracy"]),
            "val_precision": float(val_metrics["precision"]),
            "val_recall": float(val_metrics["recall"]),
            "val_f1": float(val_metrics["f1"]),
            "best_val_accuracy": float(best_metrics["val_accuracy"]),
            "best_val_precision": float(best_metrics["val_precision"]),
            "best_val_recall": float(best_metrics["val_recall"]),
            "best_val_f1": float(best_metrics["val_f1"]),
            "best_val_loss": best_val_loss,
            "val_loss_plateau_count": val_loss_plateau_count,
            "overfit_gap": overfit_gap,
            "moe_aux_loss": epoch_aux_loss_total / max(processed, 1),
            "optimizer_state_dict": optimizer.state_dict(),
            "scheduler_state_dict": scheduler.state_dict()
            if scheduler is not None
            else {},
            "rng_state": get_rng_state(torch),
            "per_epoch": per_epoch,
            "precision_mode": precision_mode,
            "batch_size": local_batch,
            "gradient_accumulation_steps": gradient_accumulation_steps,
            "train_samples": int(train_y.size),
            "val_samples": int(val_y.size),
            "test_samples": int(test_y.size),
            "split_seed": DATA_SPLIT_SEED,
            "effective_hidden_dim": effective_hidden_dim,
            "optimizer_lr": OPTIMIZER_LR,
            "optimizer_weight_decay": OPTIMIZER_WEIGHT_DECAY,
            "label_smoothing": LABEL_SMOOTHING,
            "latest_checkpoint_meta_path": latest_checkpoint_meta_path,
            "best_checkpoint_meta_path": best_checkpoint_meta_path,
        }
        if scaler is not None:
            training_state["scaler_state_dict"] = scaler.state_dict()

        meta_common = {
            "epoch": epoch + 1,
            "accuracy": float(val_metrics["accuracy"]),
            "loss": float(val_metrics["loss"]),
            "train_loss": float(train_metrics["loss"]),
            "train_accuracy": float(train_metrics["accuracy"]),
            "train_f1": float(train_metrics["f1"]),
            "val_accuracy": float(val_metrics["accuracy"]),
            "val_precision": float(val_metrics["precision"]),
            "val_recall": float(val_metrics["recall"]),
            "val_f1": float(val_metrics["f1"]),
            "overfit_gap": overfit_gap,
            "moe_aux_loss": epoch_aux_loss_total / max(processed, 1),
            "saved_at": time.time(),
            "precision_mode": precision_mode,
            "dataset_hash": dataset_hash,
            "world_size": effective_world_size,
            "batch_size": local_batch,
            "gradient_accumulation_steps": gradient_accumulation_steps,
            "cluster_sps": cluster_sps,
            "effective_hidden_dim": effective_hidden_dim,
            "optimizer_lr": OPTIMIZER_LR,
            "optimizer_weight_decay": OPTIMIZER_WEIGHT_DECAY,
            "label_smoothing": LABEL_SMOOTHING,
        }

        if config.checkpoint_every_epoch:
            epoch_name = f"epoch_{epoch + 1:04d}"
            if config.async_checkpoints:
                checkpoint_futures = [
                    future for future in checkpoint_futures if not future.done()
                ]
                if len(checkpoint_futures) >= max(1, int(config.checkpoint_workers)):
                    checkpoint_futures[0].result()
                    checkpoint_futures = [
                        future for future in checkpoint_futures if not future.done()
                    ]
                future = ckpt_manager.save_async(
                    name=epoch_name,
                    model_state=model_state,
                    optimizer_state=training_state,
                    scheduler_state=training_state.get("scheduler_state_dict", {}),
                    meta={**meta_common, "checkpoint_name": epoch_name},
                    rank=rank,
                    world_size=effective_world_size,
                    is_latest=True,
                )
                checkpoint_futures.append(future)
                latest_checkpoint_future = future
            else:
                latest_checkpoint_meta_path = save_training_checkpoint(
                    base_dir=config.checkpoint_dir,
                    name=epoch_name,
                    model_state=model_state,
                    training_state=training_state,
                    meta={**meta_common, "is_latest": True},
                )
            if not config.async_checkpoints:
                prune_epoch_checkpoints(
                    config.checkpoint_dir, config.keep_epoch_checkpoints
                )

        if should_save_best:
            if config.async_checkpoints:
                future = ckpt_manager.save_async(
                    name="best",
                    model_state=model_state,
                    optimizer_state=training_state,
                    scheduler_state=training_state.get("scheduler_state_dict", {}),
                    meta={**meta_common, "checkpoint_name": "best", "is_best": True},
                    rank=rank,
                    world_size=effective_world_size,
                    is_best=True,
                )
                checkpoint_futures.append(future)
                best_checkpoint_future = future
            else:
                best_checkpoint_meta_path = save_training_checkpoint(
                    base_dir=config.checkpoint_dir,
                    name="best",
                    model_state=model_state,
                    training_state=training_state,
                    meta={**meta_common, "is_best": True},
                )

        if should_stop_early:
            logger.info(
                "  early stopping triggered: val_loss failed to improve for %s consecutive epochs",
                EARLY_STOPPING_PATIENCE,
            )
            break

    if config.async_checkpoints:
        for future in checkpoint_futures:
            future.result()
        if latest_checkpoint_future is not None:
            latest_checkpoint_meta_path = str(
                latest_checkpoint_future.result() or latest_checkpoint_meta_path
            )
        if best_checkpoint_future is not None:
            best_checkpoint_meta_path = str(
                best_checkpoint_future.result() or best_checkpoint_meta_path
            )

    if fault_monitor is not None:
        fault_monitor.stop()
    if monitor is not None:
        monitor.close()
    ckpt_manager.close()

    epochs_completed = len(per_epoch)
    final_loss = per_epoch[-1]["val_loss"] if per_epoch else float("inf")
    final_accuracy = per_epoch[-1]["val_accuracy"] if per_epoch else 0.0
    cluster_sps = per_epoch[-1]["cluster_sps"] if per_epoch else 0.0
    merged_weight_hash = per_epoch[-1]["weight_hash"] if per_epoch else ""
    selected_metrics = (
        best_metrics
        if best_val_f1 > float("-inf")
        else {
            "val_accuracy": final_accuracy,
            "val_precision": per_epoch[-1]["val_precision"] if per_epoch else 0.0,
            "val_recall": per_epoch[-1]["val_recall"] if per_epoch else 0.0,
            "val_f1": per_epoch[-1]["val_f1"] if per_epoch else 0.0,
        }
    )
    best_accuracy = float(selected_metrics["val_accuracy"])
    reported_best_val_loss = best_val_loss if math.isfinite(best_val_loss) else final_loss

    return TrainingResult(
        epochs_completed=epochs_completed,
        final_loss=final_loss,
        final_accuracy=final_accuracy,
        best_accuracy=best_accuracy,
        cluster_sps=cluster_sps,
        merged_weight_hash=merged_weight_hash,
        drift_aborted=drift_aborted,
        per_epoch=per_epoch,
        resumed_from_checkpoint=resumed_from_checkpoint,
        start_epoch=start_epoch,
        latest_checkpoint_meta_path=latest_checkpoint_meta_path,
        best_checkpoint_meta_path=best_checkpoint_meta_path,
        val_accuracy=best_accuracy,
        val_f1=float(selected_metrics["val_f1"]),
        val_precision=float(selected_metrics["val_precision"]),
        val_recall=float(selected_metrics["val_recall"]),
        best_val_loss=reported_best_val_loss,
        train_samples=int(train_y.size),
        val_samples=int(val_y.size),
        test_samples=int(test_y.size),
        effective_hidden_dim=effective_hidden_dim,
        split_seed=DATA_SPLIT_SEED,
        optimizer_lr=OPTIMIZER_LR,
        optimizer_weight_decay=OPTIMIZER_WEIGHT_DECAY,
        label_smoothing=LABEL_SMOOTHING,
    )
