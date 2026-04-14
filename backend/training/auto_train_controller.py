"""Automatic safetensors-driven training controller."""

from __future__ import annotations

import inspect
import logging
import threading
import time
import uuid
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import torch
from torch.utils.data import DataLoader, TensorDataset

from backend.training.adaptive_learner import AdaptationEvent, get_adaptive_learner
from backend.training.data_purity import AllRowsRejectedError, DataPurityEnforcer
from backend.training.incremental_trainer import (
    DEFAULT_BASELINE_PATH,
    DEFAULT_FEATURE_STORE_ROOT,
    DEFAULT_MODEL_PATH,
    DEFAULT_STATE_PATH,
    DatasetQualityGate,
    IncrementalTrainer,
)
from backend.training.rl_feedback import get_reward_buffer, get_rl_collector
from backend.training.runtime_status_validator import (
    TrainingGovernanceError,
    validate_promotion_readiness,
)
from backend.training.safetensors_store import FEATURE_DIM, SafetensorsFeatureStore

logger = logging.getLogger("ygb.training.auto_train_controller")

DEFAULT_CHECKPOINTS_ROOT = Path("checkpoints")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class AutoTrainConfig:
    feature_store_root: Path = Path(DEFAULT_FEATURE_STORE_ROOT)
    checkpoints_root: Path = DEFAULT_CHECKPOINTS_ROOT
    check_interval_seconds: float = 60.0
    min_new_samples: int = DatasetQualityGate.MIN_SAMPLES
    max_history: int = 50


@dataclass(frozen=True)
class AutoTrainRun:
    run_id: str
    trigger: str
    status: str
    started_at: str
    finished_at: str | None
    shard_count: int
    total_samples: int
    new_samples: int
    promoted: bool
    promotion_ready: bool | None
    checkpoint_updated: bool
    dataset_quality: dict[str, Any] | None
    trainer_status: str | None
    epoch_number: int | None
    error: str | None


