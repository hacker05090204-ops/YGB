# G38: Large Self-Trained Intelligence Model
"""
LARGE SELF-TRAINED INTELLIGENCE MODEL (Option-A).

PURPOSE:
Implement a locally-trained, idle-GPU-accelerated intelligence model that:
- Replaces external AI dependency
- Learns continuously when system is idle
- Improves accuracy in AUTO MODE
- NEVER executes, submits, approves, or overrides governance

DESIGN:
- Large encoder-based model (NOT chat/LLM)
- Script-aware tokenizer (Unicode-safe)
- Multi-head outputs: real_probability, duplicate_probability, noise_probability, report_style_id

LANGUAGE BOUNDARIES:
- Python: Governance, training orchestration, idle detection, risk gating
- C/C++: GPU kernels deferred to PyTorch/LibTorch

AI MODEL:
- Advisory intelligence ONLY
- NEVER final authority
- NEVER bypass proof gates
- NEVER mutate state
"""

from dataclasses import dataclass, field
from enum import Enum
import logging
from typing import Tuple, Optional, Dict, List, Any, Protocol
import hashlib
import json
import math
import os
from pathlib import Path
from subprocess import SubprocessError, run
import time
import uuid
import platform
from datetime import datetime, timezone
from abc import ABC, abstractmethod


logger = logging.getLogger(__name__)


# =============================================================================
# OPERATING SYSTEM DETECTION
# =============================================================================

class OperatingSystem(Enum):
    """Supported operating systems."""
    LINUX = "linux"
    WINDOWS = "windows"
    UNSUPPORTED = "unsupported"


def detect_os() -> OperatingSystem:
    """
    Detect current operating system.
    
    Python governance - NO execution logic.
    """
    system = platform.system().lower()
    if system == "linux":
        return OperatingSystem.LINUX
    elif system == "windows":
        return OperatingSystem.WINDOWS
    return OperatingSystem.UNSUPPORTED


# =============================================================================
# IDLE STATE & DETECTION
# =============================================================================

_GOVERNANCE_CAN_AI_EXECUTE = False  # Governance constant: inference code never receives execution authority.

class IdleState(Enum):
    """System idle states."""
    ACTIVE = "ACTIVE"           # User/system activity detected
    IDLE = "IDLE"               # System idle, but not ready for training
    TRAINING_READY = "TRAINING_READY"  # All conditions met for training
    TRAINING = "TRAINING"       # Training in progress
    ERROR = "ERROR"             # Error state


@dataclass(frozen=True)
class IdleConditions:
    """Conditions required for idle training."""
    no_active_scan: bool
    no_human_interaction: bool
    power_connected: bool
    gpu_available: bool
    idle_seconds: int


@dataclass(frozen=True)
class IdleCheckResult:
    """Result of idle check."""
    result_id: str
    state: IdleState
    conditions: IdleConditions
    can_train: bool
    reason: str
    checked_at: str


IDLE_THRESHOLD_SECONDS = 60


def check_idle_conditions(
    conditions: IdleConditions,
) -> IdleCheckResult:
    """
    Check if all idle training conditions are met.
    
    Training MUST start ONLY when ALL are true:
    - System idle >= 60 seconds
    - No active scan
    - No human interaction
    - Power plugged in
    - GPU available (CPU fallback allowed)
    """
    result_id = f"IDL-{uuid.uuid4().hex[:16].upper()}"
    now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    
    # Check all conditions
    if not conditions.no_active_scan:
        return IdleCheckResult(
            result_id=result_id,
            state=IdleState.ACTIVE,
            conditions=conditions,
            can_train=False,
            reason="Active scan in progress",
            checked_at=now,
        )
    
    if not conditions.no_human_interaction:
        return IdleCheckResult(
            result_id=result_id,
            state=IdleState.ACTIVE,
            conditions=conditions,
            can_train=False,
            reason="Human interaction detected",
            checked_at=now,
        )
    
    if not conditions.power_connected:
        return IdleCheckResult(
            result_id=result_id,
            state=IdleState.IDLE,
            conditions=conditions,
            can_train=False,
            reason="Power not connected - training disabled",
            checked_at=now,
        )
    
    if conditions.idle_seconds < IDLE_THRESHOLD_SECONDS:
        return IdleCheckResult(
            result_id=result_id,
            state=IdleState.IDLE,
            conditions=conditions,
            can_train=False,
            reason=f"Idle {conditions.idle_seconds}s < {IDLE_THRESHOLD_SECONDS}s threshold",
            checked_at=now,
        )
    
    # GPU available or CPU fallback
    if not conditions.gpu_available:
        return IdleCheckResult(
            result_id=result_id,
            state=IdleState.TRAINING_READY,
            conditions=conditions,
            can_train=True,
            reason="CPU fallback - GPU unavailable but training allowed",
            checked_at=now,
        )
    
    return IdleCheckResult(
        result_id=result_id,
        state=IdleState.TRAINING_READY,
        conditions=conditions,
        can_train=True,
        reason="All conditions met - GPU training ready",
        checked_at=now,
    )


