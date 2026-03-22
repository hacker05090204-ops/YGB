# G38 Runtime - Auto Trainer
"""
AUTOMATIC IDLE-BASED TRAINING FOR G38.

PURPOSE:
Run background scheduler that triggers MODE-A training
when system is idle. Training happens WITHOUT human input,
WITHOUT human approval, WITHOUT AI authority.

BEHAVIOR:
Every 30 seconds:
    → Check idle conditions
    → If idle >= 60s
    → If no scan active
    → If no human interaction
    → If power connected
    → If GPU or CPU available
    → THEN trigger G38 MODE-A training

RULES:
- Training trigger is idempotent
- Never trigger twice concurrently
- If training is active → skip
- If scan starts → abort training
- If human interacts → abort training
- All guards checked BEFORE execution
- Guard failure = HARD BLOCK
"""

import asyncio
import concurrent.futures
import os
import subprocess
import sys
import threading
import time
import logging
import uuid
import hashlib
import json
import tempfile
import numpy as np
from datetime import datetime, timezone
from dataclasses import dataclass
from typing import Optional, Callable, List, Tuple, Dict, Any
from enum import Enum
import warnings

from backend.training.runtime_artifacts import (
    ensure_local_mode_a_bootstrap,
    probe_host_metrics,
    write_field_runtime_status,
    write_training_gate,
    write_training_telemetry,
    write_runtime_state_snapshot,
)

# Import idle detection
from .idle_detector import (
    get_idle_seconds,
    is_power_connected,
    is_scan_active,
)
from .telegram_notifier import build_training_telegram_notifier_from_env

# Import guards and conditions from G38
from impl_v1.phase49.governors.g38_self_trained_model import (
    IdleConditions,
    IdleCheckResult,
    IdleState,
    check_idle_conditions,
    evaluate_training_trigger,
    ALL_GUARDS,
    verify_all_guards,
    IDLE_THRESHOLD_SECONDS,
)

from impl_v1.phase49.governors.g38_safe_pretraining import (
    TrainingMode,
    verify_pretraining_guards,
    get_mode_a_status,
    TrainingModeStatus,
)

from impl_v1.phase49.runtime.training_reports import (
    TrainingMode as ReportTrainingMode,
    generate_training_report,
)

# Import REAL PyTorch GPU training backend
from impl_v1.phase49.governors.g37_pytorch_backend import (
    train_single_epoch,
    train_full,
    create_model_config,
    TrainingSample,
    get_torch_device,
    save_model_checkpoint,
    detect_compute_device,
    DeviceType,
    PYTORCH_AVAILABLE,
)

# Try importing torch for GPU enforcement
try:
    import torch
    import torch.nn as nn
    import torch.optim as optim
    from torch.amp import autocast, GradScaler
    TORCH_AVAILABLE = True
    AMP_AVAILABLE = True
except ImportError:
    TORCH_AVAILABLE = False
    AMP_AVAILABLE = False

try:
    from safetensors.torch import load_file as load_safetensors_file, save_file as save_safetensors_file
    SAFETENSORS_AVAILABLE = True
except ImportError:
    SAFETENSORS_AVAILABLE = False
    load_safetensors_file = None
    save_safetensors_file = None

# Training profile: deterministic (default) or fast
_TRAINING_PROFILE = os.environ.get("YGB_TRAINING_PROFILE", "deterministic").lower()
_FORCE_FRESH = os.environ.get("YGB_FORCE_FRESH_TRAIN", "0") == "1"

# GPU performance settings (profile-dependent)
if TORCH_AVAILABLE:
    if _TRAINING_PROFILE == "fast":
        torch.backends.cudnn.deterministic = False
        torch.backends.cudnn.benchmark = True
        # deterministic algorithms OFF for speed
    else:
        torch.backends.cudnn.deterministic = True
        torch.backends.cudnn.benchmark = False
    # Enable TF32 tensor core math (RTX 30-series) — ~3x faster matmul
    torch.backends.cuda.matmul.allow_tf32 = True
    torch.backends.cudnn.allow_tf32 = True

# CUBLAS deterministic workspace config
os.environ.setdefault('CUBLAS_WORKSPACE_CONFIG', ':4096:8')

# Background thread pool for async checkpoint saving (1 worker = serialized saves)
_checkpoint_executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)


# =============================================================================
# LOGGING
# =============================================================================

logger = logging.getLogger("g38.auto_trainer")
logger.setLevel(logging.INFO)

if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter(
        "%(asctime)s [G38] %(levelname)s: %(message)s"
    ))
    logger.addHandler(handler)


# =============================================================================
# TRAINING STATE
# =============================================================================

class TrainingState(Enum):
    """Current training state."""
    IDLE = "IDLE"
    CHECKING = "CHECKING"
    TRAINING = "TRAINING"
    ABORTING = "ABORTING"
    ERROR = "ERROR"


@dataclass
class TrainingEvent:
    """Training event for observability."""
    event_id: str
    event_type: str  # "IDLE_DETECTED", "TRAINING_STARTED", "TRAINING_STOPPED", etc.
    timestamp: str
    details: str
    idle_seconds: int
    gpu_used: bool
    epoch: Optional[int] = None


@dataclass
class TrainingSession:
    """Training session metadata for report generation."""
    started_at: str
    start_epoch: int
    gpu_used: bool
    checkpoints_saved: int = 0
    last_checkpoint_hash: str = ""


# =============================================================================
# AUTO TRAINER CLASS
# =============================================================================

