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
import os
import threading
import time
import logging
import uuid
import hashlib
import json
import shutil
from datetime import datetime, timezone
from dataclasses import dataclass
from typing import Optional, Callable, List, Tuple, Any
from enum import Enum
from pathlib import Path

# Import idle detection
from .idle_detector import (
    get_idle_seconds,
    is_power_connected,
    is_scan_active,
)

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

try:
    from api.distributed_runtime import DistributedClusterCoordinator
except ImportError:  # pragma: no cover
    DistributedClusterCoordinator = None  # type: ignore

# Try importing torch for GPU enforcement
try:
    import torch
    import torch.nn as nn
    import torch.optim as optim
    from torch.cuda.amp import autocast, GradScaler
    import torch.distributed as dist

    TORCH_AVAILABLE = True
    AMP_AVAILABLE = True
except ImportError:
    TORCH_AVAILABLE = False
    AMP_AVAILABLE = False
    dist = None

try:
    from torch.distributed.fsdp import FullyShardedDataParallel as FSDP
    from torch.distributed.fsdp import StateDictType as FSDPStateDictType
    from torch.distributed.fsdp import FullStateDictConfig as FSDPFullStateDictConfig
    from torch.distributed.fsdp import ShardingStrategy

    FSDP_AVAILABLE = True
except ImportError:
    FSDP = None
    FSDPStateDictType = None
    FSDPFullStateDictConfig = None
    ShardingStrategy = None
    FSDP_AVAILABLE = False

try:
    from safetensors.torch import save_file as save_safetensors_file

    SAFETENSORS_AVAILABLE = True
except ImportError:
    SAFETENSORS_AVAILABLE = False
    save_safetensors_file = None

try:
    import psutil  # type: ignore

    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False
    psutil = None

# Enforce deterministic mode for reproducibility
if TORCH_AVAILABLE:
    torch.backends.cudnn.benchmark = False
    torch.backends.cudnn.deterministic = True
    try:
        torch.use_deterministic_algorithms(True)
    except Exception:
        pass  # Not all operations support deterministic mode


# =============================================================================
# LOGGING
# =============================================================================

logger = logging.getLogger("g38.auto_trainer")
logger.setLevel(logging.INFO)