class AutoTrainController:
    def __init__(
        self,
        config: AutoTrainConfig | None = None,
        *,
        trainer: IncrementalTrainer | None = None,
    ) -> None:
        self.config = config or AutoTrainConfig()
        self.feature_store = SafetensorsFeatureStore(self.config.feature_store_root)
        self.dataset_quality_gate = DatasetQualityGate()
        self._purity_enforcer = DataPurityEnforcer()
        self._rl_collector = get_rl_collector()
        self._reward_buffer = get_reward_buffer()
        self.trainer = trainer or IncrementalTrainer(
            model_path=self.config.checkpoints_root / DEFAULT_MODEL_PATH.name,
            state_path=self.config.checkpoints_root / DEFAULT_STATE_PATH.name,
            baseline_path=self.config.checkpoints_root / DEFAULT_BASELINE_PATH.name,
            feature_store_root=self.config.feature_store_root,
        )
        self.adaptive_learner = get_adaptive_learner(
            state_path=self.config.checkpoints_root / "adaptive_learning_state.json",
            ewc_state_path=self.config.checkpoints_root / "adaptive_ewc_state.safetensors",
        )
        self._state_lock = threading.Lock()
        self._stop_event = threading.Event()
        self._loop_thread: threading.Thread | None = None
        self._current_worker: threading.Thread | None = None
        self._run_history: list[AutoTrainRun] = []
        self._run_active = False
        self._active_run_id: str | None = None
        self._last_promoted_at: str | None = None
        self._last_processed_total_samples = 0
        self._last_observed_total_samples = 0
        self._last_observed_shard_count = 0
        self._next_check_at_epoch: float | None = None

    def start(self) -> bool:
        with self._state_lock:
            if self._loop_thread is not None and self._loop_thread.is_alive():
                logger.info("auto train scheduler already running")
                return False
            self._stop_event.clear()
            self._next_check_at_epoch = time.time() + float(
                self.config.check_interval_seconds
            )
            self._loop_thread = threading.Thread(
                target=self._run_loop,
                name="ygb-auto-train-scheduler",
                daemon=True,
            )
            self._loop_thread.start()
        logger.info(
            "auto train scheduler started interval_seconds=%.3f",
            float(self.config.check_interval_seconds),
        )
        return True

    def stop(self, timeout: float | None = None) -> bool:
        with self._state_lock:
            loop_thread = self._loop_thread
            if loop_thread is None:
                self._next_check_at_epoch = None
                logger.info("auto train scheduler already stopped")
                return False
            self._stop_event.set()
        join_timeout = (
            float(timeout)
            if timeout is not None
            else max(float(self.config.check_interval_seconds), 0.1) + 1.0
        )
        loop_thread.join(join_timeout)
        stopped = not loop_thread.is_alive()
        with self._state_lock:
            if stopped:
                self._loop_thread = None
                self._next_check_at_epoch = None
            else:
                logger.warning(
                    "auto train scheduler thread did not stop within %.3f seconds",
                    join_timeout,
                )
        if stopped:
            logger.info("auto train scheduler stopped")
        return stopped

    def is_scheduled_running(self) -> bool:
        with self._state_lock:
            return self._loop_thread is not None and self._loop_thread.is_alive()

    def trigger_check(self, *, trigger: str = "manual") -> dict[str, str]:
        placeholder = self._begin_run(trigger=trigger)
        if placeholder is None:
            current_run = self.get_last_run()
            run_id = current_run.run_id if current_run is not None else ""
            logger.info("auto train trigger ignored because a run is already active")
            return {"run_id": run_id, "status": "already_running"}

        worker = threading.Thread(
            target=self._execute_run,
            args=(placeholder,),
            name=f"ygb-auto-train-{placeholder.run_id}",
            daemon=True,
        )
        with self._state_lock:
            self._current_worker = worker
        worker.start()
        logger.info("auto train run triggered run_id=%s trigger=%s", placeholder.run_id, trigger)
        return {"run_id": placeholder.run_id, "status": "triggered"}

    def check_and_train(self, *, trigger: str = "manual") -> AutoTrainRun:
        placeholder = self._begin_run(trigger=trigger)
        if placeholder is None:
            current_run = self.get_last_run()
            if current_run is None:
                raise RuntimeError("auto train run requested while controller state is inconsistent")
            logger.info(
                "auto train synchronous request reused active run run_id=%s",
                current_run.run_id,
            )
            return current_run
        return self._execute_run(placeholder)

    def get_run_history(self, limit: int | None = None) -> list[AutoTrainRun]:
        with self._state_lock:
            history = list(self._run_history)
        if limit is None or limit <= 0:
            return history
        return history[-limit:]

    def get_last_run(self) -> AutoTrainRun | None:
        with self._state_lock:
            return self._run_history[-1] if self._run_history else None

    def get_status(self) -> dict[str, Any]:
        last_run = self.get_last_run()
        with self._state_lock:
            next_check_at_epoch = self._next_check_at_epoch
            scheduled_running = (
                self._loop_thread is not None and self._loop_thread.is_alive()
            )
            run_in_progress = self._run_active
            last_promoted_at = self._last_promoted_at
            total_runs = len(self._run_history)
            last_observed_total_samples = self._last_observed_total_samples
            last_observed_shard_count = self._last_observed_shard_count
            last_processed_total_samples = self._last_processed_total_samples
        next_check_at = (
            datetime.fromtimestamp(next_check_at_epoch, tz=timezone.utc).isoformat()
            if next_check_at_epoch is not None
            else None
        )
        next_check_in_seconds = (
            max(0.0, float(next_check_at_epoch - time.time()))
            if next_check_at_epoch is not None
            else None
        )
        return {
            "scheduled_running": scheduled_running,
            "run_in_progress": run_in_progress,
            "check_interval_seconds": float(self.config.check_interval_seconds),
            "next_check_at": next_check_at,
            "next_check_in_seconds": next_check_in_seconds,
            "last_promoted_at": last_promoted_at,
            "total_runs": total_runs,
            "last_observed_shard_count": last_observed_shard_count,
            "last_observed_total_samples": last_observed_total_samples,
            "last_processed_total_samples": last_processed_total_samples,
            "last_run": asdict(last_run) if last_run is not None else None,
        }

    def get_rl_stats(self) -> dict[str, float | int]:
        stats = self._reward_buffer.stats()
        return {
            "total_signals": int(stats["total_signals"]),
            "mean_reward": float(stats["mean_reward"]),
            "positive_signals": int(stats["positive_signals"]),
            "negative_signals": int(stats["negative_signals"]),
        }

    def get_adaptation_events(self) -> list[AdaptationEvent]:
        return self.adaptive_learner.get_events()

    def _run_loop(self) -> None:
        logger.info("auto train scheduler thread entered")
        try:
            while not self._stop_event.is_set():
                if self._stop_event.wait(float(self.config.check_interval_seconds)):
                    break
                try:
                    self.check_and_train(trigger="scheduled")
                except TrainingGovernanceError as exc:
                    logger.critical(
                        "scheduled auto train governance hard block: %s",
                        exc,
                    )
                    self._stop_event.set()
                    raise
                except Exception as exc:
                    logger.exception("scheduled auto train check failed: %s", exc)
                finally:
                    with self._state_lock:
                        if not self._stop_event.is_set():
                            self._next_check_at_epoch = time.time() + float(
                                self.config.check_interval_seconds
                            )
        finally:
            logger.info("auto train scheduler thread exiting")

    def _begin_run(self, *, trigger: str) -> AutoTrainRun | None:
        with self._state_lock:
            if self._run_active:
                return None
            now = _utc_now()
            placeholder = AutoTrainRun(
                run_id=uuid.uuid4().hex,
                trigger=trigger,
                status="RUNNING",
                started_at=now,
                finished_at=None,
                shard_count=self._last_observed_shard_count,
                total_samples=self._last_observed_total_samples,
                new_samples=max(
                    0,
                    self._last_observed_total_samples - self._last_processed_total_samples,
                ),
                promoted=False,
                promotion_ready=None,
                checkpoint_updated=False,
                dataset_quality=None,
                trainer_status=None,
                epoch_number=None,
                error=None,
            )
            self._run_active = True
            self._active_run_id = placeholder.run_id
            self._append_or_replace_run_locked(placeholder)
            return placeholder

    def _append_or_replace_run_locked(self, run: AutoTrainRun) -> None:
        if self._run_history and self._run_history[-1].run_id == run.run_id:
            self._run_history[-1] = run
        else:
            self._run_history.append(run)
        if len(self._run_history) > int(self.config.max_history):
            self._run_history = self._run_history[-int(self.config.max_history) :]

    def _finalize_run(
        self,
        run: AutoTrainRun,
        *,
        processed_total_samples: int | None,
    ) -> AutoTrainRun:
        with self._state_lock:
            if processed_total_samples is not None:
                self._last_processed_total_samples = processed_total_samples
            if run.promoted and run.finished_at is not None:
                self._last_promoted_at = run.finished_at
            self._run_active = False
            self._active_run_id = None
            self._current_worker = None
            self._append_or_replace_run_locked(run)
        return run

    @staticmethod
    def _shard_row_ids(shard_name: str, metadata: dict[str, Any], row_count: int) -> list[str]:
        raw_row_ids = metadata.get("row_ids")
        if isinstance(raw_row_ids, (list, tuple)):
            coerced_row_ids = [str(value) for value in raw_row_ids]
            if len(coerced_row_ids) == row_count:
                return coerced_row_ids
        sample_sha256 = str(metadata.get("sample_sha256") or metadata.get("sample_id") or "").strip()
        if row_count == 1:
            return [sample_sha256 or shard_name]
        return [f"{shard_name}:{index}" for index in range(row_count)]

    def _load_all_shards(self) -> tuple[np.ndarray, np.ndarray, list[str], int]:
        shard_names = self.feature_store.list_shards()
        feature_batches: list[np.ndarray] = []
        label_batches: list[np.ndarray] = []
        row_ids: list[str] = []
        for shard_name in shard_names:
            shard = self.feature_store.read(shard_name)
            shard_features = np.asarray(shard.features, dtype=np.float32)
            shard_labels = np.asarray(shard.labels, dtype=np.int64)
            feature_batches.append(shard_features)
            label_batches.append(shard_labels)
            row_ids.extend(
                self._shard_row_ids(
                    shard_name,
                    shard.metadata,
                    int(shard_labels.shape[0]),
                )
            )

        if feature_batches:
            features = np.concatenate(feature_batches, axis=0)
        else:
            features = np.empty((0, FEATURE_DIM), dtype=np.float32)
        if label_batches:
            labels = np.concatenate(label_batches, axis=0)
        else:
            labels = np.empty((0,), dtype=np.int64)

        shard_count = len(shard_names)
        try:
            features, labels, row_ids, purity_result = self._purity_enforcer.enforce_feature_tensor(
                features,
                labels,
                row_ids,
            )
        except AllRowsRejectedError:
            with self._state_lock:
                self._last_observed_shard_count = shard_count
                self._last_observed_total_samples = 0
            raise
        total_samples = int(labels.shape[0])
        if purity_result.rejected_count:
            logger.warning(
                "auto train data purity filtered rows shard_count=%d rejected=%d reasons=%s",
                shard_count,
                purity_result.rejected_count,
                purity_result.rejection_reasons,
            )
        with self._state_lock:
            self._last_observed_shard_count = shard_count
            self._last_observed_total_samples = total_samples
        return features, labels, row_ids, shard_count

    def _load_store_snapshot(self) -> tuple[np.ndarray, np.ndarray, list[str], int]:
        return self._load_all_shards()

    def _compute_trigger_threshold(self) -> int:
        total = int(self.feature_store.total_samples())
        if total < 500:
            return 50
        if total < 2000:
            return 100
        if total < 10000:
            return 200
        return 500

    @staticmethod
    def _log_run_summary(run: AutoTrainRun, *, threshold: int) -> None:
        logger.info(
            "auto train summary run_id=%s status=%s new_samples=%d threshold=%d total_samples=%d",
            run.run_id,
            run.status,
            run.new_samples,
            threshold,
            run.total_samples,
        )

    def _build_reward_weight_lookup(
        self,
        row_ids: list[str],
        weighted_rewards: dict[str, float] | None = None,
    ) -> dict[str, float] | None:
        if weighted_rewards is None:
            weighted_rewards = self._reward_buffer.get_weighted_signals()
        if not weighted_rewards:
            return None
        sample_weights: dict[str, float] = {}
        for row_id in row_ids:
            if row_id not in weighted_rewards:
                continue
            sample_weights[row_id] = float(max(0.1, 1.0 + weighted_rewards[row_id]))
        return sample_weights or None

    @staticmethod
    def _severity_counts_from_labels(labels: np.ndarray) -> dict[str, int]:
        label_aliases = {0: "NEGATIVE", 1: "POSITIVE"}
        severity_counts: dict[str, int] = {}
        for raw_label in np.asarray(labels, dtype=np.int64).tolist():
            label_value = int(raw_label)
            label_name = label_aliases.get(label_value, f"LABEL_{label_value}")
            severity_counts[label_name] = severity_counts.get(label_name, 0) + 1
        return severity_counts

    @staticmethod
    def _expand_adaptation_features(features: np.ndarray) -> np.ndarray:
        feature_array = np.asarray(features, dtype=np.float32)
        if feature_array.ndim != 2:
            raise ValueError(
                f"adaptation features must have shape (N, D), got {feature_array.shape}"
            )
        if feature_array.shape[1] == 512:
            return feature_array
        if feature_array.shape[1] == FEATURE_DIM:
            return np.repeat(feature_array, 2, axis=1).astype(np.float32, copy=False)
        raise ValueError(
            f"adaptation features must have width {FEATURE_DIM} or 512, got {feature_array.shape[1]}"
        )

    def _build_adaptation_dataloader(
        self,
        features: np.ndarray,
        labels: np.ndarray,
    ) -> DataLoader | None:
        feature_array = np.asarray(features, dtype=np.float32)
        label_array = np.asarray(labels, dtype=np.int64)
        if feature_array.ndim != 2 or label_array.ndim != 1:
            logger.warning(
                "adaptive learning dataloader skipped because feature or label array shape is invalid features=%s labels=%s",
                feature_array.shape,
                label_array.shape,
            )
            return None
        if feature_array.shape[0] == 0 or label_array.shape[0] == 0:
            return None
        if feature_array.shape[0] != label_array.shape[0]:
            logger.warning(
                "adaptive learning dataloader skipped because feature and label counts differ features=%d labels=%d",
                feature_array.shape[0],
                label_array.shape[0],
            )
            return None
        try:
            expanded_features = self._expand_adaptation_features(feature_array)
        except ValueError as exc:
            logger.warning("adaptive learning dataloader skipped: %s", exc)
            return None
        dataset = TensorDataset(
            torch.from_numpy(np.ascontiguousarray(expanded_features)),
            torch.from_numpy(np.ascontiguousarray(label_array)),
        )
        return DataLoader(
            dataset,
            batch_size=min(256, max(len(dataset), 1)),
            shuffle=False,
        )

    def _run_incremental_epoch(
        self,
        *,
        sample_weights: dict[str, float] | None,
    ):
        run_incremental_epoch = getattr(self.trainer, "run_incremental_epoch")
        try:
            signature = inspect.signature(run_incremental_epoch)
        except (TypeError, ValueError):
            signature = None
        if signature is not None and "sample_weights" in signature.parameters:
            return run_incremental_epoch(sample_weights=sample_weights)
        return run_incremental_epoch()

    def _artifact_signature(self) -> tuple[tuple[str, int, int], ...]:
        model_path = Path(getattr(self.trainer, "model_path", self.config.checkpoints_root / DEFAULT_MODEL_PATH.name))
        baseline_path = Path(
            getattr(
                self.trainer,
                "baseline_path",
                self.config.checkpoints_root / DEFAULT_BASELINE_PATH.name,
            )
        )
        signature: list[tuple[str, int, int]] = []
        for path in (model_path, baseline_path):
            if path.exists():
                stat_result = path.stat()
                signature.append((str(path), int(stat_result.st_mtime_ns), int(stat_result.st_size)))
            else:
                signature.append((str(path), 0, 0))
        return tuple(signature)

    def _latest_accuracy_snapshot(self):
        get_accuracy_history = getattr(self.trainer, "get_accuracy_history", None)
        if not callable(get_accuracy_history):
            logger.warning(
                "auto train trainer does not expose get_accuracy_history(); promotion tracking disabled"
            )
            return None
        history = list(get_accuracy_history())
        if not history:
            logger.warning("auto train trainer returned an empty accuracy history")
            return None
        return history[-1]

    def _execute_run(self, placeholder: AutoTrainRun) -> AutoTrainRun:
        features: np.ndarray | None = None
        labels: np.ndarray | None = None
        row_ids: list[str] = []
        shard_count = placeholder.shard_count
        total_samples = placeholder.total_samples
        new_samples = placeholder.new_samples
        processed_total_samples: int | None = None
        trigger_threshold = self._compute_trigger_threshold()
        dataset_quality_payload: dict[str, Any] | None = None
        checkpoint_updated = False
        trainer_status: str | None = None
        try:
            features, labels, row_ids, shard_count = self._load_store_snapshot()
            total_samples = int(labels.shape[0])
            new_samples = max(0, total_samples - self._last_processed_total_samples)
            severity_counts = self._severity_counts_from_labels(labels)
            adaptation_event = self.adaptive_learner.on_new_grab_cycle(
                severity_counts=severity_counts,
                model=getattr(self.trainer, "model", None),
                prev_dataloader=self._build_adaptation_dataloader(features, labels),
            )
            weighted_rewards = self._reward_buffer.get_weighted_signals()
            sample_weight_lookup = self._build_reward_weight_lookup(
                row_ids,
                weighted_rewards,
            )
            logger.info(
                "auto train scan run_id=%s shard_count=%d total_samples=%d new_samples=%d",
                placeholder.run_id,
                shard_count,
                total_samples,
                new_samples,
            )
            trigger_threshold = self._compute_trigger_threshold()
            logger.info(
                "AutoTrain check: new=%d threshold=%d total=%d",
                new_samples,
                trigger_threshold,
                total_samples,
            )
            if weighted_rewards:
                logger.info(
                    "auto train reward signals loaded run_id=%s total_signals=%d matched_rows=%d",
                    placeholder.run_id,
                    len(weighted_rewards),
                    0 if sample_weight_lookup is None else len(sample_weight_lookup),
                )
            if adaptation_event is not None:
                logger.info(
                    "adaptive learning event recorded run_id=%s js_distance=%.6f fisher_samples=%d",
                    placeholder.run_id,
                    adaptation_event.js_distance,
                    adaptation_event.fisher_sample_count,
                )

            if new_samples < trigger_threshold:
                final_run = replace(
                    placeholder,
                    status="SKIPPED",
                    finished_at=_utc_now(),
                    shard_count=shard_count,
                    total_samples=total_samples,
                    new_samples=new_samples,
                )
                logger.info(
                    "auto train skipped run_id=%s insufficient_new_samples=%d min_required=%d threshold=%d total_samples=%d",
                    placeholder.run_id,
                    new_samples,
                    trigger_threshold,
                    trigger_threshold,
                    total_samples,
                )
                self._log_run_summary(final_run, threshold=trigger_threshold)
                return self._finalize_run(
                    final_run,
                    processed_total_samples=None,
                )

            quality_report = self.dataset_quality_gate.validate_arrays(
                features,
                labels,
                total_samples,
            )
            dataset_quality_payload = asdict(quality_report)
            if not quality_report.passed:
                final_run = replace(
                    placeholder,
                    status="FAILED",
                    finished_at=_utc_now(),
                    shard_count=shard_count,
                    total_samples=total_samples,
                    new_samples=new_samples,
                    dataset_quality=dataset_quality_payload,
                    error="dataset_quality_failed",
                )
                logger.warning(
                    "auto train quality gate failed run_id=%s reasons=%s",
                    placeholder.run_id,
                    quality_report.failed_reasons,
                )
                processed_total_samples = total_samples
                self._log_run_summary(final_run, threshold=trigger_threshold)
                return self._finalize_run(
                    final_run,
                    processed_total_samples=processed_total_samples,
                )

            artifact_signature_before = self._artifact_signature()
            trainer_result = self._run_incremental_epoch(
                sample_weights=sample_weight_lookup,
            )
            artifact_signature_after = self._artifact_signature()
            checkpoint_updated = artifact_signature_before != artifact_signature_after
            trainer_status = str(getattr(trainer_result, "status", "COMPLETED"))
            latest_snapshot = self._latest_accuracy_snapshot()
            promotion_ready = False
            if latest_snapshot is not None:
                validate_promotion_readiness(latest_snapshot)
                promotion_ready = True
            promoted = bool(
                latest_snapshot is not None
                and promotion_ready
                and checkpoint_updated
                and trainer_status == "COMPLETED"
                and not bool(getattr(trainer_result, "rollback", False))
            )
            processed_total_samples = total_samples
            final_run = replace(
                placeholder,
                status=trainer_status,
                finished_at=_utc_now(),
                shard_count=shard_count,
                total_samples=total_samples,
                new_samples=new_samples,
                promoted=promoted,
                promotion_ready=promotion_ready,
                checkpoint_updated=checkpoint_updated,
                dataset_quality=dataset_quality_payload,
                trainer_status=trainer_status,
                epoch_number=int(getattr(trainer_result, "epoch_number", 0) or 0),
            )
            logger.info(
                "auto train completed run_id=%s trainer_status=%s promoted=%s checkpoint_updated=%s new_samples=%d threshold=%d total_samples=%d",
                placeholder.run_id,
                trainer_status,
                promoted,
                checkpoint_updated,
                new_samples,
                trigger_threshold,
                total_samples,
            )
            logger.info(
                "auto train rl mean_reward=%.6f total_signals=%d",
                self._reward_buffer.mean_reward(),
                int(self.get_rl_stats()["total_signals"]),
            )
            self._log_run_summary(final_run, threshold=trigger_threshold)
            return self._finalize_run(
                final_run,
                processed_total_samples=processed_total_samples,
            )
        except AllRowsRejectedError as exc:
            with self._state_lock:
                shard_count = self._last_observed_shard_count
            logger.critical(
                "auto train data purity failed run_id=%s trigger=%s reasons=%s",
                placeholder.run_id,
                placeholder.trigger,
                exc.result.rejection_reasons,
            )
            failed_run = replace(
                placeholder,
                status="FAILED",
                finished_at=_utc_now(),
                shard_count=shard_count,
                total_samples=0,
                new_samples=0,
                error=str(exc),
            )
            self._log_run_summary(failed_run, threshold=trigger_threshold)
            return self._finalize_run(
                failed_run,
                processed_total_samples=None,
            )
        except TrainingGovernanceError as exc:
            logger.critical(
                "auto train governance hard block run_id=%s trigger=%s status=%s error=%s",
                placeholder.run_id,
                placeholder.trigger,
                exc.status,
                exc,
            )
            failed_run = replace(
                placeholder,
                status=str(getattr(exc, "status", "FAILED")),
                finished_at=_utc_now(),
                shard_count=shard_count,
                total_samples=total_samples,
                new_samples=new_samples,
                promoted=False,
                promotion_ready=False,
                checkpoint_updated=checkpoint_updated,
                dataset_quality=dataset_quality_payload,
                trainer_status=trainer_status or str(getattr(exc, "status", "FAILED")),
                error=str(exc),
            )
            self._log_run_summary(failed_run, threshold=trigger_threshold)
            self._finalize_run(
                failed_run,
                processed_total_samples=None,
            )
            raise
        except Exception as exc:
            logger.exception(
                "auto train failed run_id=%s trigger=%s error=%s",
                placeholder.run_id,
                placeholder.trigger,
                exc,
            )
            failed_run = replace(
                placeholder,
                status="FAILED",
                finished_at=_utc_now(),
                shard_count=shard_count,
                total_samples=total_samples,
                new_samples=new_samples,
                error=str(exc),
            )
            self._log_run_summary(failed_run, threshold=trigger_threshold)
            return self._finalize_run(
                failed_run,
                processed_total_samples=processed_total_samples,
            )


_controller_singleton: AutoTrainController | None = None
_controller_singleton_lock = threading.Lock()


def get_auto_train_controller(
    config: AutoTrainConfig | None = None,
) -> AutoTrainController:
    global _controller_singleton
    with _controller_singleton_lock:
        if _controller_singleton is None:
            _controller_singleton = AutoTrainController(config=config)
        return _controller_singleton