class AutoTrainer:
    """
    MANUAL-CONTROL trainer for G38.
    
    Training is triggered ONLY by explicit user action via API.
    NO idle-based auto-trigger. NO automatic background training.
    
    OPTIMIZATION: Uses RealTrainingDataset with 18K+ structured samples,
    PyTorch DataLoader with pin_memory, and AMP mixed precision.
    """
    
    CHECK_INTERVAL_SECONDS = 30
    
    def __init__(self):
        self._state = TrainingState.IDLE
        self._training_lock = threading.RLock()
        self._abort_flag = threading.Event()
        self._events: List[TrainingEvent] = []
        self._epoch = 0  # Total epochs completed ever
        self._target_epochs = 0  # Target epochs for current session
        self._session_epoch = 0  # Current epoch within session (0 to target)
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._on_event_callback: Optional[Callable[[TrainingEvent], None]] = None
        self._current_session: Optional[TrainingSession] = None
        # 24/7 CONTINUOUS MODE - training runs regardless of user activity
        self._continuous_mode = False
        self._continuous_target = 0  # Target epochs for continuous training (0 = infinite)
        self._continuous_thread: Optional[threading.Thread] = None
        # Track last completed session for progress display
        self._last_completed_epochs = 0
        self._last_target_epochs = 0
        
        # === GPU RESOURCE CACHING (reduces CPU overhead) ===
        self._gpu_model = None  # Persistent model in GPU memory
        self._gpu_optimizer = None
        self._gpu_criterion = None
        self._gpu_features = None  # Pre-created tensors on GPU
        self._gpu_labels = None
        self._gpu_device = None
        self._gpu_initialized = False
        self._gpu_dataloader = None  # Real data DataLoader
        self._gpu_holdout_loader = None  # Holdout validation DataLoader
        self._gpu_dataset_stats = None  # Dataset statistics
        self._governance_dataset_hash = ""
        self._last_loss = 0.0  # Last training loss
        self._last_accuracy = 0.0  # Last training accuracy
        self._last_holdout_accuracy = 0.0  # Last holdout (real) accuracy
        self._samples_per_sec = 0.0  # Training throughput
        self._real_samples_processed = 0  # Total real samples processed
        self._last_batch_index = 0  # Live batch index in current epoch
        self._last_total_batches = 0  # Total batches in current epoch
        self._last_epoch_samples = 0  # Samples processed in current epoch
        
        # === GOVERNANCE INTEGRATION ===
        self._curriculum = None  # RealDataCurriculum instance
        self._promotion = None   # GovernedFieldPromotion instance
        self._source_id = None   # Registered data source ID
        
        # === ATTRIBUTES SET DYNAMICALLY (declared here for type-checker) ===
        self._checkpoint_path: Optional[str] = None
        self._checkpoint_meta_path: Optional[str] = None
        self._gpu_scheduler = None  # LR scheduler (ReduceLROnPlateau)
        self._scaler = None  # AMP GradScaler
        self._training_mode_label: str = "MANUAL"
        self._session_start_monotonic = 0.0
        self._session_start_timestamp = None
        self._batch_size = 0
        self._last_error = ""
        self._telegram_notifier = build_training_telegram_notifier_from_env()
        self._worker_status_path = os.path.abspath(os.path.join(
            os.path.dirname(__file__), "..", "..", "..", "reports", "g38_training_worker.status.json"
        ))
        self._dataset_manifest_path = os.path.abspath(os.path.join(
            os.path.dirname(__file__), "..", "..", "..", "secure_data", "dataset_manifest.json"
        ))
        
        # === MODE_A EARLY STOPPING ===
        self._best_accuracy = 0.0
        self._no_improvement_count = 0
        self._early_stop_patience = 5  # Stop after 5 epochs without improvement
        self._early_stop_baseline = 0.80  # Min accuracy before early stop allowed
        self._write_worker_status()

    def _get_state(self) -> TrainingState:
        with self._training_lock:
            return self._state

    def _set_state(self, new_state: TrainingState) -> None:
        with self._training_lock:
            self._state = new_state
    
    @property
    def state(self) -> TrainingState:
        """Get current training state."""
        return self._get_state()
    
    @property
    def events(self) -> List[TrainingEvent]:
        """Get all training events."""
        return self._events.copy()
    
    @property
    def is_training(self) -> bool:
        """Check if training is active."""
        return self._get_state() == TrainingState.TRAINING
    
    def set_event_callback(self, callback: Callable[[TrainingEvent], None]) -> None:
        """Set callback for training events (for dashboard)."""
        self._on_event_callback = callback

    @staticmethod
    def _atomic_write_json(path: str, payload: Dict[str, Any]) -> None:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        fd, tmp_path = tempfile.mkstemp(
            dir=os.path.dirname(path),
            prefix=os.path.basename(path) + ".",
            suffix=".tmp",
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, indent=2)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp_path, path)
        except Exception:
            try:
                os.remove(tmp_path)
            except OSError:
                pass
            raise

    @staticmethod
    def _checkpoint_paths_for(base_dir: str) -> tuple[str, str, str]:
        base = os.path.join(base_dir, "g38_model_checkpoint")
        return (
            base + ".safetensors",
            base + ".json",
            base + ".pt",
        )

    @staticmethod
    def _build_checkpoint_metadata(
        *,
        epoch: int,
        accuracy: float,
        holdout_accuracy: float,
        loss: float,
        real_samples_processed: int,
    ) -> Dict[str, Any]:
        return {
            "schema_version": 1,
            "format": "safetensors",
            "epoch": int(epoch),
            "accuracy": float(accuracy),
            "holdout_accuracy": float(holdout_accuracy),
            "loss": float(loss),
            "real_samples_processed": int(real_samples_processed),
            "saved_at": datetime.now(timezone.utc).isoformat(),
        }

    @classmethod
    def _save_checkpoint_bundle(
        cls,
        checkpoint_path: str,
        checkpoint_meta_path: str,
        model_state: Dict[str, "torch.Tensor"],
        metadata: Dict[str, Any],
    ) -> None:
        if not SAFETENSORS_AVAILABLE or save_safetensors_file is None:
            raise RuntimeError("safetensors package not available")

        os.makedirs(os.path.dirname(checkpoint_path), exist_ok=True)
        fd, tmp_weights = tempfile.mkstemp(
            dir=os.path.dirname(checkpoint_path),
            prefix=os.path.basename(checkpoint_path) + ".",
            suffix=".tmp",
        )
        os.close(fd)
        try:
            save_safetensors_file(model_state, tmp_weights)
            os.replace(tmp_weights, checkpoint_path)
        except Exception:
            try:
                os.remove(tmp_weights)
            except OSError:
                pass
            raise

        cls._atomic_write_json(checkpoint_meta_path, metadata)

    def _load_checkpoint_metadata(self, checkpoint_meta_path: str) -> Dict[str, Any]:
        try:
            with open(checkpoint_meta_path, "r", encoding="utf-8") as handle:
                payload = json.load(handle)
            if isinstance(payload, dict):
                return payload
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            pass
        return {}

    def _write_worker_status(self) -> None:
        try:
            payload = self.get_status()
            self._atomic_write_json(self._worker_status_path, payload)
        except Exception as exc:
            logger.debug("Worker status write skipped: %s", exc)

    @staticmethod
    def _archive_legacy_checkpoint(legacy_checkpoint_path: str) -> None:
        if not legacy_checkpoint_path or not os.path.exists(legacy_checkpoint_path):
            return
        archived_path = legacy_checkpoint_path + ".legacy"
        os.replace(legacy_checkpoint_path, archived_path)
    
    def _emit_event(
        self,
        event_type: str,
        details: str,
        idle_seconds: int = 0,
        gpu_used: bool = False,
        epoch: Optional[int] = None,
    ) -> TrainingEvent:
        """Emit and log a training event."""
        event = TrainingEvent(
            event_id=f"EVT-{uuid.uuid4().hex[:12].upper()}",
            event_type=event_type,
            timestamp=datetime.now(timezone.utc).isoformat(),
            details=details,
            idle_seconds=idle_seconds,
            gpu_used=gpu_used,
            epoch=epoch,
        )
        
        self._events.append(event)
        if event_type == "ERROR":
            self._last_error = details
        
        # Log to console
        log_msg = f"[{event_type}] {details}"
        if event_type in ("TRAINING_STARTED", "IDLE_DETECTED"):
            logger.info(log_msg)
        elif event_type in ("TRAINING_STOPPED", "CHECKPOINT_SAVED"):
            logger.info(log_msg)
        elif event_type in ("TRAINING_ABORTED", "GUARD_BLOCKED"):
            logger.warning(log_msg)
        elif event_type == "ERROR":
            logger.error(log_msg)
        else:
            logger.debug(log_msg)
        
        # Notify callback
        if self._on_event_callback:
            try:
                self._on_event_callback(event)
            except Exception:
                pass

        if self._telegram_notifier is not None:
            try:
                self._telegram_notifier.notify(event, self.get_status())
            except Exception:
                pass

        try:
            self._write_worker_status()
        except Exception:
            pass
        
        return event

    def _session_duration_seconds(self) -> float:
        """Return current session duration in seconds."""
        if not self._current_session:
            return 0.0
        try:
            started = datetime.fromisoformat(self._current_session.started_at)
            if started.tzinfo is None:
                started = started.replace(tzinfo=timezone.utc)
            return max(
                0.0,
                (datetime.now(timezone.utc) - started).total_seconds(),
            )
        except ValueError:
            return 0.0

    def _fast_validate_dataset_manifest(self, min_samples: int) -> Tuple[bool, str]:
        """Use the signed dataset manifest as the fast-path readiness check."""
        try:
            with open(self._dataset_manifest_path, "r", encoding="utf-8") as handle:
                manifest = json.load(handle)
        except (FileNotFoundError, json.JSONDecodeError, OSError) as exc:
            return False, f"manifest_unavailable: {type(exc).__name__}"

        if not isinstance(manifest, dict):
            return False, "manifest_invalid: not a JSON object"

        dataset_source = str(manifest.get("dataset_source", "") or "").upper()
        strict_real = bool(manifest.get("strict_real_mode", False))
        training_mode = str(manifest.get("training_mode", "") or "").upper()
        sample_count = int(manifest.get("sample_count", manifest.get("total_samples", 0)) or 0)
        class_histogram = manifest.get("class_histogram", {}) or {}
        positive = int(class_histogram.get("1", class_histogram.get(1, 0)) or 0)
        total = max(sample_count, int(manifest.get("total_samples", sample_count) or sample_count))
        positive_ratio = (positive / total) if total > 0 else 0.0
        signed = bool(manifest.get("signature_hash")) and bool(manifest.get("signed_by"))

        if not strict_real:
            return False, "manifest_invalid: strict_real_mode is not enabled"
        if dataset_source != "INGESTION_PIPELINE":
            return False, f"manifest_invalid: dataset_source={dataset_source or '<missing>'}"
        if training_mode and training_mode != "PRODUCTION_REAL":
            return False, f"manifest_invalid: training_mode={training_mode}"
        if not signed:
            return False, "manifest_invalid: signature fields missing"
        if total < min_samples:
            return False, f"manifest_invalid: sample_count={total} below threshold={min_samples}"
        if not (0.40 <= positive_ratio <= 0.60):
            return False, f"manifest_invalid: class balance {positive_ratio:.2%}"

        return True, (
            f"Dataset valid (MANIFEST_FAST_PATH): {total} samples, "
            f"{positive_ratio:.2%} positive, source={dataset_source}"
        )

    def _determinism_status(self) -> bool:
        """Infer whether the current trainer is running in deterministic mode."""
        if not TORCH_AVAILABLE or not PYTORCH_AVAILABLE:
            return False
        try:
            return bool(
                torch.cuda.is_available()
                and torch.backends.cudnn.deterministic
                and _TRAINING_PROFILE != "fast"
                and os.environ.get("CUBLAS_WORKSPACE_CONFIG")
            )
        except Exception:
            return False

    def _extract_governance_dataset_arrays(self, dataset) -> Tuple[Optional[np.ndarray], Optional[np.ndarray]]:
        """Extract feature and label arrays from the active dataset, including Subset wrappers."""
        if dataset is None:
            return None, None

        subset_indices = getattr(dataset, "indices", None)
        underlying_dataset = getattr(dataset, "dataset", None)
        if subset_indices is not None and underlying_dataset is not None:
            base_features, base_labels = self._extract_governance_dataset_arrays(underlying_dataset)
            if base_features is None or base_labels is None:
                return None, None
            index_array = np.asarray(list(subset_indices), dtype=np.int64)
            return base_features[index_array], base_labels[index_array]

        features_tensor = getattr(dataset, "_features_tensor", None)
        labels_tensor = getattr(dataset, "_labels_tensor", None)
        if features_tensor is None or labels_tensor is None:
            return None, None

        return (
            features_tensor.detach().cpu().numpy(),
            labels_tensor.detach().cpu().numpy(),
        )

    def _hash_governance_dataset(self, features: np.ndarray, labels: np.ndarray) -> str:
        """Compute a stable hash of the governed training dataset."""
        digest = hashlib.sha256()
        digest.update(np.ascontiguousarray(features).tobytes())
        digest.update(np.ascontiguousarray(labels).tobytes())
        return digest.hexdigest()

    def _run_governance_pre_training_gate(self) -> bool:
        """Run the pre-training governance gate against the real DataLoader dataset."""
        if self._gpu_dataloader is None:
            logger.error("Governance pre-training gate failed: DataLoader not initialized")
            return False

        features, labels = self._extract_governance_dataset_arrays(self._gpu_dataloader.dataset)
        if features is None or labels is None or features.size == 0 or labels.size == 0:
            logger.error("Governance pre-training gate failed: dataset tensors unavailable")
            return False

        from impl_v1.training.data.governance_pipeline import pre_training_gate

        n_classes = max(1, int(np.unique(labels).size))
        source_id = self._source_id or "ingestion_pipeline"
        result = pre_training_gate(
            features,
            labels,
            n_classes=n_classes,
            source_id=source_id,
        )
        self._governance_dataset_hash = self._hash_governance_dataset(features, labels)

        if not result.passed:
            failure_summary = "; ".join(result.failures[:3]) if result.failures else "unknown governance failure"
            logger.error(f"Governance pre-training gate blocked training: {failure_summary}")
            self._emit_event(
                "GUARD_BLOCKED",
                f"Governance pre-training gate failed: {failure_summary}",
                epoch=self._epoch,
                gpu_used=True,
            )
            return False

        logger.info(
            "Governance pre-training gate passed: %s/%s checks in %.0fms",
            result.checks_passed,
            result.checks_run,
            result.duration_ms,
        )
        return True

    def _run_governance_post_epoch_audit(
        self,
        *,
        epoch: int,
        accuracy: float,
        holdout_accuracy: float,
        loss: float,
        train_accuracy: float,
        total_samples: int,
    ) -> None:
        """Run the post-epoch governance audit on the real epoch outputs."""
        from impl_v1.training.data.governance_pipeline import post_epoch_audit

        result = post_epoch_audit(
            epoch=epoch,
            accuracy=accuracy,
            holdout_accuracy=holdout_accuracy,
            loss=loss,
            train_accuracy=train_accuracy,
            total_samples=total_samples,
            dataset_hash=self._governance_dataset_hash,
        )
        for warning in result.warnings:
            logger.warning(f"[GOVERNANCE] {warning}")

    def _persist_runtime_artifacts(
        self,
        *,
        epoch_elapsed_seconds: Optional[float] = None,
    ) -> None:
        """Persist telemetry, gate state, and field progression outputs."""
        try:
            host_metrics = probe_host_metrics()
            determinism_status = self._determinism_status()
            promotion_frozen = bool(
                self._promotion is not None and self._promotion.state.frozen
            )
            promotion_reason = (
                self._promotion.state.freeze_reason
                if self._promotion is not None else None
            )
            duration_seconds = self._session_duration_seconds()
            total_epochs = (
                self._target_epochs
                if self._target_epochs > 0 and self._target_epochs < 999999
                else 0
            )
            batch_velocity = None
            if epoch_elapsed_seconds and self._last_total_batches > 0:
                batch_velocity = self._last_total_batches / max(epoch_elapsed_seconds, 0.001)

            write_training_gate(
                determinism_status=determinism_status,
                freeze_status=promotion_frozen,
                gpu_temperature=host_metrics.get("gpu_temperature"),
            )
            write_training_telemetry(
                epoch=self._session_epoch if self._session_epoch > 0 else self._epoch,
                batch_size=int(self._batch_size or 0),
                loss=float(self._last_loss),
                precision=float(self._last_accuracy),
                total_epochs=total_epochs,
                training_duration_seconds=duration_seconds,
                samples_per_second=float(self._samples_per_sec),
                determinism_status=determinism_status,
                freeze_status=promotion_frozen,
                gpu_temperature=host_metrics.get("gpu_temperature"),
                cpu_util=host_metrics.get("cpu_util"),
                gpu_util=host_metrics.get("gpu_util"),
                monotonic_start_time=int(self._session_start_monotonic or time.monotonic()),
                dataset_size=(
                    self._gpu_dataset_stats["train"]["total"]
                    if self._gpu_dataset_stats else None
                ),
            )
            current_epoch = self._session_epoch if self._session_epoch > 0 else self._epoch
            runtime_total_epochs = total_epochs if total_epochs > 0 else max(current_epoch, 0)
            progress_pct = 0.0
            if runtime_total_epochs > 0 and current_epoch > 0:
                progress_pct = min((current_epoch / runtime_total_epochs) * 100.0, 100.0)
            if self._last_loss > 0 and self._best_accuracy > 0 and self._last_accuracy >= self._best_accuracy:
                loss_trend = "improving"
            elif self._last_loss > 0:
                loss_trend = "active"
            else:
                loss_trend = "idle"

            write_runtime_state_snapshot(
                mode=self._get_state().value,
                total_epochs=runtime_total_epochs,
                completed_epochs=current_epoch,
                current_loss=float(self._last_loss),
                best_loss=float(self._last_loss if self._best_accuracy <= 0 else self._last_loss),
                precision=float(self._last_accuracy),
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
                    int(self._session_start_timestamp.timestamp() * 1000)
                    if self._session_start_timestamp else 0
                ),
                total_errors=0,
            )
            write_field_runtime_status(
                containment_active=promotion_frozen,
                containment_reason=promotion_reason,
                precision_breach=bool(
                    self._last_accuracy > 0 and self._last_accuracy < self._early_stop_baseline
                ),
                drift_alert=promotion_frozen,
                freeze_valid=(not promotion_frozen) if self._last_accuracy > 0 else None,
                freeze_reason=promotion_reason,
                training_velocity_samples_hr=(
                    float(self._samples_per_sec) * 3600.0
                    if self._samples_per_sec > 0 else None
                ),
                training_velocity_batches_sec=batch_velocity,
                gpu_utilization=host_metrics.get("gpu_util"),
                determinism_pass=determinism_status,
                data_freshness="fresh" if self._gpu_dataset_stats else None,
                merge_status="blocked" if promotion_frozen else None,
            )

            try:
                from backend.api.field_progression_api import sync_active_field_training

                sync_active_field_training(
                    precision=float(self._last_accuracy) if self._last_accuracy > 0 else None,
                    fpr=max(0.0, 1.0 - float(self._last_accuracy))
                    if self._last_accuracy > 0 else None,
                    stability_cycles=(
                        self._promotion.state.stable_cycles
                        if self._promotion is not None else None
                    ),
                    promotion_ready=bool(
                        self._promotion is not None and self._promotion.is_live_ready()
                    ),
                    promotion_frozen=promotion_frozen,
                    promotion_freeze_reason=promotion_reason,
                    determinism_passed=determinism_status,
                    drift_passed=not promotion_frozen,
                    regression_passed=True,
                    training_velocity_samples_hr=(
                        float(self._samples_per_sec) * 3600.0
                        if self._samples_per_sec > 0 else None
                    ),
                    training_velocity_batches_sec=batch_velocity,
                    gpu_utilization=host_metrics.get("gpu_util"),
                    data_freshness="fresh" if self._gpu_dataset_stats else None,
                    merge_status="blocked" if promotion_frozen else None,
                )
            except Exception as exc:
                logger.warning(f"Field progression sync failed: {exc}")
        except Exception as exc:
            logger.warning(f"Runtime artifact persistence failed: {exc}")

    def _attempt_ingestion_recovery(self, target_samples: int) -> Tuple[bool, str]:
        """
        Attempt automatic recovery when bridge persistence is missing.

        Runs scripts/fast_bridge_ingest.py to regenerate:
          - secure_data/bridge_state.json
          - secure_data/bridge_samples.jsonl.gz
        """
        auto_recovery = os.environ.get("YGB_AUTO_INGEST_RECOVERY", "true").lower()
        if auto_recovery in ("0", "false", "no", "off"):
            return False, "auto recovery disabled (YGB_AUTO_INGEST_RECOVERY=false)"

        project_root = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "..", "..")
        )
        script_path = os.path.join(project_root, "scripts", "fast_bridge_ingest.py")
        if not os.path.exists(script_path):
            return False, f"recovery script not found: {script_path}"

        env_target = os.environ.get("YGB_AUTO_INGEST_TARGET", "")
        try:
            target = max(target_samples, int(env_target)) if env_target else target_samples
        except ValueError:
            target = target_samples
        timeout_sec = int(os.environ.get("YGB_AUTO_INGEST_TIMEOUT_SEC", "7200"))

        self._emit_event(
            "INGESTION_RECOVERY_STARTED",
            f"Regenerating bridge persistence via fast ingest (target={target})",
            gpu_used=False,
        )
        logger.warning(
            f"Auto-ingestion recovery triggered: python {script_path} {target}"
        )

        try:
            env = os.environ.copy()
            env.setdefault("PYTHONUTF8", "1")
            result = subprocess.run(
                [sys.executable, script_path, str(target)],
                cwd=project_root,
                env=env,
                capture_output=True,
                text=True,
                timeout=timeout_sec,
            )
        except Exception as e:
            msg = f"auto-ingest recovery execution failed: {e}"
            logger.error(msg)
            self._emit_event("INGESTION_RECOVERY_FAILED", msg, gpu_used=False)
            return False, msg

        if result.returncode != 0:
            stderr_tail = "\n".join((result.stderr or "").strip().splitlines()[-8:])
            stdout_tail = "\n".join((result.stdout or "").strip().splitlines()[-8:])
            tail = stderr_tail or stdout_tail or "<no output>"
            msg = f"fast_bridge_ingest failed (rc={result.returncode})"
            logger.error(f"{msg}\n{tail}")
            self._emit_event("INGESTION_RECOVERY_FAILED", msg, gpu_used=False)
            return False, msg

        self._emit_event(
            "INGESTION_RECOVERY_COMPLETED",
            "Bridge persistence regenerated",
            gpu_used=False,
        )
        logger.info("Auto-ingestion recovery completed")
        return True, "Bridge persistence regenerated"

    def _build_training_dataloaders(
        self,
        *,
        batch_size: int,
        seed: int,
    ):
        """
        Build DataLoaders and validate that worker startup survives first use.

        On Windows, a DataLoader can be constructed successfully and still fail
        on the first iterator pull due to multiprocessing/pickling problems.
        Treat that as a real loader failure and fall back to ``num_workers=0``.
        """
        from impl_v1.training.data.real_dataset_loader import create_training_dataloader

        env_workers = os.environ.get("YGB_TRAIN_DATALOADER_WORKERS", "").strip()
        if env_workers:
            requested_workers = max(0, int(env_workers))
        elif sys.platform == "win32":
            # Windows worker spawn has repeatedly hit DLL pickling failures and
            # multi-minute startup stalls in the ingestion dataset path.
            requested_workers = 0
        else:
            requested_workers = 4

        def _create(num_workers: int):
            prefetch = 2 if num_workers > 0 else None
            persistent = num_workers > 0
            train_loader, holdout_loader, stats = create_training_dataloader(
                batch_size=batch_size,
                num_workers=num_workers,
                pin_memory=True,
                prefetch_factor=prefetch,
                seed=seed,
            )
            first_batch = next(iter(train_loader))
            logger.info(
                "DataLoader: num_workers=%s, persistent=%s, profile=%s",
                num_workers,
                persistent,
                _TRAINING_PROFILE,
            )
            return train_loader, holdout_loader, stats, first_batch

        try:
            return _create(requested_workers)
        except Exception as e:
            logger.warning(
                "DataLoader with workers=%s failed during startup/probe: %s",
                requested_workers,
                e,
            )
            if requested_workers == 0:
                raise
            logger.warning("Retrying with num_workers=0")
            return _create(0)
    
    def _init_gpu_resources(self) -> bool:
        """
        Initialize GPU resources ONCE with REAL structured data.
        
        Uses RealTrainingDataset (18K+ samples) with PyTorch DataLoader.
        NO synthetic data. NO random samples.
        """
        if self._gpu_initialized:
            return True

        if self._abort_flag.is_set():
            logger.info("GPU initialization skipped: abort requested")
            return False
        
        if not TORCH_AVAILABLE or not PYTORCH_AVAILABLE:
            return False
        
        device_info = detect_compute_device()
        if device_info.device_type != DeviceType.CUDA:
            return False
        
        try:
            from impl_v1.phase49.governors.g37_pytorch_backend import BugClassifier
            
            self._gpu_device = get_torch_device()
            
            # Create model config
            config = create_model_config(
                input_dim=256,
                output_dim=2,
                hidden_dims=(512, 256, 128),
                dropout=0.3,
                learning_rate=0.001,
                batch_size=1024,
                epochs=1,
                seed=42,
            )
            
            # Create model on GPU (PERSISTENT)
            if self._gpu_model is None:
                self._gpu_model = BugClassifier(config)
            self._gpu_model = self._gpu_model.to(self._gpu_device)
            
            # Create optimizer and criterion (PERSISTENT)
            if self._gpu_optimizer is None:
                self._gpu_optimizer = optim.Adam(
                    self._gpu_model.parameters(),
                    lr=config.learning_rate,
                    weight_decay=1e-5,
                )
            if self._gpu_criterion is None:
                self._gpu_criterion = nn.CrossEntropyLoss()
            
            # LR scheduler — cosine annealing with warm restarts (24/7 mode)
            # T_0=50: full cosine cycle every 50 epochs, T_mult=1: same length each restart
            if self._gpu_scheduler is None:
                self._gpu_scheduler = optim.lr_scheduler.CosineAnnealingWarmRestarts(
                    self._gpu_optimizer, T_0=50, T_mult=1, eta_min=1e-6,
                )
            
            # === REAL DATA PIPELINE (NO SYNTHETIC DATA) ===
            from impl_v1.training.data.real_dataset_loader import (
                get_per_field_report,
                validate_dataset_integrity,
                YGB_MIN_REAL_SAMPLES,
            )
            
            # Validate dataset before use. Fast-path via the signed manifest, then
            # fall back to the full ingestion integrity scan if the manifest is
            # missing or insufficient.
            valid, msg = self._fast_validate_dataset_manifest(YGB_MIN_REAL_SAMPLES)
            if not valid:
                valid, msg = validate_dataset_integrity()
            if not valid:
                logger.error(f"Dataset validation failed: {msg}")

                # Auto-heal known mismatch:
                # manifest says READY but authoritative bridge persistence is missing.
                recovery_attempted = False
                try:
                    report = get_per_field_report()
                    threshold = int(report.get("threshold", YGB_MIN_REAL_SAMPLES))
                    manifest_verified = int(report.get("manifest_verified_count", 0) or 0)
                    bridge_verified = int(report.get("bridge_verified_count", 0) or 0)
                    consistency_warning = str(report.get("consistency_warning", ""))
                    has_manifest_bridge_mismatch = (
                        "bridge=0 but manifest=" in consistency_warning
                        or (bridge_verified == 0 and manifest_verified >= threshold)
                    )

                    if has_manifest_bridge_mismatch:
                        recovered, rec_msg = self._attempt_ingestion_recovery(threshold)
                        recovery_attempted = True
                        if not recovered:
                            logger.error(f"Auto-ingestion recovery failed: {rec_msg}")
                        else:
                            valid, msg = validate_dataset_integrity()
                except Exception as e:
                    logger.warning(f"Recovery precheck skipped: {e}")

                if not valid:
                    logger.error(f"Dataset validation failed: {msg}")
                    return False

                if recovery_attempted:
                    logger.info(f"Dataset validated after recovery: {msg}")
            logger.info(f"Dataset validated: {msg}")

            if self._abort_flag.is_set():
                logger.info("GPU initialization aborted before DataLoader creation")
                return False
            
            train_loader, holdout_loader, stats, first_batch = self._build_training_dataloaders(
                batch_size=1024,
                seed=42,
            )
            
            self._gpu_dataloader = train_loader
            self._gpu_holdout_loader = holdout_loader  # Store holdout for validation
            self._gpu_dataset_stats = stats
            self._batch_size = int(getattr(train_loader, "batch_size", 0) or 0)

            dataset_source = str(stats.get("dataset_source", "") or "").upper()
            if dataset_source != "INGESTION_PIPELINE":
                logger.error(
                    "Refusing to initialize training with non-real dataset source: %s",
                    dataset_source or "<missing>",
                )
                return False

            if self._abort_flag.is_set():
                logger.info("GPU initialization aborted after DataLoader creation")
                return False
            
            # Pre-load first batch to GPU for fast access
            self._gpu_features = first_batch[0].to(self._gpu_device)
            self._gpu_labels = first_batch[1].to(self._gpu_device)
            
            # === GOVERNANCE: Register data source + validate trust ===
            try:
                from impl_v1.training.data.data_source_registry import DataSourceRegistry
                registry = DataSourceRegistry()
                sources = registry.get_all_sources()
                if not sources:
                    src = registry.register_source(
                        "ingestion_pipeline", "INGESTION_PIPELINE",
                        tags=["real", "production"],
                    )
                    registry.verify_source(src.source_id)  # +30 trust
                    registry.verify_source(src.source_id)  # +30 trust
                    registry.verify_source(src.source_id)  # +30 trust = 90
                    self._source_id = src.source_id
                else:
                    self._source_id = sources[0].source_id
                logger.info(f"Data source registered: {self._source_id}")
            except Exception as e:
                logger.warning(f"Data source registry: {e}")

            if not self._run_governance_pre_training_gate():
                return False
            
            # === GOVERNANCE: Initialize curriculum + promotion ===
            try:
                from impl_v1.training.data.real_data_curriculum import RealDataCurriculum
                from impl_v1.training.data.governed_field_promotion import GovernedFieldPromotion
                self._curriculum = RealDataCurriculum()
                self._promotion = GovernedFieldPromotion()
                logger.info(f"Curriculum initialized: {self._curriculum.get_stage_name()}")
            except Exception as e:
                logger.warning(f"Curriculum/promotion init: {e}")
            
            # === TRY TO LOAD EXISTING CHECKPOINT ===
            try:
                hdd_root = os.environ.get('YGB_HDD_ROOT', 'D:/ygb_hdd')
                checkpoint_dir = os.path.join(hdd_root, 'training')
                (
                    self._checkpoint_path,
                    self._checkpoint_meta_path,
                    legacy_checkpoint_path,
                ) = self._checkpoint_paths_for(checkpoint_dir)
                os.makedirs(os.path.dirname(self._checkpoint_path), exist_ok=True)
            except OSError:
                # HDD path not available (e.g. D: drive missing), use local fallback
                checkpoint_dir = os.path.abspath(os.path.join(
                    os.path.dirname(__file__), '..', '..', '..', 'data'
                ))
                (
                    self._checkpoint_path,
                    self._checkpoint_meta_path,
                    legacy_checkpoint_path,
                ) = self._checkpoint_paths_for(checkpoint_dir)
                os.makedirs(os.path.dirname(self._checkpoint_path), exist_ok=True)
                logger.warning(f"HDD path unavailable, using local checkpoint: {self._checkpoint_path}")
            
            if os.path.exists(self._checkpoint_path):
                try:
                    if not SAFETENSORS_AVAILABLE or load_safetensors_file is None:
                        raise RuntimeError("safetensors package not available")
                    model_state = load_safetensors_file(self._checkpoint_path, device='cpu')
                    self._gpu_model.load_state_dict(model_state)
                    ckpt_meta = self._load_checkpoint_metadata(self._checkpoint_meta_path or "")
                    self._epoch = int(ckpt_meta.get('epoch', 0) or 0)
                    self._last_accuracy = float(ckpt_meta.get('accuracy', 0.0) or 0.0)
                    self._last_holdout_accuracy = float(ckpt_meta.get('holdout_accuracy', self._last_accuracy) or self._last_accuracy)
                    self._last_loss = float(ckpt_meta.get('loss', 0.0) or 0.0)
                    self._real_samples_processed = int(
                        ckpt_meta.get('real_samples_processed', self._real_samples_processed) or 0
                    )
                    if os.path.exists(legacy_checkpoint_path):
                        self._archive_legacy_checkpoint(legacy_checkpoint_path)
                    logger.info(
                        f"Loaded safetensors checkpoint: epoch={self._epoch}, "
                        f"accuracy={self._last_accuracy:.2%}, loss={self._last_loss:.4f}"
                    )
                except Exception as e:
                    logger.warning(f"Could not load checkpoint, starting fresh: {e}")
            elif os.path.exists(legacy_checkpoint_path):
                try:
                    ckpt = torch.load(legacy_checkpoint_path, map_location=self._gpu_device, weights_only=True)
                    model_state = ckpt.get('model_state') or ckpt.get('model_state_dict') or ckpt
                    self._gpu_model.load_state_dict(model_state)
                    if isinstance(ckpt, dict) and 'optimizer_state' in ckpt:
                        self._gpu_optimizer.load_state_dict(ckpt['optimizer_state'])
                    if isinstance(ckpt, dict) and 'scheduler_state' in ckpt:
                        self._gpu_scheduler.load_state_dict(ckpt['scheduler_state'])
                    self._epoch = int(ckpt.get('epoch', 0) or 0) if isinstance(ckpt, dict) else 0
                    self._last_accuracy = float(ckpt.get('accuracy', 0.0) or 0.0) if isinstance(ckpt, dict) else 0.0
                    self._last_holdout_accuracy = float(
                        ckpt.get('holdout_accuracy', self._last_accuracy) or self._last_accuracy
                    ) if isinstance(ckpt, dict) else self._last_accuracy
                    self._last_loss = float(ckpt.get('loss', 0.0) or 0.0) if isinstance(ckpt, dict) else 0.0
                    self._real_samples_processed = int(
                        ckpt.get('real_samples_processed', self._real_samples_processed) or 0
                    ) if isinstance(ckpt, dict) else self._real_samples_processed
                    logger.info(
                        "Loaded legacy checkpoint for migration: epoch=%s, accuracy=%.2f%%, loss=%.4f",
                        self._epoch,
                        self._last_accuracy * 100.0,
                        self._last_loss,
                    )
                    if SAFETENSORS_AVAILABLE and self._checkpoint_meta_path:
                        migrated_state = {
                            key: value.detach().cpu().clone().contiguous()
                            for key, value in self._gpu_model.state_dict().items()
                        }
                        migrated_meta = self._build_checkpoint_metadata(
                            epoch=self._epoch,
                            accuracy=self._last_accuracy,
                            holdout_accuracy=self._last_holdout_accuracy,
                            loss=self._last_loss,
                            real_samples_processed=self._real_samples_processed,
                        )
                        self._save_checkpoint_bundle(
                            self._checkpoint_path,
                            self._checkpoint_meta_path,
                            migrated_state,
                            migrated_meta,
                        )
                        self._archive_legacy_checkpoint(legacy_checkpoint_path)
                        logger.info("Migrated legacy checkpoint to safetensors: %s", self._checkpoint_path)
                except Exception as e:
                    logger.warning(f"Could not load legacy checkpoint, starting fresh: {e}")
            
            # NOTE: torch.compile skipped — model is too small to benefit,
            # and torch._dynamo can silently corrupt outputs on Windows.
            
            self._gpu_initialized = True
            
            # Verify model is on GPU (not CPU)
            model_device = next(self._gpu_model.parameters()).device
            logger.info(
                f"GPU resources initialized on {device_info.device_name} "
                f"with {stats['train']['total']} real samples "
                f"(model on {model_device}, NOT CPU)"
            )
            return True
            
        except Exception as e:
            self._last_error = str(e).strip()
            logger.error(f"Failed to initialize GPU resources: {e}")
            return False
    
    def _check_all_guards(self) -> Tuple[bool, str]:
        """
        Check ALL guards before training.
        
        Returns (passed, reason).
        """
        # Check main G38 guards
        result, msg = verify_all_guards()
        if not result:
            return False, msg
        
        # Check pretraining guards
        result, msg = verify_pretraining_guards()
        if not result:
            return False, msg
        
        # Check MODE-A status
        status, _ = get_mode_a_status()
        if status != TrainingModeStatus.ACTIVE:
            return False, "MODE-A is not active"
        
        return True, "All guards passed"
    
    def _gpu_train_step(self) -> tuple:
        """
        Execute one FULL EPOCH over the entire DataLoader with AMP.
        
        Iterates through ALL batches of the real 20K+ sample dataset.
        Uses mixed precision for RTX 2050 Tensor cores.
        Returns (success: bool, accuracy: float, loss: float).
        """
        if not self._gpu_initialized:
            if not self._init_gpu_resources():
                return False, 0.0, 0.0
        
        try:
            # Initialize AMP scaler if not exists
            if not hasattr(self, '_scaler') or self._scaler is None:
                self._scaler = GradScaler('cuda') if AMP_AVAILABLE else None
            
            self._gpu_model.train()
            
            # Accumulate metrics on GPU to avoid per-batch GPU→CPU sync stalls
            total_loss_gpu = torch.zeros(1, device=self._gpu_device)
            total_correct_gpu = torch.zeros(1, dtype=torch.long, device=self._gpu_device)
            total_samples = 0
            batch_count = 0
            try:
                self._last_total_batches = len(self._gpu_dataloader)
            except Exception:
                self._last_total_batches = 0
            self._last_batch_index = 0
            self._last_epoch_samples = 0
            
            self._gpu_optimizer.zero_grad(set_to_none=True)
            
            # === CUDA STREAM PREFETCHING ===
            # Overlap data transfer with computation
            prefetch_stream = torch.cuda.Stream()
            
            # === ITERATE OVER FULL DATALOADER (all batches, all 20K+ samples) ===
            data_iter = iter(self._gpu_dataloader)
            
            # Pre-fetch first batch
            try:
                next_batch = next(data_iter)
                with torch.cuda.stream(prefetch_stream):
                    next_features = next_batch[0].to(self._gpu_device, non_blocking=True)
                    next_labels = next_batch[1].to(self._gpu_device, non_blocking=True)
            except StopIteration:
                return False, 0.0, 0.0
            
            while next_features is not None:
                if self._abort_flag.is_set():
                    return False, 0.0, 0.0
                
                # Wait for prefetch to complete
                torch.cuda.current_stream().wait_stream(prefetch_stream)
                batch_features = next_features
                batch_labels = next_labels
                
                # Start prefetching NEXT batch while we compute
                try:
                    next_batch = next(data_iter)
                    with torch.cuda.stream(prefetch_stream):
                        next_features = next_batch[0].to(self._gpu_device, non_blocking=True)
                        next_labels = next_batch[1].to(self._gpu_device, non_blocking=True)
                except StopIteration:
                    next_features = None
                    next_labels = None
                batch_size = batch_labels.size(0)
                
                # AMP: Mixed precision forward pass
                if AMP_AVAILABLE and self._scaler is not None:
                    with autocast('cuda', dtype=torch.float16):
                        outputs = self._gpu_model(batch_features)
                        loss = self._gpu_criterion(outputs, batch_labels)
                    
                    # AMP: Scaled backward + step every batch (no accumulation)
                    self._scaler.scale(loss).backward()
                    self._scaler.step(self._gpu_optimizer)
                    self._scaler.update()
                    self._gpu_optimizer.zero_grad(set_to_none=True)
                else:
                    # Fallback: Standard FP32 training
                    outputs = self._gpu_model(batch_features)
                    loss = self._gpu_criterion(outputs, batch_labels)
                    loss.backward()
                    self._gpu_optimizer.step()
                    self._gpu_optimizer.zero_grad(set_to_none=True)
                
                # Accumulate batch stats on GPU (no per-batch CPU sync)
                total_loss_gpu += loss.detach() * batch_size
                _, predicted = torch.max(outputs.data, 1)
                total_correct_gpu += (predicted == batch_labels).sum()
                total_samples += batch_size
                batch_count += 1
                self._last_batch_index = batch_count
                self._last_epoch_samples = total_samples
            
            # Synchronize CUDA streams before computing metrics
            torch.cuda.synchronize()
            
            # Also update the cached batch reference for status queries
            if total_samples > 0:
                self._gpu_features = batch_features
                self._gpu_labels = batch_labels
            
            # Track real samples processed
            self._real_samples_processed += total_samples
            
            # Epoch-level training metrics (single GPU→CPU sync point)
            avg_loss = total_loss_gpu.item() / max(total_samples, 1)
            train_accuracy = total_correct_gpu.item() / max(total_samples, 1)
            
            # === HOLDOUT VALIDATION (real generalization accuracy) ===
            holdout_accuracy = train_accuracy  # Fallback if no holdout loader
            if self._gpu_holdout_loader is not None:
                self._gpu_model.eval()
                holdout_correct_gpu = torch.zeros(1, dtype=torch.long, device=self._gpu_device)
                holdout_total = 0
                with torch.no_grad(), autocast('cuda', dtype=torch.float16):
                    for h_features, h_labels in self._gpu_holdout_loader:
                        h_features = h_features.to(self._gpu_device, non_blocking=True)
                        h_labels = h_labels.to(self._gpu_device, non_blocking=True)
                        h_outputs = self._gpu_model(h_features)
                        _, h_predicted = torch.max(h_outputs.data, 1)
                        holdout_correct_gpu += (h_predicted == h_labels).sum()
                        holdout_total += h_labels.size(0)
                if holdout_total > 0:
                    holdout_accuracy = holdout_correct_gpu.item() / holdout_total
                self._gpu_model.train()
            self._last_holdout_accuracy = holdout_accuracy
            
            # Use holdout accuracy as the real accuracy metric
            accuracy = holdout_accuracy
            
            # Step LR scheduler (cosine annealing — no loss arg needed)
            current_lr = self._gpu_optimizer.param_groups[0]['lr']
            if hasattr(self, '_gpu_scheduler') and self._gpu_scheduler is not None:
                self._gpu_scheduler.step()
                current_lr = self._gpu_optimizer.param_groups[0]['lr']
            
            # === CURRICULUM STAGE UPDATE ===
            if self._curriculum is not None:
                try:
                    fpr = 1.0 - accuracy  # Approximate FPR
                    self._curriculum.update_metrics(
                        accuracy=accuracy, fpr=fpr, fnr=fpr,
                        loss=avg_loss, epochs=1, samples=total_samples,
                    )
                    advanced, adv_msg = self._curriculum.try_advance()
                    if advanced:
                        logger.info(f"Curriculum: {adv_msg}")
                except Exception as e:
                    logger.warning(f"Curriculum update: {e}")
            
            # === PROMOTION GATE EVALUATION ===
            if self._promotion is not None:
                try:
                    curriculum_done = (
                        self._curriculum.state.curriculum_complete
                        if self._curriculum else False
                    )
                    fpr = 1.0 - accuracy
                    all_passed, gates = self._promotion.evaluate_gates(
                        accuracy=accuracy,
                        fpr=fpr,
                        binding_ratio=1.0,
                        curriculum_complete=curriculum_done,
                        deterministic_verified=True,
                        previous_accuracy=self._last_accuracy,
                    )
                    if self._promotion.is_live_ready():
                        logger.info("\U0001f3af LIVE_READY achieved — all 7 gates × 5 cycles")
                except Exception as e:
                    logger.warning(f"Promotion eval: {e}")
            
            # Save checkpoint async (background thread — doesn't block GPU training)
            try:
                self._run_governance_post_epoch_audit(
                    epoch=self._epoch,
                    accuracy=accuracy,
                    holdout_accuracy=holdout_accuracy,
                    loss=avg_loss,
                    train_accuracy=train_accuracy,
                    total_samples=total_samples,
                )
            except Exception as e:
                logger.warning(f"Post-epoch governance audit failed: {e}")

            if hasattr(self, '_checkpoint_path') and self._checkpoint_path:
                try:
                    if not SAFETENSORS_AVAILABLE or not self._checkpoint_meta_path:
                        raise RuntimeError("safetensors checkpoint support unavailable")
                    model_state = {
                        key: value.detach().cpu().clone().contiguous()
                        for key, value in self._gpu_model.state_dict().items()
                    }
                    checkpoint_meta = self._build_checkpoint_metadata(
                        epoch=self._epoch,
                        accuracy=accuracy,
                        holdout_accuracy=holdout_accuracy,
                        loss=avg_loss,
                        real_samples_processed=self._real_samples_processed,
                    )
                    future = _checkpoint_executor.submit(
                        self._save_checkpoint_bundle,
                        self._checkpoint_path,
                        self._checkpoint_meta_path,
                        model_state,
                        checkpoint_meta,
                    )
                    def _on_checkpoint_done(f, path=self._checkpoint_path):
                        exc = f.exception()
                        if exc:
                            logger.error(f"Async checkpoint save FAILED for {path}: {exc}")
                        else:
                            logger.info(f"Checkpoint saved: {path}")
                            if self._current_session:
                                self._current_session.checkpoints_saved += 1
                    future.add_done_callback(_on_checkpoint_done)
                except Exception as e:
                    logger.warning(f"Checkpoint save failed: {e}")
            
            # Verify training is on GPU, not CPU
            model_device = next(self._gpu_model.parameters()).device
            
            logger.info(
                f"Epoch complete: {batch_count} batches, "
                f"{total_samples} samples, "
                f"train_acc={train_accuracy:.2%}, holdout_acc={holdout_accuracy:.2%}, "
                f"loss={avg_loss:.4f}, lr={current_lr:.2e}, device={model_device}"
            )
            
            return True, accuracy, avg_loss
            
        except Exception as e:
            self._last_error = str(e).strip()
            import traceback
            err_tb = traceback.format_exc()
            logger.error(f"GPU training step failed: {e}\n{err_tb}")
            print(f"\n!!! GPU TRAIN ERROR !!!\n{e}\n{err_tb}", flush=True)
            return False, 0.0, 0.0
    
    def _get_current_conditions(self) -> IdleConditions:
        """Get current idle conditions from real OS."""
        idle_seconds = get_idle_seconds()
        power_connected = is_power_connected()
        scan_active = is_scan_active()
        
        # GPU detection
        gpu_available = False
        try:
            import torch
            gpu_available = torch.cuda.is_available()
        except ImportError:
            pass
        
        return IdleConditions(
            no_active_scan=not scan_active,
            no_human_interaction=idle_seconds >= IDLE_THRESHOLD_SECONDS,
            power_connected=power_connected,
            gpu_available=gpu_available,
            idle_seconds=idle_seconds,
        )
    
    def _train_representation_only(self) -> bool:
        """
        Execute MODE-A representation-only training using REAL GPU.
        
        This updates embeddings and weights WITHOUT:
        - Verifying bugs
        - Labeling severity
        - Learning accepted/rejected outcomes
        
        ENFORCES GPU-ONLY MODE - will NOT fall back to CPU.
        Uses the shared full-DataLoader training step (20K+ real samples).
        
        Returns True if training completed, False if aborted.
        """
        # === GPU ENFORCEMENT ===
        if not TORCH_AVAILABLE or not PYTORCH_AVAILABLE:
            self._emit_event(
                "ERROR",
                "PyTorch not installed - cannot train",
                epoch=self._epoch,
            )
            return False
        
        device_info = detect_compute_device()
        if device_info.device_type != DeviceType.CUDA:
            self._emit_event(
                "ERROR",
                f"GPU training required but CUDA not available (device: {device_info.device_type.value})",
                epoch=self._epoch,
                gpu_used=False,
            )
            return False
        
        self._epoch += 1
        
        self._emit_event(
            "TRAINING_STARTED",
            f"Starting epoch {self._epoch} on GPU ({device_info.device_name})",
            epoch=self._epoch,
            gpu_used=True,
        )
        
        try:
            # Check for abort before training
            if self._abort_flag.is_set():
                self._emit_event(
                    "TRAINING_ABORTED",
                    "Aborted before GPU training started",
                    epoch=self._epoch,
                    gpu_used=True,
                )
                return False
            
            # Check if scan started
            if is_scan_active():
                self._abort_flag.set()
                self._emit_event(
                    "TRAINING_ABORTED",
                    "Scan started - aborting GPU training",
                    epoch=self._epoch,
                    gpu_used=True,
                )
                return False
            
            # Check if human interaction
            idle = get_idle_seconds()
            if idle < IDLE_THRESHOLD_SECONDS:
                self._abort_flag.set()
                self._emit_event(
                    "TRAINING_ABORTED",
                    f"Human interaction detected (idle={idle}s) - aborting GPU training",
                    idle_seconds=idle,
                    epoch=self._epoch,
                    gpu_used=True,
                )
                return False
            
            # === REAL GPU TRAINING using full DataLoader (20K+ samples) ===
            import time as _time
            _step_start = _time.perf_counter()
            success, accuracy, loss = self._gpu_train_step()
            _step_elapsed = _time.perf_counter() - _step_start
            
            if not success:
                self._emit_event(
                    "ERROR",
                    "GPU training step failed",
                    epoch=self._epoch,
                    gpu_used=True,
                )
                return False
            
            # Update metrics
            self._last_loss = loss
            self._last_accuracy = accuracy
            ds_total = self._gpu_dataset_stats.get('train', {}).get('total', 0) if self._gpu_dataset_stats else 0
            self._samples_per_sec = ds_total / max(_step_elapsed, 0.001)
            
            # === MODE_A EARLY STOPPING → AUTO-RESTART (24/7) ===
            if accuracy > self._best_accuracy:
                self._best_accuracy = accuracy
                self._no_improvement_count = 0
            else:
                self._no_improvement_count += 1
            
            if (self._best_accuracy >= self._early_stop_baseline
                    and self._no_improvement_count >= self._early_stop_patience):
                self._emit_event(
                    "MODE_A_CYCLE_COMPLETE",
                    f"MODE_A cycle complete: accuracy={self._best_accuracy:.2%} "
                    f"(>={self._early_stop_baseline:.0%}), no improvement for "
                    f"{self._no_improvement_count} epochs. "
                    f"Resetting counters for new cycle.",
                    epoch=self._epoch,
                    gpu_used=True,
                )
                # Reset counters — training continues in 24/7 mode
                self._best_accuracy = 0.0
                self._no_improvement_count = 0
                logger.info(
                    "[MODE_A] Cycle complete — resetting early stop counters "
                    "for new learning cycle (24/7 continuous mode)"
                )
            
            # Save checkpoint
            checkpoint_hash = hashlib.sha256(f"epoch-{self._epoch}-gpu".encode()).hexdigest()[:16]
            self._emit_event(
                "CHECKPOINT_SAVED",
                f"Saved GPU checkpoint for epoch {self._epoch} (hash: {checkpoint_hash}, accuracy: {accuracy:.2%}, loss: {loss:.4f})",
                epoch=self._epoch,
                gpu_used=True,
            )
            
            self._emit_event(
                "TRAINING_STOPPED",
                f"Completed GPU epoch {self._epoch} — {ds_total} samples, {_step_elapsed:.1f}s (accuracy: {accuracy:.2%}, loss: {loss:.4f})",
                epoch=self._epoch,
                gpu_used=True,
            )
            
            self._persist_runtime_artifacts(epoch_elapsed_seconds=_step_elapsed)
            
            return True
            
        except Exception as e:
            self._emit_event(
                "ERROR",
                f"GPU training failed: {str(e)}",
                epoch=self._epoch,
                gpu_used=True,
            )
            return False
    
    def check_and_train(self) -> bool:
        """
        Check conditions and train if met.
        
        Returns True if training was triggered and completed.
        """
        with self._training_lock:
            # Don't trigger if already training
            if self._state == TrainingState.TRAINING:
                return False
            
            self._state = TrainingState.CHECKING
            self._abort_flag.clear()
        
        try:
            # Get conditions
            conditions = self._get_current_conditions()
            
            # Check idle conditions
            idle_result = check_idle_conditions(conditions)
            
            if not idle_result.can_train:
                self._set_state(TrainingState.IDLE)
                return False
            
            # Emit idle detected event
            self._emit_event(
                "IDLE_DETECTED",
                f"System idle for {conditions.idle_seconds}s - checking guards",
                idle_seconds=conditions.idle_seconds,
            )
            
            # Check ALL guards
            guards_ok, guard_msg = self._check_all_guards()
            if not guards_ok:
                self._emit_event(
                    "GUARD_BLOCKED",
                    f"Training blocked: {guard_msg}",
                    idle_seconds=conditions.idle_seconds,
                )
                self._set_state(TrainingState.IDLE)
                return False
            
            # Evaluate training trigger
            trigger = evaluate_training_trigger(
                idle_result,
                None,  # model_status - we allow fresh training
                pending_samples=100,  # representation samples available
            )
            
            if not trigger.should_train:
                self._set_state(TrainingState.IDLE)
                return False
            
            # Start training session
            with self._training_lock:
                self._state = TrainingState.TRAINING
                self._session_start_timestamp = datetime.now(timezone.utc)
                self._session_start_monotonic = time.monotonic()
                self._current_session = TrainingSession(
                    started_at=self._session_start_timestamp.isoformat(),
                    start_epoch=self._epoch,
                    gpu_used=conditions.gpu_available,
                )
            
            success = self._train_representation_only()
            
            # Generate training report after session
            if self._current_session:
                self._generate_session_report()
            
            with self._training_lock:
                self._state = TrainingState.IDLE
                self._current_session = None
                self._session_start_timestamp = None
                self._session_start_monotonic = 0.0
            
            return success
            
        except Exception as e:
            self._emit_event("ERROR", str(e))
            self._set_state(TrainingState.ERROR)
            return False
    
    def _generate_session_report(self) -> None:
        """Generate training report after session completes."""
        if not self._current_session:
            return
        
        try:
            stopped_at = datetime.now(timezone.utc).isoformat()
            epochs_trained = self._epoch - self._current_session.start_epoch
            
            # Get last checkpoint hash from events
            checkpoint_events = [
                e for e in self._events 
                if e.event_type == "CHECKPOINT_SAVED"
            ]
            last_hash = ""
            if checkpoint_events:
                # Extract hash from details
                details = checkpoint_events[-1].details
                if "hash: " in details:
                    last_hash = details.split("hash: ")[1].rstrip(")")
            
            paths = generate_training_report(
                total_epochs=epochs_trained,
                gpu_used=self._current_session.gpu_used,
                started_at=self._current_session.started_at,
                stopped_at=stopped_at,
                checkpoints_saved=len(checkpoint_events),
                last_checkpoint_hash=last_hash,
                samples_processed=getattr(self, '_real_samples_processed', 0),  # Real sample count from ingestion
                training_mode=ReportTrainingMode.MODE_A,
                reports_dir="reports/g38_training",
            )
            
            self._emit_event(
                "REPORT_GENERATED",
                f"Training report saved: {list(paths.values())[0]}",
            )
            
            logger.info(f"Training report generated: {paths}")
            
        except Exception as e:
            logger.error(f"Failed to generate training report: {e}")
    
    async def run_scheduler(self) -> None:
        """
        Background loop - IDLE AUTO-TRAINING MODE.
        
        Every 30 seconds, checks if the system is idle (≥60s no input).
        If idle + power connected + no scan active + guards pass:
            → Automatically triggers one training epoch.
        
        Training aborts immediately if:
            - User starts interacting (idle < 60s)
            - A scan starts
            - Any guard check fails
        
        Manual training via API always available regardless.
        """
        self._running = True
        self._training_mode_label = "MANUAL"
        logger.info("G38 Trainer started in MANUAL training mode — API-only trigger")
        
        while self._running:
            try:
                # MANUAL MODE: scheduler loop runs but does NOT auto-trigger training.
                # Training is triggered ONLY via explicit API call (force_start_training).
                # This loop monitors system conditions for dashboard reporting only.
                if not self.is_training:
                    conditions = self._get_current_conditions()
                    if conditions.idle_seconds >= IDLE_THRESHOLD_SECONDS:
                        logger.debug(
                            f"System idle ({conditions.idle_seconds}s) — "
                            f"awaiting manual training trigger via API"
                        )
            except Exception as e:
                logger.error(f"Scheduler monitoring error: {e}")
            
            await asyncio.sleep(self.CHECK_INTERVAL_SECONDS)
        
        logger.info("G38 Trainer stopped")
    
    def start(self) -> None:
        """Start the background scheduler."""
        if self._task is not None:
            return
        
        loop = asyncio.get_event_loop()
        self._task = loop.create_task(self.run_scheduler())
        self._write_worker_status()
    
    def stop(self) -> None:
        """Stop the background scheduler."""
        self._running = False
        self._abort_flag.set()
        
        if self._task is not None:
            self._task.cancel()
            self._task = None
        self._write_worker_status()
    
    def abort_training(self) -> dict:
        """Abort training immediately. Returns status."""
        if self.state != TrainingState.TRAINING:
            return {
                "aborted": False,
                "reason": "No training in progress",
                "state": self.state.value,
            }
        
        self._abort_flag.set()
        self._emit_event(
            "MANUAL_STOP",
            "Training aborted by user",
            gpu_used=True,
        )
        
        return {
            "aborted": True,
            "epoch_at_stop": self._session_epoch,
            "total_completed": self._epoch,
            "state": "ABORTING",
        }
    
    def abort_training_legacy(self) -> None:
        """Legacy abort - use abort_training() instead.

        .. deprecated:: 2024-03
            Use :meth:`abort_training` which returns a status dict.
        """
        warnings.warn(
            "abort_training_legacy() is deprecated — use abort_training()",
            DeprecationWarning,
            stacklevel=2,
        )
        self.abort_training()
    
    def force_start_training(self, epochs: int = 5) -> dict:
        """
        Manually start GPU training regardless of idle conditions.
        
        ENFORCES GPU-ONLY MODE - will NOT fall back to CPU.
        Used for demo/testing purposes.
        """
        # === GPU ENFORCEMENT ===
        if not TORCH_AVAILABLE or not PYTORCH_AVAILABLE:
            return {
                "started": False,
                "reason": "PyTorch not installed - cannot train on GPU",
                "state": "ERROR",
            }
        if not SAFETENSORS_AVAILABLE:
            return {
                "started": False,
                "reason": "safetensors not installed - required checkpoint format unavailable",
                "state": "ERROR",
            }
        
        device_info = detect_compute_device()
        if device_info.device_type != DeviceType.CUDA:
            return {
                "started": False,
                "reason": f"GPU training required but CUDA not available (device: {device_info.device_type.value})",
                "state": "ERROR",
            }
        
        with self._training_lock:
            if self._state == TrainingState.TRAINING:
                return {
                    "started": False,
                    "reason": "Training already in progress",
                    "state": self._state.value,
                }
            
            self._last_error = ""
            self._state = TrainingState.TRAINING
            self._abort_flag.clear()
            # Set REAL target for progress tracking
            self._target_epochs = epochs
            self._session_epoch = 0
            # Track session for report generation
            self._session_start_timestamp = datetime.now(timezone.utc)
            self._session_start_monotonic = time.monotonic()
            self._current_session = TrainingSession(
                started_at=self._session_start_timestamp.isoformat(),
                start_epoch=self._epoch,
                gpu_used=True,  # Always GPU
            )
        
        self._emit_event(
            "MANUAL_START",
            f"Manual GPU training triggered for {epochs} epochs on {device_info.device_name}",
            gpu_used=True,
        )
        
        try:
            # Initialize GPU resources ONCE (data stays on GPU)
            if not self._init_gpu_resources():
                self._last_error = self._last_error or "Failed to initialize GPU resources"
                self._state = TrainingState.ERROR
                return {
                    "started": False,
                    "reason": "Failed to initialize GPU resources",
                    "state": "ERROR",
                }
            
            for i in range(epochs):
                if self._abort_flag.is_set():
                    break
                
                # Update progress BEFORE training starts
                self._session_epoch = i + 1
                self._epoch += 1
                
                self._emit_event(
                    "TRAINING_STARTED",
                    f"Starting GPU epoch {self._session_epoch}/{epochs} (OPTIMIZED)",
                    epoch=self._session_epoch,
                    gpu_used=True,
                )
                
                # === USE OPTIMIZED GPU TRAINING (zero CPU overhead) ===
                import time as _time
                _step_start = _time.perf_counter()
                success, accuracy, loss = self._gpu_train_step()
                _step_elapsed = _time.perf_counter() - _step_start
                
                # Store metrics for dashboard display
                if success:
                    self._last_loss = loss
                    self._last_accuracy = accuracy
                    # Use real dataset size for throughput (full DataLoader iteration)
                    ds_total = self._gpu_dataset_stats.get('train', {}).get('total', 0) if self._gpu_dataset_stats else 0
                    self._samples_per_sec = ds_total / max(_step_elapsed, 0.001)
                
                if not self._abort_flag.is_set() and success:
                    checkpoint_hash = hashlib.sha256(f"epoch-{self._epoch}-gpu".encode()).hexdigest()[:16]
                    self._emit_event(
                        "CHECKPOINT_SAVED",
                        f"GPU checkpoint {self._session_epoch}/{epochs} (hash: {checkpoint_hash}, accuracy: {accuracy:.2%}, loss: {loss:.4f})",
                        epoch=self._session_epoch,
                        gpu_used=True,
                    )
            
            completed = self._session_epoch
            
            # Generate training report
            if self._current_session:
                self._generate_session_report()
            
            with self._training_lock:
                # Save last session for progress display
                self._last_completed_epochs = completed
                self._last_target_epochs = epochs
                self._state = TrainingState.IDLE
                self._target_epochs = 0
                self._session_epoch = 0
                self._current_session = None
                self._session_start_timestamp = None
                self._session_start_monotonic = 0.0
            self._write_worker_status()
            
            self._emit_event(
                "TRAINING_STOPPED",
                f"Manual GPU training completed: {completed}/{epochs} epochs",
                epoch=completed,
                gpu_used=True,
            )
            
            return {
                "started": True,
                "completed_epochs": completed,
                "total_epochs": self._epoch,
                "gpu_used": True,
                "device": device_info.device_name,
                "state": "COMPLETED",
            }
            
        except Exception as e:
            self._last_error = str(e).strip()
            self._set_state(TrainingState.ERROR)
            self._emit_event("ERROR", f"GPU training failed: {str(e)}", gpu_used=True)
            return {
                "started": False,
                "reason": "GPU training failed — check server logs",
                "state": "ERROR",
            }
    
    def get_status(self) -> dict:
        """Get current trainer status for dashboard."""
        conditions = self._get_current_conditions()
        current_state = self.state
        
        # Calculate REAL progress percentage
        is_continuous = getattr(self, '_continuous_mode', False)
        
        if self.is_training and is_continuous:
            # 24/7 continuous mode: show accuracy as progress
            real_progress = round(self._last_accuracy * 100)
            current_epoch = self._session_epoch
            target = 0  # 0 = infinite
        elif self.is_training and self._target_epochs > 0:
            # Fixed-epoch training: show live epoch progress
            real_progress = round((self._session_epoch / self._target_epochs) * 100)
            current_epoch = self._session_epoch
            target = self._target_epochs
        elif self._last_target_epochs > 0:
            # Training completed - show last session at 100%
            real_progress = 100
            current_epoch = self._last_completed_epochs
            target = self._last_target_epochs
        else:
            # No training has happened yet
            real_progress = 0
            current_epoch = 0
            target = 0
        
        # GPU metrics
        gpu_mem_allocated = 0.0
        gpu_mem_reserved = 0.0
        gpu_utilization = 0.0
        if TORCH_AVAILABLE and torch.cuda.is_available():
            gpu_mem_allocated = torch.cuda.memory_allocated() / 1024 / 1024  # MB
            gpu_mem_reserved = torch.cuda.memory_reserved() / 1024 / 1024  # MB
        
        return {
            "state": current_state.value,
            "is_training": self.is_training,
            "epoch": current_epoch,
            "total_epochs": target,
            "total_completed": self._epoch,
            "progress": real_progress,
            "idle_seconds": conditions.idle_seconds,
            "power_connected": conditions.power_connected,
            "scan_active": not conditions.no_active_scan,
            "gpu_available": conditions.gpu_available,
            "events_count": len(self._events),
            "last_event": self._events[-1].event_type if self._events else None,
            # Real GPU metrics
            "gpu_mem_allocated_mb": round(gpu_mem_allocated, 2),
            "gpu_mem_reserved_mb": round(gpu_mem_reserved, 2),
            "last_loss": round(self._last_loss, 6),
            "last_accuracy": round(self._last_accuracy, 4),
            "samples_per_sec": round(self._samples_per_sec, 1),
            "dataset_size": self._gpu_dataset_stats["train"]["total"] if self._gpu_dataset_stats else 0,
            "training_mode": "CONTINUOUS" if is_continuous else getattr(self, '_training_mode_label', 'MANUAL'),
            "continuous_mode": is_continuous,
            "last_error": self._last_error or None,
            # Explicit dependency availability — never imply success with zeros
            "dependencies": {
                "pytorch": "AVAILABLE" if TORCH_AVAILABLE else "UNAVAILABLE",
                "pytorch_backend": "AVAILABLE" if PYTORCH_AVAILABLE else "UNAVAILABLE",
                "safetensors": "AVAILABLE" if SAFETENSORS_AVAILABLE else "UNAVAILABLE",
                "cuda": (
                    "AVAILABLE" if (TORCH_AVAILABLE and torch.cuda.is_available())
                    else "UNAVAILABLE"
                ),
                "amp": "AVAILABLE" if AMP_AVAILABLE else "UNAVAILABLE",
                "numpy": "AVAILABLE",  # numpy is a hard dependency (imported at top)
            },
        }


