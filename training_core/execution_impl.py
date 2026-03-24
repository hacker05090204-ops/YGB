from __future__ import annotations

import math
import os
import random
import time
from contextlib import nullcontext
from typing import Any, Dict, List

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


def run_phase3_training_execution(
    config, X: np.ndarray, y: np.ndarray, dataset_hash: str, logger
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
    from impl_v1.training.distributed.optimized_layers import OptimizedTrainingModel
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

    model = OptimizedTrainingModel(
        input_dim=config.input_dim,
        hidden_dim=config.hidden_dim,
        num_classes=config.num_classes,
        attention_heads=config.attention_heads,
        token_dim=config.token_dim,
        use_flash_attention=config.use_flash_attention,
        gradient_checkpointing=config.gradient_checkpointing,
    ).to(device)
    optimizer = build_optimizer(optim, model.parameters(), config.base_lr, device)
    scheduler = (
        optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=max(config.num_epochs, 1))
        if config.cosine_lr
        else None
    )
    criterion = nn.CrossEntropyLoss()

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
            "find_unused_parameters": False,
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
                per_epoch = list(training_state.get("per_epoch", []))
                resumed_from_checkpoint = start_epoch > 0
                logger.info(
                    f"  resumed from checkpoint: epoch={start_epoch}, best_acc={best_acc:.4f}"
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
            X_data,
            y_data,
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
                        loss = criterion(out, batch_y)
                elif use_amp:
                    with torch.autocast(device_type=device.type, dtype=torch.float16):
                        out = _forward_pass(batch_x)
                        loss = criterion(out, batch_y)
                else:
                    out = _forward_pass(batch_x)
                    loss = criterion(out, batch_y)

                loss_for_update = loss / gradient_accumulation_steps
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
            total_loss += float(loss.item()) * batch_size

            if monitor is not None:
                monitor.record_throughput(batch_size, time.perf_counter())
                monitor.record_runtime(
                    loss=float(loss.item()), accuracy=(correct / max(processed, 1))
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
        acc = correct / processed
        latest_sps = processed / max(time.perf_counter() - t0, 1e-6)
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

        guard.check_epoch(
            epoch=epoch + 1, accuracy=acc, loss=avg_loss, gradient_norm=max_grad
        )
        drift = guard.get_report()
        per_epoch.append(
            {
                "epoch": epoch + 1,
                "loss": avg_loss,
                "accuracy": acc,
                "precision_mode": precision_mode,
                "cluster_sps": cluster_sps,
                "weight_hash": merged_hash,
                "grad_norm": max_grad,
                "batch_size": local_batch,
                "gradient_accumulation_steps": gradient_accumulation_steps,
                "gpu_utilization": gpu_util,
                "gpu_memory_utilization": gpu_mem_util,
                "lr": optimizer.param_groups[0].get("lr", config.base_lr),
                "load_balance_factor": round(load_balance_factor, 4),
                "tuning": tuning,
            }
        )

        logger.info(
            f"  Epoch {epoch + 1}/{config.num_epochs} | loss={avg_loss:.6f} | acc={acc:.4f} | sps={cluster_sps:.1f} | grad={max_grad:.4f}"
        )

        if monitor is not None:
            monitor.log_epoch(
                epoch=epoch + 1,
                loss=avg_loss,
                accuracy=acc,
                gpu_utilization=gpu_util,
                gpu_memory_utilization=gpu_mem_util,
                batch_size=local_batch,
                learning_rate=float(
                    optimizer.param_groups[0].get("lr", config.base_lr)
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
            "accuracy": acc,
            "best_accuracy": max(best_acc, acc),
            "loss": avg_loss,
            "optimizer_state_dict": optimizer.state_dict(),
            "scheduler_state_dict": scheduler.state_dict()
            if scheduler is not None
            else {},
            "rng_state": get_rng_state(torch),
            "per_epoch": per_epoch,
            "precision_mode": precision_mode,
            "batch_size": local_batch,
            "gradient_accumulation_steps": gradient_accumulation_steps,
        }
        if scaler is not None:
            training_state["scaler_state_dict"] = scaler.state_dict()

        meta_common = {
            "epoch": epoch + 1,
            "accuracy": acc,
            "loss": avg_loss,
            "saved_at": time.time(),
            "precision_mode": precision_mode,
            "dataset_hash": dataset_hash,
            "world_size": effective_world_size,
            "batch_size": local_batch,
            "gradient_accumulation_steps": gradient_accumulation_steps,
            "cluster_sps": cluster_sps,
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

        if acc >= best_acc:
            best_acc = acc
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

    if config.async_checkpoints:
        for future in checkpoint_futures:
            result = future.result()
            if result and isinstance(result, dict):
                if result.get("name") == "best":
                    best_checkpoint_meta_path = result.get(
                        "meta_path", best_checkpoint_meta_path
                    )
                latest_checkpoint_meta_path = result.get(
                    "meta_path", latest_checkpoint_meta_path
                )

    if fault_monitor is not None:
        fault_monitor.stop()
    if monitor is not None:
        monitor.close()
    ckpt_manager.close()

    epochs_completed = len(per_epoch)
    final_loss = per_epoch[-1]["loss"] if per_epoch else float("inf")
    final_accuracy = per_epoch[-1]["accuracy"] if per_epoch else 0.0
    total_duration = max(time.perf_counter() - t_training_start, 1e-6)
    cluster_sps = (
        (processed / total_duration) * effective_world_size if epochs_completed else 0.0
    )
    merged_weight_hash = per_epoch[-1]["weight_hash"] if per_epoch else ""

    return TrainingResult(
        epochs_completed=epochs_completed,
        final_loss=final_loss,
        final_accuracy=final_accuracy,
        best_accuracy=best_acc,
        cluster_sps=cluster_sps,
        merged_weight_hash=merged_weight_hash,
        drift_aborted=drift_aborted,
        per_epoch=per_epoch,
        resumed_from_checkpoint=resumed_from_checkpoint,
        start_epoch=start_epoch,
        latest_checkpoint_meta_path=latest_checkpoint_meta_path,
        best_checkpoint_meta_path=best_checkpoint_meta_path,
    )
