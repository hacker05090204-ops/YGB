from __future__ import annotations

import time
from datetime import datetime, timezone

from backend.training.runtime_artifacts import (
    probe_host_metrics,
    write_field_runtime_status,
    write_training_gate,
    write_training_telemetry,
    write_runtime_state_snapshot,
)

from impl_v1.phase49.runtime.training_reports import (
    TrainingMode as ReportTrainingMode,
    generate_training_report,
)


def persist_runtime_artifacts(trainer, logger, *, epoch_elapsed_seconds=None) -> None:
    try:
        host_metrics = probe_host_metrics()
        determinism_status = trainer._determinism_status()
        promotion_frozen = bool(
            trainer._promotion is not None and trainer._promotion.state.frozen
        )
        promotion_reason = (
            trainer._promotion.state.freeze_reason
            if trainer._promotion is not None
            else None
        )
        duration_seconds = trainer._session_duration_seconds()
        total_epochs = (
            trainer._target_epochs
            if trainer._target_epochs > 0 and trainer._target_epochs < 999999
            else 0
        )
        batch_velocity = None
        if epoch_elapsed_seconds and trainer._last_total_batches > 0:
            batch_velocity = trainer._last_total_batches / max(
                epoch_elapsed_seconds, 0.001
            )

        write_training_gate(
            determinism_status=determinism_status,
            freeze_status=promotion_frozen,
            gpu_temperature=host_metrics.get("gpu_temperature"),
        )
        write_training_telemetry(
            epoch=trainer._session_epoch
            if trainer._session_epoch > 0
            else trainer._epoch,
            batch_size=int(trainer._batch_size or 0),
            loss=float(trainer._last_loss),
            precision=float(trainer._last_accuracy),
            total_epochs=total_epochs,
            training_duration_seconds=duration_seconds,
            samples_per_second=float(trainer._samples_per_sec),
            determinism_status=determinism_status,
            freeze_status=promotion_frozen,
            gpu_temperature=host_metrics.get("gpu_temperature"),
            cpu_util=host_metrics.get("cpu_util"),
            gpu_util=host_metrics.get("gpu_util"),
            monotonic_start_time=int(
                trainer._session_start_monotonic or time.monotonic()
            ),
            dataset_size=(
                trainer._gpu_dataset_stats["train"]["total"]
                if trainer._gpu_dataset_stats
                else None
            ),
        )
        current_epoch = (
            trainer._session_epoch if trainer._session_epoch > 0 else trainer._epoch
        )
        runtime_total_epochs = (
            total_epochs if total_epochs > 0 else max(current_epoch, 0)
        )
        progress_pct = 0.0
        if runtime_total_epochs > 0 and current_epoch > 0:
            progress_pct = min((current_epoch / runtime_total_epochs) * 100.0, 100.0)
        if (
            trainer._last_loss > 0
            and trainer._best_accuracy > 0
            and trainer._last_accuracy >= trainer._best_accuracy
        ):
            loss_trend = "improving"
        elif trainer._last_loss > 0:
            loss_trend = "active"
        else:
            loss_trend = "idle"

        write_runtime_state_snapshot(
            mode=trainer._get_state().value,
            total_epochs=runtime_total_epochs,
            completed_epochs=current_epoch,
            current_loss=float(trainer._last_loss),
            best_loss=float(
                trainer._last_loss
                if trainer._best_accuracy <= 0
                else trainer._last_loss
            ),
            precision=float(trainer._last_accuracy),
            ece=0.0,
            drift_kl=0.0,
            duplicate_rate=0.0,
            gpu_util=host_metrics.get("gpu_util"),
            cpu_util=host_metrics.get("cpu_util"),
            temperature=host_metrics.get("gpu_temperature"),
            determinism_status=determinism_status,
            freeze_status=promotion_frozen,
            progress_pct=progress_pct,
            loss_trend=loss_trend,
            training_start_ms=(
                int(trainer._session_start_timestamp.timestamp() * 1000)
                if trainer._session_start_timestamp
                else 0
            ),
            total_errors=0,
        )
        write_field_runtime_status(
            containment_active=promotion_frozen,
            containment_reason=promotion_reason,
            precision_breach=bool(
                trainer._last_accuracy > 0
                and trainer._last_accuracy < trainer._early_stop_baseline
            ),
            drift_alert=promotion_frozen,
            freeze_valid=(not promotion_frozen) if trainer._last_accuracy > 0 else None,
            freeze_reason=promotion_reason,
            training_velocity_samples_hr=(
                float(trainer._samples_per_sec) * 3600.0
                if trainer._samples_per_sec > 0
                else None
            ),
            training_velocity_batches_sec=batch_velocity,
            gpu_utilization=host_metrics.get("gpu_util"),
            determinism_pass=determinism_status,
            data_freshness="fresh" if trainer._gpu_dataset_stats else None,
            merge_status="blocked" if promotion_frozen else None,
        )

        try:
            from backend.api.field_progression_api import sync_active_field_training

            sync_active_field_training(
                precision=float(trainer._last_accuracy)
                if trainer._last_accuracy > 0
                else None,
                fpr=max(0.0, 1.0 - float(trainer._last_accuracy))
                if trainer._last_accuracy > 0
                else None,
                containment=promotion_frozen,
                determinism_status=determinism_status,
            )
        except Exception as exc:
            logger.debug("Field progression sync skipped: %s", exc)
    except Exception as exc:
        logger.error("Failed to persist runtime artifacts: %s", exc)


def generate_session_report_for_trainer(trainer, logger) -> None:
    if not trainer._current_session:
        return
    try:
        stopped_at = datetime.now(timezone.utc).isoformat()
        epochs_trained = trainer._epoch - trainer._current_session.start_epoch
        checkpoint_events = [
            event for event in trainer._events if event.event_type == "CHECKPOINT_SAVED"
        ]
        last_hash = ""
        if checkpoint_events:
            details = checkpoint_events[-1].details
            if "hash: " in details:
                last_hash = details.split("hash: ")[1].rstrip(")")

        paths = generate_training_report(
            total_epochs=epochs_trained,
            gpu_used=trainer._current_session.gpu_used,
            started_at=trainer._current_session.started_at,
            stopped_at=stopped_at,
            checkpoints_saved=len(checkpoint_events),
            last_checkpoint_hash=last_hash,
            samples_processed=getattr(trainer, "_real_samples_processed", 0),
            training_mode=ReportTrainingMode.MODE_A,
            reports_dir="reports/g38_training",
        )
        trainer._emit_event(
            "REPORT_GENERATED", f"Training report saved: {list(paths.values())[0]}"
        )
        logger.info("Training report generated: %s", paths)
    except Exception as exc:
        logger.error("Failed to generate training report: %s", exc)