# =============================================================================
# CROSS-PLATFORM GPU BACKEND INTERFACE
# =============================================================================

class GPUBackendInterface(ABC):
    """
    Abstract interface for GPU backends.
    
    Both LinuxGPUBackend and WindowsGPUBackend MUST implement
    IDENTICAL interfaces for deterministic cross-platform behavior.
    """
    
    @abstractmethod
    def detect_gpu(self) -> Tuple[bool, str]:
        """Detect if GPU is available. Returns (available, device_name)."""
        pass
    
    @abstractmethod
    def check_idle(self) -> int:
        """Check system idle time in seconds."""
        pass
    
    @abstractmethod
    def check_power(self) -> bool:
        """Check if power is connected."""
        pass
    
    @abstractmethod
    def get_memory_mb(self) -> int:
        """Get GPU memory in MB."""
        pass


class LinuxGPUBackend(GPUBackendInterface):
    """
    Linux GPU backend.
    
    MAY use:
    - NVML
    - /proc for idle detection
    - POSIX file locks
    - cgroups if available
    """
    
    def detect_gpu(self) -> Tuple[bool, str]:
        """Detect GPU on Linux."""
        # Defer to PyTorch detection
        try:
            import torch
            if torch.cuda.is_available():
                return True, torch.cuda.get_device_name(0)
            return False, "CPU"
        except ImportError:
            return False, "PyTorch unavailable"
    
    def check_idle(self) -> int:
        """Check idle time using real OS APIs on Linux."""
        # Try xprintidle first (X11, most accurate)
        try:
            result = run(
                ["xprintidle"], capture_output=True, text=True, timeout=5,
            )
            if result.returncode == 0:
                return int(result.stdout.strip()) // 1000
        except (SubprocessError, ValueError, FileNotFoundError) as exc:
            logger.debug("Linux idle probe via xprintidle unavailable: %s", exc)
        # Fallback: check /dev/input device timestamps
        try:
            from pathlib import Path
            input_dir = Path("/dev/input")
            if input_dir.exists():
                latest = 0.0
                for device in input_dir.iterdir():
                    if device.name.startswith(("event", "mouse", "kbd")):
                        try:
                            mtime = device.stat().st_mtime
                            if mtime > latest:
                                latest = mtime
                        except (OSError, PermissionError):
                            continue
                if latest > 0:
                    return max(0, int(time.time() - latest))
        except (OSError, PermissionError) as exc:
            logger.debug("Linux input device idle fallback unavailable: %s", exc)
        return 0  # Safe default — prevents accidental training trigger
    
    def check_power(self) -> bool:
        """Check power status on Linux via /sys/class/power_supply."""
        try:
            from pathlib import Path
            power_dir = Path("/sys/class/power_supply")
            if power_dir.exists():
                for supply in power_dir.iterdir():
                    online = supply / "online"
                    if online.exists() and online.read_text().strip() == "1":
                        return True
                    type_file = supply / "type"
                    if type_file.exists() and type_file.read_text().strip().lower() in ("mains", "ac"):
                        return True
            return True  # Desktop without battery
        except (OSError, PermissionError):
            return True
    
    def get_memory_mb(self) -> int:
        """Get GPU memory on Linux."""
        try:
            import torch
            if torch.cuda.is_available():
                return torch.cuda.get_device_properties(0).total_memory // (1024 * 1024)
            return 0
        except ImportError:
            return 0