if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(
        logging.Formatter("%(asctime)s [G38] %(levelname)s: %(message)s")
    )
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
        self._training_lock = threading.Lock()
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
        self._continuous_target = (
            0  # Target epochs for continuous training (0 = infinite)
        )
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
        self._gpu_holdout_loader = None
        self._gpu_dataset_stats = None  # Dataset statistics
        self._last_loss = 0.0  # Last training loss
        self._last_accuracy = 0.0  # Last training accuracy
        self._samples_per_sec = 0.0  # Training throughput
        self._paused_for_resources = False
        self._max_cpu_ratio = float(os.getenv("YGB_TRAINING_MAX_CPU_RATIO", "0.9"))
        self._max_memory_ratio = float(
            os.getenv("YGB_TRAINING_MAX_MEMORY_RATIO", "0.9")
        )
        self._max_gpu_ratio = float(os.getenv("YGB_TRAINING_MAX_GPU_RATIO", "0.9"))
        self._checkpoint_dir = Path(
            os.getenv("YGB_CHECKPOINT_DIR", "reports/g38_training/checkpoints")
        )
        sync_dirs = os.getenv("YGB_CHECKPOINT_SYNC_DIRS", "")
        self._checkpoint_sync_dirs = [
            Path(item) for item in sync_dirs.split(os.pathsep) if item.strip()
        ]
        self._last_checkpoint_tensors = None
        self._last_checkpoint_path = ""
        self._checkpoint_interval = max(
            1, int(os.getenv("YGB_CHECKPOINT_INTERVAL", "5"))
        )
        self._cluster = (
            DistributedClusterCoordinator() if DistributedClusterCoordinator else None
        )
        self._checkpoint_version = 0
        self._distributed_rank = 0
        self._distributed_world_size = 1
        self._fsdp_enabled = False

    @property
    def state(self) -> TrainingState:
        """Get current training state."""
        return self._state

    def _distributed_enabled(self) -> bool:
        return bool(
            TORCH_AVAILABLE
            and dist is not None
            and dist.is_available()
            and dist.is_initialized()
            and dist.get_world_size() > 1
        )

    def _distributed_barrier(self) -> None:
        if self._distributed_enabled():
            dist.barrier()

    def _initialize_cluster_state(self) -> None:
        if self._cluster is None:
            return
        try:
            asyncio.run(self._cluster.startup())
        except RuntimeError:
            loop = asyncio.new_event_loop()
            try:
                loop.run_until_complete(self._cluster.startup())
            finally:
                loop.close()

    @property
    def events(self) -> List[TrainingEvent]:
        """Get all training events."""
        return self._events.copy()

    @property
    def is_training(self) -> bool:
        """Check if training is active."""
        return self._state == TrainingState.TRAINING

    def set_event_callback(self, callback: Callable[[TrainingEvent], None]) -> None:
        """Set callback for training events (for dashboard)."""
        self._on_event_callback = callback

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
        if len(self._events) > 1000:
            self._events = self._events[-500:]

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

        return event

    def _init_gpu_resources(self) -> bool:
        """
        Initialize GPU resources ONCE with REAL structured data.

        Uses RealTrainingDataset (18K+ samples) with PyTorch DataLoader.
        NO synthetic data. NO random samples.
        """
        if self._gpu_initialized:
            return True

        if not TORCH_AVAILABLE or not PYTORCH_AVAILABLE:
            return False

        device_info = detect_compute_device()
        if device_info.device_type != DeviceType.CUDA:
            return False

        try:
            from impl_v1.phase49.governors.g37_pytorch_backend import BugClassifier

            self._gpu_device = get_torch_device()
            self._initialize_cluster_state()
            self._distributed_rank = (
                dist.get_rank() if self._distributed_enabled() else 0
            )
            self._distributed_world_size = (
                dist.get_world_size() if self._distributed_enabled() else 1
            )

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
            self._gpu_model = BugClassifier(config)
            self._gpu_model = self._gpu_model.to(self._gpu_device)
            self._gpu_model = self._maybe_wrap_sharded_model(self._gpu_model)

            # Create optimizer and criterion (PERSISTENT)
            self._gpu_optimizer = optim.Adam(
                self._gpu_model.parameters(), lr=config.learning_rate
            )
            self._gpu_criterion = nn.CrossEntropyLoss()

            # === REAL DATA PIPELINE (NO SYNTHETIC DATA) ===
            from impl_v1.training.data.real_dataset_loader import (
                create_training_dataloader,
                validate_dataset_integrity,
            )

            # Validate dataset before use
            valid, msg = validate_dataset_integrity()
            if not valid:
                logger.error(f"Dataset validation failed: {msg}")
                return False
            logger.info(f"Dataset validated: {msg}")

            # Create optimized DataLoader (pin_memory, workers)
            train_loader, holdout_loader, stats = create_training_dataloader(
                batch_size=1024,
                num_workers=4,
                pin_memory=True,
                prefetch_factor=2,
                seed=42,
            )

            self._gpu_dataloader = train_loader
            self._gpu_holdout_loader = holdout_loader
            self._gpu_dataset_stats = stats

            # Pre-load first batch to GPU for fast access
            first_batch = next(iter(train_loader))
            self._gpu_features = first_batch[0].to(self._gpu_device)
            self._gpu_labels = first_batch[1].to(self._gpu_device)
            self._restore_checkpoint_if_available()

            self._gpu_initialized = True
            logger.info(
                f"GPU resources initialized on {device_info.device_name} "
                f"with {stats['train']['total']} real samples"
            )
            return True

        except Exception as e:
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

    def _checkpoint_hash(self) -> str:
        """Hash the real model state for checkpoint identity."""
        if not self._gpu_model or not TORCH_AVAILABLE:
            return hashlib.sha256(f"epoch-{self._epoch}".encode()).hexdigest()[:16]
        import io

        buffer = io.BytesIO()
        state_dict = self._state_dict_for_save()
        torch.save(state_dict, buffer)
        return hashlib.sha256(buffer.getvalue()).hexdigest()[:16]

    def _state_dict_for_save(self) -> dict:
        if self._gpu_model is None:
            return {}
        if (
            self._fsdp_enabled
            and FSDP is not None
            and FSDPStateDictType is not None
            and FSDPFullStateDictConfig is not None
        ):
            config = FSDPFullStateDictConfig(offload_to_cpu=True, rank0_only=True)
            with FSDP.state_dict_type(
                self._gpu_model, FSDPStateDictType.FULL_STATE_DICT, config
            ):
                state = self._gpu_model.state_dict()
        else:
            state = self._gpu_model.state_dict()
        return {key: tensor.detach().to("cpu") for key, tensor in state.items()}

    def _maybe_wrap_sharded_model(self, model):
        self._distributed_rank = dist.get_rank() if self._distributed_enabled() else 0
        self._distributed_world_size = (
            dist.get_world_size() if self._distributed_enabled() else 1
        )
        if (
            self._distributed_world_size > 1
            and self._gpu_device is not None
            and FSDP_AVAILABLE
            and FSDP is not None
            and ShardingStrategy is not None
        ):
            self._fsdp_enabled = True
            return FSDP(
                model,
                sharding_strategy=ShardingStrategy.FULL_SHARD,
                device_id=self._gpu_device,
                use_orig_params=True,
            )
        self._fsdp_enabled = False
        return model

    def _evaluate_holdout_accuracy(self) -> float:
        """Evaluate current model on the holdout loader."""
        if not self._gpu_holdout_loader or not self._gpu_model:
            return self._last_accuracy

        self._gpu_model.eval()
        correct = 0
        total = 0
        with torch.no_grad():
            for batch_features, batch_labels in self._gpu_holdout_loader:
                batch_features = batch_features.to(self._gpu_device, non_blocking=True)
                batch_labels = batch_labels.to(self._gpu_device, non_blocking=True)
                outputs = self._gpu_model(batch_features)
                _, predicted = torch.max(outputs.data, 1)
                correct += (predicted == batch_labels).sum().item()
                total += batch_labels.size(0)
        return correct / total if total > 0 else 0.0

    def _current_pressure(self) -> tuple[float, float, float]:
        """Return CPU, memory, and GPU pressure ratios."""
        cpu_ratio = 0.0
        memory_ratio = 0.0
        gpu_ratio = 0.0

        if PSUTIL_AVAILABLE and psutil is not None:
            cpu_ratio = min(psutil.cpu_percent(interval=None) / 100.0, 1.0)
            memory_ratio = min(psutil.virtual_memory().percent / 100.0, 1.0)
        elif hasattr(os, "getloadavg"):
            cpu_ratio = min((os.getloadavg()[0] / max(os.cpu_count() or 1, 1)), 1.0)

        if TORCH_AVAILABLE and torch.cuda.is_available():
            reserved = float(torch.cuda.memory_reserved())
            total = float(torch.cuda.get_device_properties(0).total_memory)
            if total > 0:
                gpu_ratio = min(reserved / total, 1.0)

        return cpu_ratio, memory_ratio, gpu_ratio

    def _adaptive_micro_batch_size(self, batch_size: int) -> int:
        """Reduce effective batch size under pressure."""
        cpu_ratio, memory_ratio, gpu_ratio = self._current_pressure()
        pressure = max(
            cpu_ratio / max(self._max_cpu_ratio, 0.01),
            memory_ratio / max(self._max_memory_ratio, 0.01),
            gpu_ratio / max(self._max_gpu_ratio, 0.01),
        )
        if pressure >= 1.1:
            return max(64, batch_size // 4)
        if pressure >= 0.9:
            return max(128, batch_size // 2)
        return batch_size

    def _wait_for_resource_window(self) -> bool:
        """Pause training until resource pressure drops or abort is requested."""
        cpu_ratio, memory_ratio, gpu_ratio = self._current_pressure()
        overloaded = (
            cpu_ratio >= self._max_cpu_ratio
            or memory_ratio >= self._max_memory_ratio
            or gpu_ratio >= self._max_gpu_ratio
        )
        if not overloaded:
            if self._paused_for_resources:
                self._paused_for_resources = False
                self._emit_event(
                    "TRAINING_RESUMED", "Resource pressure normalized", gpu_used=True
                )
            return True

        if not self._paused_for_resources:
            self._paused_for_resources = True
            self._emit_event(
                "TRAINING_PAUSED",
                f"Resource governor pause (cpu={cpu_ratio:.2f}, mem={memory_ratio:.2f}, gpu={gpu_ratio:.2f})",
                gpu_used=True,
            )

        wait_deadline = time.time() + 5.0
        while time.time() < wait_deadline and not self._abort_flag.is_set():
            self._abort_flag.wait(0.25)
            cpu_ratio, memory_ratio, gpu_ratio = self._current_pressure()
            if (
                cpu_ratio < self._max_cpu_ratio
                and memory_ratio < self._max_memory_ratio
                and gpu_ratio < self._max_gpu_ratio
            ):
                self._paused_for_resources = False
                self._emit_event(
                    "TRAINING_RESUMED", "Resource pressure normalized", gpu_used=True
                )
                return True
        return not self._abort_flag.is_set()

    def _save_checkpoint_artifacts(
        self, accuracy: float, loss: float
    ) -> tuple[str, str]:
        """Persist SafeTensors checkpoints, delta manifests, and sync artifacts."""
        self._initialize_cluster_state()
        self._checkpoint_dir.mkdir(parents=True, exist_ok=True)
        checkpoint_hash = self._checkpoint_hash()
        checkpoint_name = f"g38_epoch_{self._epoch:06d}"
        checkpoint_id = f"G38-{self._epoch:06d}"
        metadata_path = self._checkpoint_dir / f"{checkpoint_name}.json"
        weights_path = self._checkpoint_dir / f"{checkpoint_name}.safetensors"
        delta_path = self._checkpoint_dir / f"{checkpoint_name}.delta.json"

        state_cpu = self._state_dict_for_save()

        if self._cluster is not None:
            barrier_payload = {
                "node_id": self._cluster.node_id,
                "checkpoint_id": checkpoint_id,
                "epoch": self._epoch,
                "rank": self._distributed_rank,
                "world_size": self._distributed_world_size,
                "checkpoint_hash": checkpoint_hash,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
            try:
                asyncio.run(
                    self._cluster.begin_checkpoint_barrier(
                        checkpoint_id, barrier_payload
                    )
                )
            except RuntimeError:
                loop = asyncio.new_event_loop()
                try:
                    loop.run_until_complete(
                        self._cluster.begin_checkpoint_barrier(
                            checkpoint_id, barrier_payload
                        )
                    )
                finally:
                    loop.close()

        self._distributed_barrier()

        if self._distributed_enabled() and self._distributed_rank != 0:
            return checkpoint_hash, str(self._checkpoint_dir / "latest_checkpoint.json")

        if SAFETENSORS_AVAILABLE and save_safetensors_file is not None and state_cpu:
            save_safetensors_file(state_cpu, str(weights_path))
        elif state_cpu:
            torch.save(state_cpu, str(weights_path.with_suffix(".pt")))
            weights_path = weights_path.with_suffix(".pt")

        delta_manifest: dict[str, Any] = {"changed_tensors": []}
        if self._last_checkpoint_tensors is None:
            delta_manifest["changed_tensors"] = list(state_cpu.keys())
        else:
            for key, tensor in state_cpu.items():
                previous = self._last_checkpoint_tensors.get(key)
                if previous is None or not torch.equal(previous, tensor):
                    delta_manifest["changed_tensors"].append(key)
        delta_manifest["base_checkpoint"] = self._last_checkpoint_path
        delta_manifest["checkpoint_hash"] = checkpoint_hash
        delta_manifest["epoch"] = self._epoch
        delta_manifest["accuracy"] = accuracy
        delta_manifest["loss"] = loss
        delta_manifest["created_at"] = datetime.now(timezone.utc).isoformat()

        metadata = {
            "checkpoint_hash": checkpoint_hash,
            "epoch": self._epoch,
            "accuracy": accuracy,
            "loss": loss,
            "weights_path": str(weights_path),
            "delta_path": str(delta_path),
            "safetensors": str(weights_path).endswith(".safetensors"),
        }

        metadata_tmp = metadata_path.with_suffix(".json.tmp")
        delta_tmp = delta_path.with_suffix(".json.tmp")
        metadata_tmp.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
        delta_tmp.write_text(json.dumps(delta_manifest, indent=2), encoding="utf-8")
        metadata_tmp.replace(metadata_path)
        delta_tmp.replace(delta_path)

        latest_manifest = self._checkpoint_dir / "latest_checkpoint.json"
        latest_tmp = latest_manifest.with_suffix(".json.tmp")
        latest_tmp.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
        latest_tmp.replace(latest_manifest)

        storage_manifest = None
        if self._cluster is not None:
            try:
                storage_manifest = asyncio.run(
                    self._cluster.storage.store_file(
                        namespace="checkpoint",
                        file_path=weights_path,
                    )
                )
            except RuntimeError:
                loop = asyncio.new_event_loop()
                try:
                    storage_manifest = loop.run_until_complete(
                        self._cluster.storage.store_file(
                            namespace="checkpoint",
                            file_path=weights_path,
                        )
                    )
                finally:
                    loop.close()

        for sync_dir in self._checkpoint_sync_dirs:
            try:
                sync_dir.mkdir(parents=True, exist_ok=True)
                shutil.copy2(metadata_path, sync_dir / metadata_path.name)
                shutil.copy2(delta_path, sync_dir / delta_path.name)
                if weights_path.exists():
                    shutil.copy2(weights_path, sync_dir / weights_path.name)
            except Exception as exc:
                self._emit_event(
                    "CHECKPOINT_SYNC_WARNING",
                    f"Checkpoint sync failed for {sync_dir}: {exc}",
                )

        self._last_checkpoint_tensors = state_cpu
        self._last_checkpoint_path = str(weights_path)
        self._checkpoint_version += 1

        if self._cluster is not None:
            manifest = {
                "epoch": self._epoch,
                "checkpoint_hash": checkpoint_hash,
                "accuracy": accuracy,
                "loss": loss,
                "weights_path": str(weights_path),
                "tiered_storage": storage_manifest,
            }
            try:
                committed = asyncio.run(
                    self._cluster.commit_checkpoint_consensus(
                        checkpoint_id,
                        version=self._checkpoint_version,
                        manifest=manifest,
                    )
                )
            except RuntimeError:
                loop = asyncio.new_event_loop()
                try:
                    committed = loop.run_until_complete(
                        self._cluster.commit_checkpoint_consensus(
                            checkpoint_id,
                            version=self._checkpoint_version,
                            manifest=manifest,
                        )
                    )
                finally:
                    loop.close()
            except Exception:
                try:
                    committed = asyncio.run(self._cluster.rollback_manifest())
                except RuntimeError:
                    loop = asyncio.new_event_loop()
                    try:
                        committed = loop.run_until_complete(
                            self._cluster.rollback_manifest()
                        )
                    finally:
                        loop.close()
            metadata["cluster_commit"] = committed
            metadata_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")

        return checkpoint_hash, str(weights_path)

    def _should_checkpoint(self, session_epoch: int, target_epochs: int = 0) -> bool:
        if session_epoch <= 0:
            return False
        if session_epoch == 1:
            return True
        if target_epochs > 0 and session_epoch >= target_epochs:
            return True
        return session_epoch % self._checkpoint_interval == 0

    def _restore_checkpoint_if_available(self) -> None:
        latest_manifest = self._checkpoint_dir / "latest_checkpoint.json"
        if self._cluster is not None:
            self._initialize_cluster_state()
            try:
                checkpoint_info = asyncio.run(
                    self._cluster.latest_consistent_checkpoint()
                )
            except RuntimeError:
                loop = asyncio.new_event_loop()
                try:
                    checkpoint_info = loop.run_until_complete(
                        self._cluster.latest_consistent_checkpoint()
                    )
                finally:
                    loop.close()
            manifest = (
                checkpoint_info.get("manifest")
                if isinstance(checkpoint_info, dict)
                else None
            )
            if isinstance(manifest, dict) and manifest.get("weights_path"):
                latest_manifest = Path(str(manifest.get("weights_path"))).with_suffix(
                    ".json"
                )
        if (
            not latest_manifest.exists()
            or not TORCH_AVAILABLE
            or self._gpu_model is None
        ):
            return
        try:
            metadata = json.loads(latest_manifest.read_text(encoding="utf-8"))
            weights_path = Path(metadata.get("weights_path", ""))
            if not weights_path.exists():
                return
            if weights_path.suffix == ".safetensors" and SAFETENSORS_AVAILABLE:
                from safetensors.torch import load_file as load_safetensors_file

                state_dict = load_safetensors_file(
                    str(weights_path), device=str(self._gpu_device)
                )
            else:
                state_dict = torch.load(
                    str(weights_path), map_location=self._gpu_device
                )
            self._gpu_model.load_state_dict(state_dict)
            self._last_checkpoint_path = str(weights_path)
            self._last_loss = float(metadata.get("loss", self._last_loss))
            self._last_accuracy = float(metadata.get("accuracy", self._last_accuracy))
        except Exception as exc:
            logger.warning(f"Failed to restore previous checkpoint: {exc}")

    def _gpu_train_step(self) -> tuple:
        """
        Execute one training step using CACHED GPU resources with AMP.

        OPTIMIZED: Uses mixed precision for RTX 2050 Tensor cores.
        Returns (success: bool, accuracy: float, loss: float).
        """
        if not self._gpu_initialized:
            if not self._init_gpu_resources():
                return False, 0.0, 0.0

        try:
            import time as _time

            # Initialize AMP scaler if not exists
            if not hasattr(self, "_scaler") or self._scaler is None:
                self._scaler = GradScaler() if AMP_AVAILABLE else None

            self._gpu_model.train()

            total_loss = 0.0
            total_correct = 0
            total_samples = 0
            total_batches = 0
            started = _time.perf_counter()

            sampler = getattr(self._gpu_dataloader, "sampler", None)
            if sampler is not None and hasattr(sampler, "set_epoch"):
                sampler.set_epoch(self._epoch)

            for batch_features, batch_labels in self._gpu_dataloader:
                if self._abort_flag.is_set():
                    return False, 0.0, 0.0

                if not self._wait_for_resource_window():
                    return False, 0.0, 0.0

                batch_features = batch_features.to(self._gpu_device, non_blocking=True)
                batch_labels = batch_labels.to(self._gpu_device, non_blocking=True)
                micro_batch_size = self._adaptive_micro_batch_size(
                    batch_features.size(0)
                )
                batch_correct = 0
                batch_seen = 0
                batch_loss = 0.0

                for start_idx in range(0, batch_features.size(0), micro_batch_size):
                    if self._abort_flag.is_set():
                        return False, 0.0, 0.0
                    end_idx = start_idx + micro_batch_size
                    feature_slice = batch_features[start_idx:end_idx]
                    label_slice = batch_labels[start_idx:end_idx]
                    self._gpu_optimizer.zero_grad(set_to_none=True)

                    if AMP_AVAILABLE and self._scaler is not None:
                        with autocast():
                            outputs = self._gpu_model(feature_slice)
                            loss = self._gpu_criterion(outputs, label_slice)
                        self._scaler.scale(loss).backward()
                        self._scaler.step(self._gpu_optimizer)
                        self._scaler.update()
                    else:
                        outputs = self._gpu_model(feature_slice)
                        loss = self._gpu_criterion(outputs, label_slice)
                        loss.backward()
                        self._gpu_optimizer.step()

                    _, predicted = torch.max(outputs.data, 1)
                    batch_correct += (predicted == label_slice).sum().item()
                    batch_seen += label_slice.size(0)
                    batch_loss += loss.item() * label_slice.size(0)

                total_correct += batch_correct
                total_samples += batch_seen
                total_batches += 1
                total_loss += batch_loss / max(batch_seen, 1)

            train_accuracy = total_correct / total_samples if total_samples > 0 else 0.0
            holdout_accuracy = self._evaluate_holdout_accuracy()
            avg_loss = total_loss / total_batches if total_batches > 0 else 0.0
            elapsed = max(_time.perf_counter() - started, 1e-6)
            self._last_loss = avg_loss
            self._last_accuracy = holdout_accuracy
            self._samples_per_sec = total_samples / elapsed

            return True, holdout_accuracy, avg_loss

        except Exception as e:
            logger.error(f"GPU training step failed: {e}")
            return False, 0.0, 0.0

    def _batch_to_training_samples(
        self,
        features_tensor,
        labels_tensor,
        source: str = "real_dataset",
    ) -> Tuple[TrainingSample, ...]:
        """Convert dataloader batch (features, labels) to Tuple[TrainingSample, ...]. NO synthetic data."""
        features_cpu = features_tensor.detach().to("cpu")
        labels_cpu = labels_tensor.detach().to("cpu")
        features_list = features_cpu.tolist()
        labels_list = labels_cpu.tolist()
        n = len(features_list)
        return tuple(
            TrainingSample(
                sample_id=f"REAL-{uuid.uuid4().hex[:12].upper()}",
                features=tuple(features_list[i]),
                label=int(labels_list[i]),
                source=source,
            )
            for i in range(n)
        )

    def _get_current_conditions(self) -> IdleConditions:
        """Get current idle conditions from real OS."""
        idle_seconds = get_idle_seconds()
        power_connected = is_power_connected()
        scan_active = is_scan_active()

        # GPU detection
        gpu_available = bool(TORCH_AVAILABLE and torch.cuda.is_available())

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

        device = get_torch_device()
        self._epoch += 1

        self._emit_event(
            "TRAINING_STARTED",
            f"Starting epoch {self._epoch} on GPU ({device_info.device_name})",
            epoch=self._epoch,
            gpu_used=True,
        )

        try:
            # Real data only: use dataloader from init (no synthetic data)
            if not self._gpu_initialized and not self._init_gpu_resources():
                self._emit_event(
                    "ERROR",
                    "GPU init failed - cannot train without real dataset",
                    epoch=self._epoch,
                    gpu_used=False,
                )
                return False

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

            success, accuracy, loss = self._gpu_train_step()
            if not success:
                return False

            if self._should_checkpoint(self._epoch, self._target_epochs):
                checkpoint_hash, checkpoint_path = self._save_checkpoint_artifacts(
                    accuracy, loss
                )
                self._emit_event(
                    "CHECKPOINT_SAVED",
                    f"Saved GPU checkpoint for epoch {self._epoch} (hash: {checkpoint_hash}, accuracy: {accuracy:.2%}, loss: {loss:.4f}, path: {checkpoint_path})",
                    epoch=self._epoch,
                    gpu_used=True,
                )

            self._emit_event(
                "TRAINING_STOPPED",
                f"Completed GPU epoch {self._epoch} (accuracy: {accuracy:.2%}, loss: {loss:.4f})",
                epoch=self._epoch,
                gpu_used=True,
            )

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
                self._state = TrainingState.IDLE
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
                self._state = TrainingState.IDLE
                return False

            # Evaluate training trigger
            trigger = evaluate_training_trigger(
                idle_result,
                None,  # model_status - we allow fresh training
                pending_samples=100,  # representation samples available
            )

            if not trigger.should_train:
                self._state = TrainingState.IDLE
                return False

            # Start training session
            with self._training_lock:
                self._state = TrainingState.TRAINING
                self._current_session = TrainingSession(
                    started_at=datetime.now(timezone.utc).isoformat(),
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

            return success

        except Exception as e:
            self._emit_event("ERROR", str(e))
            self._state = TrainingState.ERROR
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
                e for e in self._events if e.event_type == "CHECKPOINT_SAVED"
            ]
            last_hash = ""
            if checkpoint_events:
                # Extract hash from details
                details = checkpoint_events[-1].details
                if "hash: " in details:
                    last_hash = (
                        details.split("hash: ", 1)[1].split(",", 1)[0].rstrip(")")
                    )

            paths = generate_training_report(
                total_epochs=epochs_trained,
                gpu_used=self._current_session.gpu_used,
                started_at=self._current_session.started_at,
                stopped_at=stopped_at,
                checkpoints_saved=len(checkpoint_events),
                last_checkpoint_hash=last_hash,
                samples_processed=epochs_trained
                * (
                    self._gpu_dataset_stats["train"]["total"]
                    if self._gpu_dataset_stats
                    else 0
                ),
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
        Background loop - MANUAL MODE ONLY.

        Does NOT auto-trigger training. Only monitors system state
        for dashboard display. Training starts ONLY via API.
        """
        self._running = True
        logger.info("G38 Trainer started in MANUAL MODE (no auto-trigger)")

        while self._running:
            # NO auto-trigger - just keep alive for status polling
            await asyncio.sleep(self.CHECK_INTERVAL_SECONDS)

        logger.info("G38 Trainer stopped")

    def start(self) -> None:
        """Start the background scheduler."""
        if self._task is not None:
            return

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        self._task = loop.create_task(self.run_scheduler())

    def stop(self) -> None:
        """Stop the background scheduler."""
        self._running = False
        self._abort_flag.set()

        if self._task is not None:
            self._task.cancel()
            self._task = None

    def abort_training(self) -> dict:
        """Abort training immediately. Returns status."""
        if self._state != TrainingState.TRAINING:
            return {
                "aborted": False,
                "reason": "No training in progress",
                "state": self._state.value,
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
        """Legacy abort - use abort_training() instead."""
        self._abort_flag.set()
        self._emit_event(
            "TRAINING_ABORTED",
            "Manual abort requested",
        )

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

            self._state = TrainingState.TRAINING
            self._abort_flag.clear()
            # Set REAL target for progress tracking
            self._target_epochs = epochs
            self._session_epoch = 0
            # Track session for report generation
            self._current_session = TrainingSession(
                started_at=datetime.now(timezone.utc).isoformat(),
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
                success, accuracy, loss = self._gpu_train_step()

                if (
                    not self._abort_flag.is_set()
                    and success
                    and self._should_checkpoint(self._session_epoch, epochs)
                ):
                    checkpoint_hash, checkpoint_path = self._save_checkpoint_artifacts(
                        accuracy, loss
                    )
                    self._emit_event(
                        "CHECKPOINT_SAVED",
                        f"GPU checkpoint {self._session_epoch}/{epochs} (hash: {checkpoint_hash}, accuracy: {accuracy:.2%}, loss: {loss:.4f}, path: {checkpoint_path})",
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
            self._state = TrainingState.ERROR
            self._emit_event("ERROR", f"GPU training failed: {str(e)}", gpu_used=True)
            return {
                "started": False,
                "reason": str(e),
                "state": "ERROR",
            }

    def get_status(self) -> dict:
        """Get current trainer status for dashboard."""
        conditions = self._get_current_conditions()

        # Calculate REAL progress percentage
        if self.is_training and self._target_epochs > 0:
            # Active training - show live progress
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
            "state": self._state.value,
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
            "dataset_size": self._gpu_dataset_stats["train"]["total"]
            if self._gpu_dataset_stats
            else 0,
            "training_mode": "MANUAL",
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
    """Initialize trainer in MANUAL mode. No auto-trigger."""
    trainer = get_auto_trainer()
    trainer.start()  # Starts background loop for status polling only


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

        trainer._continuous_mode = True
        trainer._continuous_target = target_epochs
        trainer._state = TrainingState.TRAINING
        trainer._abort_flag.clear()
        trainer._target_epochs = target_epochs if target_epochs > 0 else 999999
        trainer._session_epoch = 0
        trainer._current_session = TrainingSession(
            started_at=datetime.now(timezone.utc).isoformat(),
            start_epoch=trainer._epoch,
            gpu_used=True,  # Always GPU
        )

    trainer._emit_event(
        "CONTINUOUS_START",
        f"24/7 continuous GPU training started on {device_info.device_name} (target: {'infinite' if target_epochs == 0 else target_epochs} epochs)",
        gpu_used=True,
    )

    # Start background thread for continuous GPU training (real data only, no synthetic)
    def _run_continuous():
        if not trainer._gpu_initialized and not trainer._init_gpu_resources():
            trainer._emit_event(
                "ERROR",
                "Continuous training requires GPU init with real dataset",
                gpu_used=False,
            )
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
                f"Starting GPU epoch {epoch_count}"
                + (f"/{target_epochs}" if target_epochs > 0 else " (24/7 mode)"),
                epoch=epoch_count,
                gpu_used=True,
            )

            try:
                success, accuracy, loss = trainer._gpu_train_step()
                if (
                    not trainer._abort_flag.is_set()
                    and trainer._continuous_mode
                    and success
                    and trainer._should_checkpoint(epoch_count, target_epochs)
                ):
                    checkpoint_hash, checkpoint_path = (
                        trainer._save_checkpoint_artifacts(accuracy, loss)
                    )
                    trainer._emit_event(
                        "CHECKPOINT_SAVED",
                        f"Saved GPU checkpoint epoch {epoch_count} (hash: {checkpoint_hash}, accuracy: {accuracy:.2%}, loss: {loss:.4f}, path: {checkpoint_path})",
                        epoch=epoch_count,
                        gpu_used=True,
                    )

            except Exception as e:
                trainer._emit_event(
                    "ERROR",
                    f"GPU training failed at epoch {epoch_count}: {str(e)}",
                    epoch=epoch_count,
                    gpu_used=True,
                )

            # Small pause between epochs
            trainer._abort_flag.wait(0.5)

        # Cleanup
        trainer._continuous_mode = False
        with trainer._training_lock:
            trainer._state = TrainingState.IDLE
            if trainer._current_session:
                trainer._generate_session_report()
            trainer._current_session = None

        trainer._emit_event(
            "CONTINUOUS_STOP",
            f"Continuous GPU training completed: {epoch_count} epochs",
            epoch=epoch_count,
            gpu_used=True,
        )

    try:
        loop = asyncio.get_running_loop()
        loop.create_task(asyncio.to_thread(_run_continuous))
    except RuntimeError:
        thread = threading.Thread(target=_run_continuous, daemon=True)
        thread.start()

    return {
        "started": True,
        "mode": "continuous",
        "gpu_used": True,
        "device": device_info.device_name,
        "target_epochs": target_epochs if target_epochs > 0 else "infinite",
        "state": "TRAINING",
    }


def stop_continuous_training() -> dict:
    """Stop 24/7 continuous training."""
    trainer = get_auto_trainer()
    trainer._continuous_mode = False
    trainer._abort_flag.set()

    return {
        "stopped": True,
        "state": trainer._state.value,
        "total_completed": trainer._epoch,
    }