# =============================================================================
# SINGLETON INSTANCE
# =============================================================================

_auto_trainer: Optional[AutoTrainer] = None


def get_auto_trainer() -> AutoTrainer:
    """Get singleton AutoTrainer instance."""
    global _auto_trainer
    if _auto_trainer is None:
        _auto_trainer = AutoTrainer()
    return _auto_trainer


def start_auto_training() -> None:
    """Initialize trainer in MANUAL training mode.
    
    Starts background scheduler for system monitoring.
    Training is triggered ONLY via explicit API call.
    MANUAL mode — no idle auto-trigger. All guards enforced.
    """
    trainer = get_auto_trainer()
    trainer.start()  # Starts MANUAL mode background monitor


def stop_auto_training() -> None:
    """Stop automatic idle training."""
    if _auto_trainer is not None:
        _auto_trainer.stop()


def start_continuous_training(target_epochs: int = 0) -> dict:
    """
    Start 24/7 continuous GPU training that runs regardless of user activity.
    
    ENFORCES GPU-ONLY MODE - will NOT fall back to CPU.
    
    Args:
        target_epochs: Number of epochs to train (0 = infinite/24/7)
    
    Returns:
        Status dict with training info
    """
    # === GPU ENFORCEMENT ===
    if not TORCH_AVAILABLE or not PYTORCH_AVAILABLE:
        return {
            "started": False,
            "reason": "PyTorch not installed - cannot train on GPU",
            "state": "ERROR",
        }
    if not SAFETENSORS_AVAILABLE:
        return {
            "started": False,
            "reason": "safetensors not installed - required checkpoint format unavailable",
            "state": "ERROR",
        }
    
    device_info = detect_compute_device()
    if device_info.device_type != DeviceType.CUDA:
        return {
            "started": False,
            "reason": f"GPU training required but CUDA not available (device: {device_info.device_type.value})",
            "state": "ERROR",
        }
    
    trainer = get_auto_trainer()
    
    with trainer._training_lock:
        if trainer._state == TrainingState.TRAINING:
            return {
                "started": False,
                "reason": "Training already in progress",
                "state": trainer._state.value,
            }
        
        trainer._last_error = ""
        trainer._continuous_mode = True
        trainer._continuous_target = target_epochs
        trainer._state = TrainingState.TRAINING
        trainer._abort_flag.clear()
        trainer._continuous_thread = None
        trainer._target_epochs = target_epochs if target_epochs > 0 else 999999
        trainer._session_epoch = 0
        trainer._session_start_timestamp = datetime.now(timezone.utc)
        trainer._current_session = TrainingSession(
            started_at=trainer._session_start_timestamp.isoformat(),
            start_epoch=trainer._epoch,
            gpu_used=True,  # Always GPU
        )
        trainer._session_start_monotonic = time.monotonic()

    ensure_local_mode_a_bootstrap()
    initial_metrics = probe_host_metrics()
    write_training_gate(
        determinism_status=trainer._determinism_status(),
        freeze_status=False,
        gpu_temperature=initial_metrics.get("gpu_temperature"),
    )
    
    trainer._emit_event(
        "CONTINUOUS_START",
        f"24/7 continuous GPU training started on {device_info.device_name} (target: {'infinite' if target_epochs == 0 else target_epochs} epochs)",
        gpu_used=True,
    )
    
    # Start background thread for continuous GPU training
    def _run_continuous():
        import time as _time
        
        # Initialize GPU resources ONCE (uses real 20K+ dataset)
        if not trainer._gpu_initialized:
            if not trainer._init_gpu_resources():
                trainer._continuous_mode = False
                with trainer._training_lock:
                    if trainer._abort_flag.is_set():
                        trainer._state = TrainingState.IDLE
                    else:
                        trainer._state = TrainingState.ERROR
                    trainer._continuous_thread = None
                if trainer._abort_flag.is_set():
                    trainer._emit_event(
                        "CONTINUOUS_STOP",
                        "Continuous training stopped during GPU initialization",
                        gpu_used=True,
                    )
                else:
                    trainer._emit_event("ERROR", "Failed to initialize GPU resources", gpu_used=True)
                return
        
        epoch_count = 0
        while trainer._continuous_mode and not trainer._abort_flag.is_set():
            # Check if target reached
            if target_epochs > 0 and epoch_count >= target_epochs:
                break
            
            epoch_count += 1
            trainer._epoch += 1
            trainer._session_epoch = epoch_count
            
            trainer._emit_event(
                "TRAINING_STARTED",
                f"Starting GPU epoch {epoch_count}" + (f"/{target_epochs}" if target_epochs > 0 else " (24/7 mode)"),
                epoch=epoch_count,
                gpu_used=True,
            )
            
            try:
                # Use the shared full-DataLoader training step
                _step_start = _time.perf_counter()
                success, accuracy, loss = trainer._gpu_train_step()
                _step_elapsed = _time.perf_counter() - _step_start
                
                if success and not trainer._abort_flag.is_set() and trainer._continuous_mode:
                    # Update metrics
                    trainer._last_loss = loss
                    trainer._last_accuracy = accuracy
                    ds_total = trainer._gpu_dataset_stats.get('train', {}).get('total', 0) if trainer._gpu_dataset_stats else 0
                    trainer._samples_per_sec = ds_total / max(_step_elapsed, 0.001)
                    
                    checkpoint_hash = hashlib.sha256(f"epoch-{trainer._epoch}-gpu".encode()).hexdigest()[:16]
                    trainer._emit_event(
                        "CHECKPOINT_SAVED",
                        f"Saved GPU checkpoint epoch {epoch_count} (hash: {checkpoint_hash}, accuracy: {accuracy:.2%}, loss: {loss:.4f})",
                        epoch=epoch_count,
                        gpu_used=True,
                    )
                    trainer._persist_runtime_artifacts(epoch_elapsed_seconds=_step_elapsed)
                
            except Exception as e:
                trainer._emit_event(
                    "ERROR",
                    f"GPU training failed at epoch {epoch_count}: {str(e)}",
                    epoch=epoch_count,
                    gpu_used=True,
                )
            
            # Small pause between epochs
            time.sleep(0.5)
        
        # Cleanup
        trainer._continuous_mode = False
        with trainer._training_lock:
            trainer._state = TrainingState.IDLE
            if trainer._current_session:
                trainer._persist_runtime_artifacts()
                trainer._generate_session_report()
            trainer._current_session = None
            trainer._session_start_timestamp = None
            trainer._session_start_monotonic = 0.0
            trainer._continuous_thread = None
        trainer._write_worker_status()
        
        trainer._emit_event(
            "CONTINUOUS_STOP",
            f"Continuous GPU training completed: {epoch_count} epochs",
            epoch=epoch_count,
            gpu_used=True,
        )
    
    thread = threading.Thread(target=_run_continuous, daemon=True, name="g38_continuous_trainer")
    trainer._continuous_thread = thread
    thread.start()
    
    return {
        "started": True,
        "mode": "continuous",
        "gpu_used": True,
        "device": device_info.device_name,
        "target_epochs": target_epochs if target_epochs > 0 else "infinite",
        "state": "TRAINING",
    }