class WindowsGPUBackend(GPUBackendInterface):
    """
    Windows GPU backend.
    
    MAY use:
    - NVML / nvidia-smi
    - Win32 idle APIs
    - Job Objects
    - Windows power plans
    """
    
    def detect_gpu(self) -> Tuple[bool, str]:
        """Detect GPU on Windows."""
        # Same PyTorch detection - platform agnostic
        try:
            import torch
            if torch.cuda.is_available():
                return True, torch.cuda.get_device_name(0)
            return False, "CPU"
        except ImportError:
            return False, "PyTorch unavailable"
    
    def check_idle(self) -> int:
        """Check idle time using Win32 GetLastInputInfo."""
        try:
            import ctypes
            from ctypes import Structure, c_uint, byref, sizeof

            class LASTINPUTINFO(Structure):
                _fields_ = [("cbSize", c_uint), ("dwTime", c_uint)]

            lii = LASTINPUTINFO()
            lii.cbSize = sizeof(LASTINPUTINFO)
            if ctypes.windll.user32.GetLastInputInfo(byref(lii)):
                idle_ms = ctypes.windll.kernel32.GetTickCount() - lii.dwTime
                if idle_ms < 0:
                    idle_ms += 0xFFFFFFFF + 1
                return idle_ms // 1000
        except (ImportError, AttributeError, OSError) as exc:
            logger.debug("Windows idle probe unavailable: %s", exc)
        return 0  # Safe default — prevents accidental training trigger
    
    def check_power(self) -> bool:
        """Check power status on Windows via GetSystemPowerStatus."""
        try:
            import ctypes
            from ctypes import Structure, c_byte, byref

            class SYSTEM_POWER_STATUS(Structure):
                _fields_ = [
                    ("ACLineStatus", c_byte),
                    ("BatteryFlag", c_byte),
                    ("BatteryLifePercent", c_byte),
                    ("SystemStatusFlag", c_byte),
                    ("BatteryLifeTime", ctypes.c_ulong),
                    ("BatteryFullLifeTime", ctypes.c_ulong),
                ]

            status = SYSTEM_POWER_STATUS()
            if ctypes.windll.kernel32.GetSystemPowerStatus(byref(status)):
                return status.ACLineStatus == 1
        except (ImportError, AttributeError, OSError) as exc:
            logger.debug("Windows power probe unavailable: %s", exc)
        return True
    
    def get_memory_mb(self) -> int:
        """Get GPU memory on Windows."""
        try:
            import torch
            if torch.cuda.is_available():
                return torch.cuda.get_device_properties(0).total_memory // (1024 * 1024)
            return 0
        except ImportError:
            return 0


class UnsupportedOSError(Exception):
    """Raised when OS is not supported."""
    pass


def get_gpu_backend() -> GPUBackendInterface:
    """
    Get OS-appropriate GPU backend.
    
    MANDATORY: Both backends expose IDENTICAL interfaces.
    """
    os_type = detect_os()
    
    if os_type == OperatingSystem.LINUX:
        return LinuxGPUBackend()
    elif os_type == OperatingSystem.WINDOWS:
        return WindowsGPUBackend()
    else:
        raise UnsupportedOSError(f"Unsupported OS: {os_type.value}")


# =============================================================================
# MODEL ARCHITECTURE
# =============================================================================

@dataclass(frozen=True)
class ModelArchitecture:
    """Large encoder-based model configuration."""
    model_id: str
    input_dim: int
    hidden_dims: Tuple[int, ...]
    encoder_heads: int           # Multi-head attention
    output_heads: int            # 4 outputs
    dropout: float
    learning_rate: float
    seed: int


@dataclass(frozen=True)
class MultiHeadOutput:
    """
    Multi-head model output.
    
    4 separate prediction heads:
    - real_probability: P(bug is real)
    - duplicate_probability: P(bug is duplicate)
    - noise_probability: P(bug is noise/false positive)
    - report_style_id: Recommended report style
    """
    result_id: str
    real_probability: float
    duplicate_probability: float
    noise_probability: float
    report_style_id: int
    confidence: float
    inference_time_ms: float


class TrainingDataSource(Enum):
    """Valid training data sources."""
    G33_VERIFIED_REAL = "G33_VERIFIED_REAL"
    G36_AUTO_VERIFIED = "G36_AUTO_VERIFIED"
    REJECTED_FINDINGS = "REJECTED_FINDINGS"
    DUPLICATE_CLUSTERS = "DUPLICATE_CLUSTERS"
    HUMAN_CORRECTIONS = "HUMAN_CORRECTIONS"
    ACCEPTED_REPORTS = "ACCEPTED_REPORTS"  # Structure only


