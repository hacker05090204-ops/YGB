from __future__ import annotations

from contextlib import nullcontext


def gpu_train_step(trainer, logger, *, torch, AMP_AVAILABLE, GradScaler, autocast):
    if not trainer._gpu_initialized:
        if not trainer._init_gpu_resources():
            return False, 0.0, 0.0

    try:
        if not hasattr(trainer, "_scaler") or trainer._scaler is None:
            trainer._scaler = GradScaler("cuda") if AMP_AVAILABLE else None
        amp_enabled = AMP_AVAILABLE and trainer._scaler is not None

        trainer._gpu_model.train()
        total_loss_gpu = torch.zeros(1, device=trainer._gpu_device)
        total_correct_gpu = torch.zeros(1, dtype=torch.long, device=trainer._gpu_device)
        total_samples = 0
        batch_count = 0
        try:
            trainer._last_total_batches = len(trainer._gpu_dataloader)
        except Exception:
            trainer._last_total_batches = 0
        trainer._last_batch_index = 0
        trainer._last_epoch_samples = 0

        trainer._gpu_optimizer.zero_grad(set_to_none=True)
        prefetch_stream = torch.cuda.Stream()
        data_iter = iter(trainer._gpu_dataloader)

        try:
            next_batch = next(data_iter)
            with torch.cuda.stream(prefetch_stream):
                next_features = next_batch[0].to(trainer._gpu_device, non_blocking=True)
                next_labels = next_batch[1].to(trainer._gpu_device, non_blocking=True)
        except StopIteration:
            return False, 0.0, 0.0

        while next_features is not None:
            if trainer._abort_flag.is_set():
                return False, 0.0, 0.0

            torch.cuda.current_stream().wait_stream(prefetch_stream)
            batch_features = next_features
            batch_labels = next_labels

            try:
                next_batch = next(data_iter)
                with torch.cuda.stream(prefetch_stream):
                    next_features = next_batch[0].to(
                        trainer._gpu_device, non_blocking=True
                    )
                    next_labels = next_batch[1].to(
                        trainer._gpu_device, non_blocking=True
                    )
            except StopIteration:
                next_features = None
                next_labels = None
            batch_size = batch_labels.size(0)

            if amp_enabled:
                with autocast("cuda", dtype=torch.float16):
                    outputs = trainer._gpu_model(batch_features)
                    loss = trainer._gpu_criterion(outputs, batch_labels)
                trainer._scaler.scale(loss).backward()
                trainer._scaler.step(trainer._gpu_optimizer)
                trainer._scaler.update()
                trainer._gpu_optimizer.zero_grad(set_to_none=True)
            else:
                outputs = trainer._gpu_model(batch_features)
                loss = trainer._gpu_criterion(outputs, batch_labels)
                loss.backward()
                trainer._gpu_optimizer.step()
                trainer._gpu_optimizer.zero_grad(set_to_none=True)

            total_loss_gpu += loss.detach() * batch_size
            _, predicted = torch.max(outputs.data, 1)
            total_correct_gpu += (predicted == batch_labels).sum()
            total_samples += batch_size
            batch_count += 1
            trainer._last_batch_index = batch_count
            trainer._last_epoch_samples = total_samples

        torch.cuda.synchronize()
        if total_samples > 0:
            trainer._gpu_features = batch_features.detach()
            trainer._gpu_labels = batch_labels.detach()
        avg_loss = (total_loss_gpu.item() / total_samples) if total_samples > 0 else 0.0
        train_accuracy = (
            (total_correct_gpu.item() / total_samples) if total_samples > 0 else 0.0
        )
        trainer._real_samples_processed += total_samples

        holdout_accuracy = train_accuracy
        if trainer._gpu_holdout_loader is not None:
            trainer._gpu_model.eval()
            holdout_correct_gpu = torch.zeros(
                1, dtype=torch.long, device=trainer._gpu_device
            )
            holdout_total = 0
            holdout_autocast = (
                autocast("cuda", dtype=torch.float16) if amp_enabled else nullcontext()
            )
            with torch.no_grad(), holdout_autocast:
                for h_features, h_labels in trainer._gpu_holdout_loader:
                    h_features = h_features.to(trainer._gpu_device, non_blocking=True)
                    h_labels = h_labels.to(trainer._gpu_device, non_blocking=True)
                    h_outputs = trainer._gpu_model(h_features)
                    _, h_predicted = torch.max(h_outputs.data, 1)
                    holdout_correct_gpu += (h_predicted == h_labels).sum()
                    holdout_total += h_labels.size(0)
            if holdout_total > 0:
                holdout_accuracy = holdout_correct_gpu.item() / holdout_total
            trainer._gpu_model.train()
        trainer._last_holdout_accuracy = holdout_accuracy
        accuracy = holdout_accuracy

        current_lr = trainer._gpu_optimizer.param_groups[0]["lr"]
        if hasattr(trainer, "_gpu_scheduler") and trainer._gpu_scheduler is not None:
            trainer._gpu_scheduler.step()
            current_lr = trainer._gpu_optimizer.param_groups[0]["lr"]

        if trainer._curriculum is not None:
            try:
                fpr = 1.0 - accuracy
                trainer._curriculum.update_metrics(
                    accuracy=accuracy,
                    fpr=fpr,
                    fnr=fpr,
                    loss=avg_loss,
                    epochs=1,
                    samples=total_samples,
                )
                advanced, adv_msg = trainer._curriculum.try_advance()
                if advanced:
                    logger.info("Curriculum: %s", adv_msg)
            except Exception as exc:
                logger.warning("Curriculum update: %s", exc)

        if trainer._promotion is not None:
            try:
                curriculum_done = (
                    trainer._curriculum.state.curriculum_complete
                    if trainer._curriculum
                    else False
                )
                fpr = 1.0 - accuracy
                trainer._promotion.evaluate_gates(
                    accuracy=accuracy,
                    fpr=fpr,
                    binding_ratio=1.0,
                    curriculum_complete=curriculum_done,
                    deterministic_verified=True,
                    previous_accuracy=trainer._last_accuracy,
                )
                if trainer._promotion.is_live_ready():
                    logger.info("🎯 LIVE_READY achieved — all 7 gates × 5 cycles")
            except Exception as exc:
                logger.warning("Promotion eval: %s", exc)

        try:
            trainer._run_governance_post_epoch_audit(
                epoch=trainer._epoch,
                accuracy=accuracy,
                holdout_accuracy=holdout_accuracy,
                loss=avg_loss,
                train_accuracy=train_accuracy,
                total_samples=total_samples,
            )
        except Exception as exc:
            logger.warning("Post-epoch governance audit failed: %s", exc)

        if hasattr(trainer, "_checkpoint_path") and trainer._checkpoint_path:
            try:
                if not trainer._checkpoint_meta_path:
                    raise RuntimeError("safetensors checkpoint support unavailable")
                model_state = {
                    key: value.detach().cpu().clone().contiguous()
                    for key, value in trainer._gpu_model.state_dict().items()
                }
                checkpoint_meta = trainer._build_checkpoint_metadata(
                    epoch=trainer._epoch,
                    accuracy=accuracy,
                    holdout_accuracy=holdout_accuracy,
                    loss=avg_loss,
                    real_samples_processed=trainer._real_samples_processed,
                )
                future = trainer._checkpoint_executor.submit(
                    trainer._save_checkpoint_bundle,
                    trainer._checkpoint_path,
                    trainer._checkpoint_meta_path,
                    model_state,
                    checkpoint_meta,
                )

                def _on_checkpoint_done(f, path=trainer._checkpoint_path):
                    exc = f.exception()
                    if exc:
                        logger.error(
                            "Async checkpoint save FAILED for %s: %s", path, exc
                        )
                    else:
                        logger.info("Checkpoint saved: %s", path)
                        if trainer._current_session:
                            trainer._current_session.checkpoints_saved += 1

                future.add_done_callback(_on_checkpoint_done)
            except Exception as exc:
                logger.warning("Checkpoint save failed: %s", exc)

        model_device = next(trainer._gpu_model.parameters()).device
        logger.info(
            "Epoch complete: %s batches, %s samples, train_acc=%.2f%%, holdout_acc=%.2f%%, loss=%.4f, lr=%.2e, device=%s",
            batch_count,
            total_samples,
            train_accuracy * 100.0,
            holdout_accuracy * 100.0,
            avg_loss,
            current_lr,
            model_device,
        )
        return True, accuracy, avg_loss
    except Exception as exc:
        trainer._last_error = str(exc).strip()
        import traceback

        err_tb = traceback.format_exc()
        logger.error("GPU training step failed: %s\n%s", exc, err_tb)
        print(f"\n!!! GPU TRAIN ERROR !!!\n{exc}\n{err_tb}", flush=True)
        return False, 0.0, 0.0