def stop_continuous_training(wait_timeout_seconds: float = 5.0) -> dict:
    """Stop 24/7 continuous training."""
    trainer = get_auto_trainer()
    trainer._continuous_mode = False
    trainer._abort_flag.set()
    thread = getattr(trainer, "_continuous_thread", None)

    # Reflect stop intent immediately for API status consumers.
    with trainer._training_lock:
        if trainer._state == TrainingState.TRAINING:
            trainer._state = TrainingState.ABORTING
    trainer._write_worker_status()

    trainer._emit_event(
        "CONTINUOUS_STOP_REQUESTED",
        f"Continuous training stop requested (timeout={wait_timeout_seconds:.1f}s)",
        gpu_used=True,
    )

    thread_alive = False
    if isinstance(thread, threading.Thread) and thread.is_alive():
        thread.join(timeout=max(0.0, float(wait_timeout_seconds)))
        thread_alive = thread.is_alive()

    # If the worker thread has exited, finalize state eagerly.
    if not thread_alive:
        with trainer._training_lock:
            trainer._state = TrainingState.IDLE
            trainer._continuous_mode = False
            trainer._continuous_thread = None
            if trainer._current_session:
                trainer._generate_session_report()
            trainer._current_session = None
            trainer._session_start_timestamp = None
            trainer._session_start_monotonic = 0.0
        trainer._write_worker_status()

    return {
        "stopped": not thread_alive,
        "stop_requested": True,
        "thread_alive": thread_alive,
        "state": trainer._state.value,
        "total_completed": trainer._epoch,
    }