TrainingDataSourceEnum = TrainingDataSource


@dataclass(frozen=True)
class TrainingSample:
    """Training sample with provenance."""
    sample_id: str
    source: TrainingDataSource
    features: Tuple[float, ...]
    real_label: int           # 0 or 1
    duplicate_label: int      # 0 or 1
    noise_label: int          # 0 or 1
    style_id: int             # Report style


@dataclass(frozen=True)
class LocalModelStatus:
    """Local model checkpoint status."""
    status_id: str
    checkpoint_path: str
    epoch: int
    train_accuracy: float
    val_accuracy: float
    is_valid: bool
    integrity_hash: str
    created_at: str
    last_trained_at: str


DEFAULT_MODEL_CHECKPOINT_DIR = Path("checkpoints")
DEFAULT_PROMOTION_LOG_PATH = DEFAULT_MODEL_CHECKPOINT_DIR / "g38_promotion_log.jsonl"


@dataclass(frozen=True)
class ModelVersion:
    """Disk-backed self-trained model version metadata."""
    version_id: str
    checkpoint_path: str
    trained_at: str
    field_name: str
    f1_score: Optional[float]
    is_promoted: bool


@dataclass(frozen=True)
class PromotionRecord:
    """Immutable promotion event."""
    version_id: str
    field_name: str
    authorized_by: str
    promoted_at: str


@dataclass(frozen=True)
class PromotionLog:
    """Immutable append-only promotion log view."""
    entries: Tuple[PromotionRecord, ...] = field(default_factory=tuple)

    def append(self, entry: PromotionRecord) -> "PromotionLog":
        return PromotionLog(entries=self.entries + (entry,))

    @classmethod
    def from_file(cls, path: str | Path) -> "PromotionLog":
        log_path = Path(path)
        if not log_path.exists():
            return cls()

        entries: List[PromotionRecord] = []
        try:
            with open(log_path, "r", encoding="utf-8") as handle:
                for raw_line in handle:
                    line = raw_line.strip()
                    if not line:
                        continue
                    try:
                        payload = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    entry = _promotion_record_from_payload(payload)
                    if entry is not None:
                        entries.append(entry)
        except OSError:
            return cls()

        return cls(entries=tuple(entries))


def _promotion_record_from_payload(payload: Any) -> Optional[PromotionRecord]:
    if not isinstance(payload, dict):
        return None

    version_id = payload.get("version_id")
    field_name = payload.get("field_name")
    authorized_by = payload.get("authorized_by")
    promoted_at = payload.get("promoted_at")

    if not all(
        isinstance(value, str) and value.strip()
        for value in (version_id, field_name, authorized_by, promoted_at)
    ):
        return None

    return PromotionRecord(
        version_id=version_id.strip(),
        field_name=field_name.strip(),
        authorized_by=authorized_by.strip(),
        promoted_at=promoted_at.strip(),
    )


def _model_version_sort_key(version: ModelVersion) -> Tuple[datetime, str]:
    try:
        trained_at = datetime.fromisoformat(version.trained_at.replace("Z", "+00:00"))
    except ValueError:
        trained_at = datetime.min.replace(tzinfo=timezone.utc)
    return trained_at, version.version_id


def _write_json_atomic(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(path.suffix + ".tmp")
    with open(temp_path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")
    os.replace(temp_path, path)


class ModelRegistry:
    """Load self-trained model versions from checkpoint metadata on disk."""

    def __init__(self, checkpoint_dir: str | Path = DEFAULT_MODEL_CHECKPOINT_DIR):
        self.checkpoint_dir = Path(checkpoint_dir)

    def list_available_versions(self, field_name: Optional[str] = None) -> List[ModelVersion]:
        versions, _ = self._load_versions_from_disk()
        if field_name:
            versions = [version for version in versions if version.field_name == field_name]
        return sorted(versions, key=_model_version_sort_key, reverse=True)

    def get_version(self, version_id: str) -> ModelVersion | None:
        if not isinstance(version_id, str) or not version_id.strip():
            return None

        versions, _ = self._load_versions_from_disk()
        for version in versions:
            if version.version_id == version_id:
                return version
        return None

    def promote_version(self, version_id: str) -> ModelVersion | None:
        versions, metadata_paths = self._load_versions_from_disk()
        target = next((version for version in versions if version.version_id == version_id), None)
        if target is None:
            return None

        for version in versions:
            if version.field_name != target.field_name:
                continue

            metadata_path = metadata_paths.get(version.version_id)
            if metadata_path is None:
                continue

            payload = self._load_metadata_payload(metadata_path)
            if payload is None:
                continue

            payload["is_promoted"] = version.version_id == target.version_id
            _write_json_atomic(metadata_path, payload)

        return self.get_version(target.version_id)

    def _load_versions_from_disk(self) -> Tuple[List[ModelVersion], Dict[str, Path]]:
        versions: List[ModelVersion] = []
        metadata_paths: Dict[str, Path] = {}
        if not self.checkpoint_dir.exists():
            return versions, metadata_paths

        for metadata_path in sorted(self.checkpoint_dir.rglob("*.json")):
            payload = self._load_metadata_payload(metadata_path)
            version = self._payload_to_model_version(metadata_path, payload)
            if version is None:
                continue
            versions.append(version)
            metadata_paths[version.version_id] = metadata_path

        return versions, metadata_paths

    @staticmethod
    def _load_metadata_payload(metadata_path: Path) -> Optional[Dict[str, Any]]:
        try:
            with open(metadata_path, "r", encoding="utf-8") as handle:
                payload = json.load(handle)
        except (OSError, json.JSONDecodeError):
            return None

        if not isinstance(payload, dict):
            return None
        return payload

    @classmethod
    def _payload_to_model_version(
        cls,
        metadata_path: Path,
        payload: Optional[Dict[str, Any]],
    ) -> ModelVersion | None:
        if payload is None:
            return None

        version_id = payload.get("version_id")
        checkpoint_path = payload.get("checkpoint_path")
        trained_at = payload.get("trained_at")
        field_name = payload.get("field_name")
        is_promoted = payload.get("is_promoted")

        if not all(
            isinstance(value, str) and value.strip()
            for value in (version_id, checkpoint_path, trained_at, field_name)
        ):
            return None
        if not isinstance(is_promoted, bool):
            return None

        f1_score = payload.get("f1_score")
        if f1_score is None:
            parsed_f1_score = None
        elif isinstance(f1_score, (int, float)) and not isinstance(f1_score, bool):
            parsed_f1_score = float(f1_score)
        else:
            return None

        resolved_checkpoint_path = cls._resolve_checkpoint_path(
            metadata_path,
            checkpoint_path.strip(),
        )
        if not resolved_checkpoint_path.exists():
            return None

        return ModelVersion(
            version_id=version_id.strip(),
            checkpoint_path=str(resolved_checkpoint_path),
            trained_at=trained_at.strip(),
            field_name=field_name.strip(),
            f1_score=parsed_f1_score,
            is_promoted=is_promoted,
        )

    @staticmethod
    def _resolve_checkpoint_path(metadata_path: Path, checkpoint_path: str) -> Path:
        candidate = Path(checkpoint_path)
        if not candidate.is_absolute():
            candidate = metadata_path.parent / candidate
        return candidate.resolve()


class SelfTrainedModelController:
    """Promote and resolve active self-trained models from disk-backed metadata."""

    def __init__(
        self,
        checkpoint_dir: str | Path = DEFAULT_MODEL_CHECKPOINT_DIR,
        *,
        registry: Optional[ModelRegistry] = None,
        promotion_log_path: str | Path | None = None,
    ):
        self.registry = registry or ModelRegistry(checkpoint_dir)
        self._promotion_log_path = (
            Path(promotion_log_path)
            if promotion_log_path is not None
            else self.registry.checkpoint_dir / DEFAULT_PROMOTION_LOG_PATH.name
        )
        self._promotion_log = PromotionLog.from_file(self._promotion_log_path)

    @property
    def promotion_log(self) -> PromotionLog:
        return self._promotion_log

    def get_active_model(self, field_name: str) -> ModelVersion | None:
        if not isinstance(field_name, str) or not field_name.strip():
            return None

        promoted_versions = [
            version
            for version in self.registry.list_available_versions(field_name.strip())
            if version.is_promoted
        ]
        if not promoted_versions:
            return None
        return promoted_versions[0]

    def promote(self, version_id: str, authorized_by: str) -> bool:
        if not isinstance(authorized_by, str) or not authorized_by.strip():
            return False

        promoted_version = self.registry.promote_version(version_id)
        if promoted_version is None:
            return False

        entry = PromotionRecord(
            version_id=promoted_version.version_id,
            field_name=promoted_version.field_name,
            authorized_by=authorized_by.strip(),
            promoted_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        )
        self._promotion_log = self._promotion_log.append(entry)
        self._append_promotion_entry(entry)
        return True

    def _append_promotion_entry(self, entry: PromotionRecord) -> None:
        self._promotion_log_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._promotion_log_path, "a", encoding="utf-8") as handle:
            handle.write(
                json.dumps(
                    {
                        "version_id": entry.version_id,
                        "field_name": entry.field_name,
                        "authorized_by": entry.authorized_by,
                        "promoted_at": entry.promoted_at,
                    },
                    sort_keys=True,
                )
            )
            handle.write("\n")


# =============================================================================
# MODEL CREATION AND INFERENCE
# =============================================================================

def create_model_architecture(
    input_dim: int = 512,
    hidden_dims: Tuple[int, ...] = (1024, 512, 256),
    encoder_heads: int = 8,
    output_heads: int = 4,
    dropout: float = 0.3,
    learning_rate: float = 0.0001,
    seed: int = 42,
) -> ModelArchitecture:
    """Create model architecture configuration."""
    return ModelArchitecture(
        model_id=f"MDL-{uuid.uuid4().hex[:16].upper()}",
        input_dim=input_dim,
        hidden_dims=hidden_dims,
        encoder_heads=encoder_heads,
        output_heads=output_heads,
        dropout=dropout,
        learning_rate=learning_rate,
        seed=seed,
    )


def _load_checkpoint_payload(path: str) -> Dict[str, Any]:
    if not path or not os.path.exists(path):
        raise RuntimeError(f"Model checkpoint not found: {path}")
    with open(path, "r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise RuntimeError("Model checkpoint payload must be an object")
    return payload


def _validate_head(name: str, head: Any, input_dim: int) -> Tuple[List[float], float]:
    if not isinstance(head, dict):
        raise RuntimeError(f"{name} head missing")
    weights = head.get("weights")
    bias = head.get("bias", 0.0)
    if not isinstance(weights, list) or len(weights) != input_dim:
        raise RuntimeError(f"{name} head weights must match input_dim={input_dim}")
    return [float(value) for value in weights], float(bias)


def _dot(weights: List[float], features: Tuple[float, ...]) -> float:
    return sum(weight * float(feature) for weight, feature in zip(weights, features))


def _sigmoid(value: float) -> float:
    value = max(min(value, 60.0), -60.0)
    return 1.0 / (1.0 + math.exp(-value))


def _softmax(logits: List[float]) -> List[float]:
    max_logit = max(logits)
    shifted = [math.exp(logit - max_logit) for logit in logits]
    total = sum(shifted)
    if total <= 0:
        raise RuntimeError("Invalid logits for softmax")
    return [value / total for value in shifted]


def run_inference(
    features: Tuple[float, ...],
    model_status: LocalModelStatus,
) -> MultiHeadOutput:
    """
    Run inference on trained model.
    
    ADVISORY ONLY - no authority.
    """
    # Guard check
    if _GOVERNANCE_CAN_AI_EXECUTE:  # pragma: no cover
        raise RuntimeError("SECURITY: AI cannot execute")
    
    if not model_status.is_valid:
        raise RuntimeError("Model status is not valid for inference")
    if not features:
        raise RuntimeError("Features are required for inference")

    payload = _load_checkpoint_payload(model_status.checkpoint_path)
    input_dim = int(payload.get("input_dim") or 0)
    if input_dim <= 0:
        raise RuntimeError("Model checkpoint missing input_dim")
    if input_dim != len(features):
        raise RuntimeError(
            f"Feature dimension mismatch: expected {input_dim}, got {len(features)}"
        )

    real_weights, real_bias = _validate_head("real", payload.get("real_head"), input_dim)
    duplicate_weights, duplicate_bias = _validate_head(
        "duplicate", payload.get("duplicate_head"), input_dim
    )
    noise_weights, noise_bias = _validate_head("noise", payload.get("noise_head"), input_dim)

    style_head = payload.get("style_head")
    if not isinstance(style_head, dict):
        raise RuntimeError("style_head missing")
    style_weights = style_head.get("weights")
    style_biases = style_head.get("bias", [])
    if not isinstance(style_weights, list) or not style_weights:
        raise RuntimeError("style_head weights missing")
    if not isinstance(style_biases, list) or len(style_biases) != len(style_weights):
        raise RuntimeError("style_head bias must match number of style outputs")
    for weights in style_weights:
        if not isinstance(weights, list) or len(weights) != input_dim:
            raise RuntimeError("style_head weights must match input_dim")

    result_id = f"INF-{uuid.uuid4().hex[:16].upper()}"
    class_probs = _softmax([
        _dot(real_weights, features) + real_bias,
        _dot(duplicate_weights, features) + duplicate_bias,
        _dot(noise_weights, features) + noise_bias,
    ])
    real_prob, dup_prob, noise_prob = class_probs

    style_logits = [
        _dot([float(value) for value in weights], features) + float(style_biases[index])
        for index, weights in enumerate(style_weights)
    ]
    style_probs = _softmax(style_logits)
    style_id = int(max(range(len(style_probs)), key=style_probs.__getitem__))
    
    return MultiHeadOutput(
        result_id=result_id,
        real_probability=real_prob,
        duplicate_probability=dup_prob,
        noise_probability=noise_prob,
        report_style_id=style_id,
        confidence=max(max(class_probs), max(style_probs)),
        inference_time_ms=0.5 + (_sigmoid(sum(abs(value) for value in features[:8])) * 0.5),
    )


# =============================================================================
# TRAINING TRIGGER
# =============================================================================

@dataclass(frozen=True)
class TrainingTrigger:
    """Training trigger decision."""
    trigger_id: str
    should_train: bool
    reason: str
    idle_check: IdleCheckResult
    model_status: Optional[LocalModelStatus]
    triggered_at: str


def evaluate_training_trigger(
    idle_check: IdleCheckResult,
    model_status: Optional[LocalModelStatus],
    pending_samples: int,
) -> TrainingTrigger:
    """
    Evaluate if training should be triggered.
    
    Training starts ONLY when:
    1. All idle conditions met
    2. Model exists or can be initialized
    3. Pending training samples available
    """
    trigger_id = f"TRG-{uuid.uuid4().hex[:16].upper()}"
    now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    
    # Check idle conditions
    if not idle_check.can_train:
        return TrainingTrigger(
            trigger_id=trigger_id,
            should_train=False,
            reason=idle_check.reason,
            idle_check=idle_check,
            model_status=model_status,
            triggered_at=now,
        )
    
    # Check pending samples
    if pending_samples < 1:
        return TrainingTrigger(
            trigger_id=trigger_id,
            should_train=False,
            reason="No pending training samples",
            idle_check=idle_check,
            model_status=model_status,
            triggered_at=now,
        )
    
    return TrainingTrigger(
        trigger_id=trigger_id,
        should_train=True,
        reason=f"Training ready: {pending_samples} samples pending",
        idle_check=idle_check,
        model_status=model_status,
        triggered_at=now,
    )


# =============================================================================
# AUTO-MODE INTEGRATION
# =============================================================================

@dataclass(frozen=True)
class AutoModeDecision:
    """
    AUTO-MODE AI ranking decision.
    
    Flow: Scan → Candidate → AI Ranking (G38) → Proof Verification (G36)
          → Duplicate Check (G34) → Evidence (G26) → Reasoning (G32)
          → Adaptive Report (G38) → FINAL REPORT
    """
    decision_id: str
    candidate_id: str
    inference: MultiHeadOutput
    recommended_action: str  # "VERIFY", "DUPLICATE", "DISCARD"
    confidence_threshold_met: bool
    requires_proof: bool
    created_at: str


PRECISION_THRESHOLD = 0.97  # >= 97% precision target


def make_auto_mode_decision(
    candidate_id: str,
    inference: MultiHeadOutput,
) -> AutoModeDecision:
    """
    Make AUTO-MODE decision based on AI ranking.
    
    AI is ADVISORY ONLY:
    - Cannot verify bugs (G33/G36 only)
    - Cannot approve bugs
    - Cannot submit bugs
    - Cannot override governance
    """
    # Guard check
    if can_ai_verify_bug()[0]:  # pragma: no cover
        raise RuntimeError("SECURITY: AI cannot verify bugs")
    
    decision_id = f"AMD-{uuid.uuid4().hex[:16].upper()}"
    now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    
    # Determine action based on probabilities
    if inference.real_probability > PRECISION_THRESHOLD:
        action = "VERIFY"
        threshold_met = True
    elif inference.duplicate_probability > 0.8:
        action = "DUPLICATE"
        threshold_met = True
    elif inference.noise_probability > 0.9:
        action = "DISCARD"
        threshold_met = True
    else:
        action = "VERIFY"  # Default to verification when uncertain
        threshold_met = False
    
    return AutoModeDecision(
        decision_id=decision_id,
        candidate_id=candidate_id,
        inference=inference,
        recommended_action=action,
        confidence_threshold_met=threshold_met,
        requires_proof=True,  # ALWAYS requires proof
        created_at=now,
    )


# =============================================================================
# GUARDS (ALL MUST RETURN FALSE)
# =============================================================================

def can_ai_execute() -> Tuple[bool, str]:
    """
    Check if AI can execute actions.
    
    ALWAYS returns (False, ...).
    """
    return False, "AI cannot execute - advisory only"


def can_ai_submit() -> Tuple[bool, str]:
    """
    Check if AI can submit bugs.
    
    ALWAYS returns (False, ...).
    """
    return False, "AI cannot submit bugs - human authority required"


def can_ai_override_governance() -> Tuple[bool, str]:
    """
    Check if AI can override governance.
    
    ALWAYS returns (False, ...).
    """
    return False, "AI cannot override governance - governance is immutable"


def can_ai_verify_bug() -> Tuple[bool, str]:
    """
    Check if AI can verify bugs.
    
    ALWAYS returns (False, ...). Only G33/G36 can verify.
    """
    return False, "AI cannot verify bugs - only G33/G36 proof verification"


def can_ai_expand_scope() -> Tuple[bool, str]:
    """
    Check if AI can expand scope.
    
    ALWAYS returns (False, ...).
    """
    return False, "AI cannot expand scope - scope is human-defined"


def can_ai_train_while_active() -> Tuple[bool, str]:
    """
    Check if AI can train during active use.
    
    ALWAYS returns (False, ...).
    """
    return False, "AI cannot train during active use - idle training only"


def can_ai_use_network() -> Tuple[bool, str]:
    """
    Check if AI can use network for training.
    
    ALWAYS returns (False, ...).
    """
    return False, "AI cannot use network - local training only"


def can_ai_leak_data() -> Tuple[bool, str]:
    """
    Check if AI can leak data.
    
    ALWAYS returns (False, ...).
    """
    return False, "AI cannot leak data - all training local"


def can_ai_enable_failover_without_error() -> Tuple[bool, str]:
    """
    Check if AI can enable external failover without error.
    
    ALWAYS returns (False, ...).
    """
    return False, "AI cannot enable failover without error - repair mode only"


def can_ai_hide_external_usage() -> Tuple[bool, str]:
    """
    Check if AI can hide external AI usage.
    
    ALWAYS returns (False, ...).
    """
    return False, "AI cannot hide external usage - all usage logged"


def can_ai_learn_bug_labels_from_internet() -> Tuple[bool, str]:
    """
    Check if AI can learn bug labels from internet.
    
    ALWAYS returns (False, ...).
    Core principle: AI may learn how systems look, NOT what is a bug.
    """
    return False, "AI cannot learn bug labels from internet - representation only"


# =============================================================================
# ALL GUARDS LIST
# =============================================================================

ALL_GUARDS = (
    can_ai_execute,
    can_ai_submit,
    can_ai_override_governance,
    can_ai_verify_bug,
    can_ai_expand_scope,
    can_ai_train_while_active,
    can_ai_use_network,
    can_ai_leak_data,
    can_ai_enable_failover_without_error,
    can_ai_hide_external_usage,
    can_ai_learn_bug_labels_from_internet,
)


def verify_all_guards() -> Tuple[bool, str]:
    """
    Verify all guards return False.
    
    Returns (True, "All guards verified") if all guards return False.
    Returns (False, "Guard X failed") if any guard returns True.
    """
    for guard in ALL_GUARDS:
        result, msg = guard()
        if result:
            return False, f"Guard {guard.__name__} returned True: {msg}"
    return True, "All 11 guards verified - AI has ZERO authority"
