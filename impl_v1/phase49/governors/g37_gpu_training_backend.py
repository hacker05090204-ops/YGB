# G37 GPU Training Backend (REAL)
"""
REAL training adapter for the G37 governor layer.

This module preserves the Phase-49 governor-facing API while routing model
training and inference through the real PyTorch backend. No hardcoded metrics,
no fake devices, and no production import block.

The guard methods remain deny-only:
- no execution of payloads
- no exploitation network access
- no evidence mutation
- no governance bypass
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple
import hashlib
import math
import os
import re
import tempfile
import uuid

try:
    import psutil
except Exception:  # pragma: no cover - optional runtime dependency
    psutil = None

from . import g37_pytorch_backend as _pt_backend


class RealBackendNotConfiguredError(RuntimeError):
    """Raised when the real GPU backend contract is not provisioned."""


@dataclass(frozen=True)
class GPUConfig:
    """Infrastructure-gated GPU execution contract."""

    device_id: int
    memory_limit_gb: float
    mixed_precision: bool


class GPUBackend(Enum):
    """Available training backends."""

    CUDA = "CUDA"
    ROCM = "ROCM"
    CPU = "CPU"
    UNAVAILABLE = "UNAVAILABLE"

    @staticmethod
    def check_availability() -> Dict[str, Any]:
        """Report real CUDA availability without synthetic fallback."""

        torch_module = getattr(_pt_backend, "torch", None)
        if not getattr(_pt_backend, "PYTORCH_AVAILABLE", False) or torch_module is None:
            return {"available": False, "device_count": 0, "devices": []}

        cuda_module = getattr(torch_module, "cuda", None)
        if cuda_module is None:
            return {"available": False, "device_count": 0, "devices": []}

        available = bool(cuda_module.is_available())
        device_count = int(cuda_module.device_count())
        devices = [str(cuda_module.get_device_name(device_id)) for device_id in range(device_count)] if available else []
        return {
            "available": available,
            "device_count": device_count,
            "devices": devices,
        }

    @staticmethod
    def train(
        gpu_config: GPUConfig,
        training_config: _pt_backend.TrainingConfig,
        dataloader: Any,
    ) -> Any:
        """Fail closed unless a real CUDA-backed training contract is provisioned."""

        availability = GPUBackend.check_availability()
        if not availability["available"]:
            raise RealBackendNotConfiguredError(
                "GPU training requires CUDA. torch.cuda.is_available() returned False."
            )

        if not isinstance(gpu_config, GPUConfig) or not isinstance(training_config, _pt_backend.TrainingConfig):
            raise RealBackendNotConfiguredError(_pt_backend.PYTORCH_BACKEND_PROVISIONING_MESSAGE)

        if gpu_config.device_id < 0 or gpu_config.device_id >= availability["device_count"]:
            raise RealBackendNotConfiguredError(
                f"GPU device_id {gpu_config.device_id} is unavailable. Detected {availability['device_count']} CUDA device(s)."
            )

        return _pt_backend.PyTorchBackend().train(training_config, dataloader)


class TrainingObjective(Enum):
    """Closed training objectives exposed by the governor."""

    BUG_CLASSIFIER = "BUG_CLASSIFIER"
    DUPLICATE_DETECTOR = "DUPLICATE_DETECTOR"
    NOISE_FILTER = "NOISE_FILTER"
    CONFIDENCE_ESTIMATOR = "CONFIDENCE_ESTIMATOR"


@dataclass(frozen=True)
class GPUDeviceInfo:
    """Detected compute device information."""

    device_id: int
    name: str
    memory_total_mb: int
    memory_free_mb: int
    compute_capability: str
    backend: GPUBackend


@dataclass(frozen=True)
class FeatureVector:
    """Feature vector for real training/inference."""

    vector_id: str
    dimensions: int
    data_hash: str
    label: str
    source: str
    values: Tuple[float, ...]


@dataclass(frozen=True)
class TrainingConfig:
    """Training configuration."""

    config_id: str
    objective: TrainingObjective
    batch_size: int
    learning_rate: float
    epochs: int
    embedding_dim: int
    hidden_layers: Tuple[int, ...]
    dropout: float
    contrastive_margin: float


@dataclass(frozen=True)
class TrainingMetrics:
    """Metrics from a real training epoch."""

    epoch: int
    loss: float
    accuracy: float
    precision: float
    recall: float
    f1_score: float
    gpu_memory_used_mb: int
    time_seconds: float


@dataclass(frozen=True)
class ModelCheckpoint:
    """Saved checkpoint metadata."""

    checkpoint_id: str
    objective: TrainingObjective
    epoch: int
    loss: float
    accuracy: float
    model_hash: str
    created_at: str
    is_best: bool
    path: Optional[str] = None


@dataclass(frozen=True)
class InferenceResult:
    """Inference result from the trained model."""

    result_id: str
    prediction: str
    confidence: float
    embedding: Tuple[float, ...]
    inference_time_ms: float


@dataclass
class _TrainerState:
    model: Any
    optimizer: Any
    criterion: Any
    model_config: _pt_backend.ModelConfig
    device: Any


_TRAINER_STATES: Dict[str, _TrainerState] = {}
_CHECKPOINT_MODELS: Dict[str, Any] = {}
_CHECKPOINT_MODEL_CONFIGS: Dict[str, _pt_backend.ModelConfig] = {}


def _generate_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:16].upper()}"


def _hash_content(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()[:32]


def _require_runtime(operation: str) -> None:
    if not _pt_backend.PYTORCH_AVAILABLE:
        raise RuntimeError(f"PyTorch runtime is required for {operation}")


def _detect_backend_type() -> GPUBackend:
    if not _pt_backend.PYTORCH_AVAILABLE or _pt_backend.torch is None:
        return GPUBackend.UNAVAILABLE
    if _pt_backend.torch.cuda.is_available():
        if getattr(_pt_backend.torch.version, "hip", None):
            return GPUBackend.ROCM
        return GPUBackend.CUDA
    return GPUBackend.CPU


def detect_gpu_devices() -> Tuple[GPUDeviceInfo, ...]:
    """Detect the real compute device available to PyTorch."""

    backend = _detect_backend_type()
    if backend == GPUBackend.UNAVAILABLE:
        return (
            GPUDeviceInfo(
                device_id=0,
                name="PyTorch unavailable",
                memory_total_mb=0,
                memory_free_mb=0,
                compute_capability="unavailable",
                backend=GPUBackend.UNAVAILABLE,
            ),
        )

    if backend in (GPUBackend.CUDA, GPUBackend.ROCM):
        props = _pt_backend.torch.cuda.get_device_properties(0)
        total_mb = int(props.total_memory // (1024 * 1024))
        free_mb = max(
            0,
            total_mb - int(_pt_backend.torch.cuda.memory_allocated(0) // (1024 * 1024)),
        )
        return (
            GPUDeviceInfo(
                device_id=0,
                name=_pt_backend.torch.cuda.get_device_name(0),
                memory_total_mb=total_mb,
                memory_free_mb=free_mb,
                compute_capability=f"{props.major}.{props.minor}",
                backend=backend,
            ),
        )

    total_mb = 0
    free_mb = 0
    if psutil is not None:
        vm = psutil.virtual_memory()
        total_mb = int(vm.total // (1024 * 1024))
        free_mb = int(vm.available // (1024 * 1024))
    return (
        GPUDeviceInfo(
            device_id=0,
            name="CPU",
            memory_total_mb=total_mb,
            memory_free_mb=free_mb,
            compute_capability="cpu",
            backend=GPUBackend.CPU,
        ),
    )


def select_best_device(devices: Tuple[GPUDeviceInfo, ...]) -> GPUDeviceInfo:
    """Select the best available real device."""

    priorities = {
        GPUBackend.CUDA: 0,
        GPUBackend.ROCM: 1,
        GPUBackend.CPU: 2,
        GPUBackend.UNAVAILABLE: 3,
    }
    return sorted(devices, key=lambda device: priorities.get(device.backend, 99))[0]


def _tokenize(text: str) -> List[str]:
    return re.findall(r"[a-z0-9_]+", text.lower())


def _vectorize_fields(
    text_fields: Tuple[str, ...],
    numeric_fields: Tuple[float, ...],
    dimensions: int,
) -> Tuple[float, ...]:
    values = [0.0] * dimensions

    for field_index, field in enumerate(text_fields):
        for token in _tokenize(field):
            digest = hashlib.sha256(f"{field_index}:{token}".encode("utf-8")).digest()
            slot = int.from_bytes(digest[:2], "big") % dimensions
            sign = 1.0 if digest[2] % 2 == 0 else -1.0
            magnitude = 1.0 + (digest[3] / 255.0)
            values[slot] += sign * magnitude

    for index, numeric in enumerate(numeric_fields):
        values[index % dimensions] += float(numeric)

    norm = math.sqrt(sum(value * value for value in values))
    if norm > 0.0:
        values = [value / norm for value in values]
    return tuple(values)


def extract_bug_features(
    bug_text: str,
    bug_type: str,
    endpoint: str,
    response_delta: bool,
    reproduction_count: int,
) -> FeatureVector:
    """Extract a deterministic real feature vector from bug metadata."""

    dimensions = 256
    values = _vectorize_fields(
        (bug_text, bug_type, endpoint),
        (
            1.0 if response_delta else 0.0,
            float(reproduction_count),
            float(len(bug_text)),
            float(len(endpoint)),
        ),
        dimensions,
    )
    content = f"{bug_text}|{bug_type}|{endpoint}|{response_delta}|{reproduction_count}"
    return FeatureVector(
        vector_id=_generate_id("FV"),
        dimensions=dimensions,
        data_hash=_hash_content(content),
        label=bug_type,
        source="G33_VERIFIED",
        values=values,
    )


def extract_duplicate_features(
    report_a: str,
    report_b: str,
) -> Tuple[FeatureVector, FeatureVector]:
    """Extract deterministic real duplicate-comparison vectors."""

    dimensions = 256
    values_a = _vectorize_fields(
        (report_a, "report_a"),
        (float(len(report_a)),),
        dimensions,
    )
    values_b = _vectorize_fields(
        (report_b, "report_b"),
        (float(len(report_b)),),
        dimensions,
    )
    return (
        FeatureVector(
            vector_id=_generate_id("FV"),
            dimensions=dimensions,
            data_hash=_hash_content(report_a),
            label="REPORT_A",
            source="G34_DUPLICATE",
            values=values_a,
        ),
        FeatureVector(
            vector_id=_generate_id("FV"),
            dimensions=dimensions,
            data_hash=_hash_content(report_b),
            label="REPORT_B",
            source="G34_DUPLICATE",
            values=values_b,
        ),
    )


def create_training_config(
    objective: TrainingObjective,
    batch_size: int = 32,
    learning_rate: float = 0.001,
    epochs: int = 100,
) -> TrainingConfig:
    """Create training configuration."""

    return TrainingConfig(
        config_id=_generate_id("CFG"),
        objective=objective,
        batch_size=batch_size,
        learning_rate=learning_rate,
        epochs=epochs,
        embedding_dim=256,
        hidden_layers=(512, 256, 128),
        dropout=0.3,
        contrastive_margin=0.5,
    )


def _to_model_config(config: TrainingConfig) -> _pt_backend.ModelConfig:
    return _pt_backend.create_model_config(
        input_dim=config.embedding_dim,
        output_dim=2,
        hidden_dims=config.hidden_layers,
        dropout=config.dropout,
        learning_rate=config.learning_rate,
        batch_size=config.batch_size,
        epochs=config.epochs,
        seed=42,
    )


def _label_to_int(feature: FeatureVector, objective: TrainingObjective) -> int:
    label = feature.label.strip().upper()
    if objective == TrainingObjective.DUPLICATE_DETECTOR:
        return 1
    if label in {"INFO", "NOT_REAL", "FALSE_POSITIVE", "REJECTED", "NOISE", "BENIGN"}:
        return 0
    return 1


def _to_training_samples(
    features: Tuple[FeatureVector, ...],
    objective: TrainingObjective,
) -> Tuple[_pt_backend.TrainingSample, ...]:
    return tuple(
        _pt_backend.TrainingSample(
            sample_id=feature.vector_id,
            features=feature.values,
            label=_label_to_int(feature, objective),
            source=feature.source,
        )
        for feature in features
    )


def _build_trainer_state(config: TrainingConfig, device: GPUDeviceInfo) -> _TrainerState:
    _require_runtime("training")
    if _pt_backend.BugClassifier is None or _pt_backend.nn is None or _pt_backend.optim is None:
        raise RuntimeError("PyTorch model components are unavailable")

    model_config = _to_model_config(config)
    device_obj = _pt_backend.get_torch_device()
    if device_obj is None:
        raise RuntimeError("No compute device available for training")

    model = _pt_backend.BugClassifier(model_config).to(device_obj)
    optimizer = _pt_backend.optim.Adam(model.parameters(), lr=config.learning_rate)
    criterion = _pt_backend.nn.CrossEntropyLoss()
    return _TrainerState(
        model=model,
        optimizer=optimizer,
        criterion=criterion,
        model_config=model_config,
        device=device_obj,
    )


def _classification_metrics(
    model: Any,
    samples: Tuple[_pt_backend.TrainingSample, ...],
    device: Any,
) -> Tuple[float, float, float]:
    if not samples:
        return 0.0, 0.0, 0.0

    with _pt_backend.torch.no_grad():
        features = _pt_backend.torch.tensor(
            [list(sample.features) for sample in samples],
            dtype=_pt_backend.torch.float32,
            device=device,
        )
        labels = _pt_backend.torch.tensor(
            [sample.label for sample in samples],
            dtype=_pt_backend.torch.long,
            device=device,
        )
        outputs = model(features)
        predictions = _pt_backend.torch.argmax(outputs, dim=1)

    tp = int(((predictions == 1) & (labels == 1)).sum().item())
    fp = int(((predictions == 1) & (labels == 0)).sum().item())
    fn = int(((predictions == 0) & (labels == 1)).sum().item())

    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    if precision + recall == 0.0:
        f1_score = 0.0
    else:
        f1_score = 2.0 * precision * recall / (precision + recall)
    return precision, recall, f1_score


def _gpu_memory_used_mb(device: GPUDeviceInfo) -> int:
    if device.backend in (GPUBackend.CUDA, GPUBackend.ROCM):
        return int(_pt_backend.torch.cuda.max_memory_allocated() // (1024 * 1024))
    return 0


def gpu_train_epoch(
    device: GPUDeviceInfo,
    config: TrainingConfig,
    features: Tuple[FeatureVector, ...],
    epoch: int,
) -> TrainingMetrics:
    """Train one real epoch using the PyTorch backend."""

    if can_training_execute_payloads()[0]:  # pragma: no cover
        raise RuntimeError("SECURITY: Training cannot execute payloads")
    if not features:
        raise ValueError("At least one feature vector is required for training")

    state = _TRAINER_STATES.get(config.config_id)
    if state is None:
        state = _build_trainer_state(config, device)
        _TRAINER_STATES[config.config_id] = state

    samples = _to_training_samples(features, config.objective)
    epoch_metrics = _pt_backend.train_single_epoch(
        state.model,
        state.optimizer,
        state.criterion,
        samples,
        state.device,
        epoch,
    )
    precision, recall, f1_score = _classification_metrics(state.model, samples, state.device)

    return TrainingMetrics(
        epoch=epoch_metrics.epoch,
        loss=epoch_metrics.train_loss,
        accuracy=epoch_metrics.train_accuracy,
        precision=precision,
        recall=recall,
        f1_score=f1_score,
        gpu_memory_used_mb=_gpu_memory_used_mb(device),
        time_seconds=epoch_metrics.time_seconds,
    )


def gpu_train_full(
    device: GPUDeviceInfo,
    config: TrainingConfig,
    features: Tuple[FeatureVector, ...],
) -> Tuple[TrainingMetrics, ...]:
    """Run a full real training session."""

    _TRAINER_STATES.pop(config.config_id, None)
    metrics: List[TrainingMetrics] = []
    for epoch in range(1, config.epochs + 1):
        epoch_metrics = gpu_train_epoch(device, config, features, epoch)
        metrics.append(epoch_metrics)
        if epoch_metrics.accuracy >= 0.97:
            break
    return tuple(metrics)


def save_checkpoint(
    config: TrainingConfig,
    metrics: TrainingMetrics,
    is_best: bool = False,
) -> ModelCheckpoint:
    """Persist the trained model checkpoint to a temp directory."""

    state = _TRAINER_STATES.get(config.config_id)
    if state is None:
        raise RuntimeError("No trained model available for this configuration")

    checkpoint_dir = os.path.join(tempfile.gettempdir(), "ygb_g37")
    os.makedirs(checkpoint_dir, exist_ok=True)
    path = os.path.join(checkpoint_dir, f"{config.config_id}_{metrics.epoch}.pt")

    epoch_metrics = _pt_backend.EpochMetrics(
        epoch=metrics.epoch,
        train_loss=metrics.loss,
        train_accuracy=metrics.accuracy,
        val_loss=metrics.loss,
        val_accuracy=metrics.accuracy,
        learning_rate=config.learning_rate,
        time_seconds=metrics.time_seconds,
    )
    backend_checkpoint = _pt_backend.save_model_checkpoint(
        state.model,
        state.model_config,
        epoch_metrics,
        path,
    )

    checkpoint = ModelCheckpoint(
        checkpoint_id=_generate_id("CKPT"),
        objective=config.objective,
        epoch=metrics.epoch,
        loss=metrics.loss,
        accuracy=metrics.accuracy,
        model_hash=backend_checkpoint.model_hash,
        created_at=backend_checkpoint.created_at,
        is_best=is_best,
        path=backend_checkpoint.path,
    )
    _CHECKPOINT_MODELS[checkpoint.checkpoint_id] = state.model
    _CHECKPOINT_MODEL_CONFIGS[checkpoint.checkpoint_id] = state.model_config
    return checkpoint


def _load_checkpoint_model(checkpoint: ModelCheckpoint) -> Tuple[Any, _pt_backend.ModelConfig]:
    model = _CHECKPOINT_MODELS.get(checkpoint.checkpoint_id)
    model_config = _CHECKPOINT_MODEL_CONFIGS.get(checkpoint.checkpoint_id)

    if model is not None and model_config is not None:
        return model, model_config

    if not checkpoint.path or model_config is None:
        raise RuntimeError("Checkpoint model is unavailable")

    model, _ = _pt_backend.load_model_checkpoint(model_config, checkpoint.path)
    _CHECKPOINT_MODELS[checkpoint.checkpoint_id] = model
    return model, model_config


def gpu_infer(
    device: GPUDeviceInfo,
    checkpoint: ModelCheckpoint,
    feature: FeatureVector,
) -> InferenceResult:
    """Run real inference using the stored checkpoint model."""

    model, _ = _load_checkpoint_model(checkpoint)
    sample = _to_training_samples((feature,), checkpoint.objective)[0]
    backend_result = _pt_backend.infer_single(model, sample)
    return InferenceResult(
        result_id=_generate_id("INF"),
        prediction="REAL" if backend_result.prediction == 1 else "NOT_REAL",
        confidence=backend_result.confidence,
        embedding=feature.values[:8],
        inference_time_ms=backend_result.inference_time_ms,
    )


def gpu_batch_infer(
    device: GPUDeviceInfo,
    checkpoint: ModelCheckpoint,
    features: Tuple[FeatureVector, ...],
) -> Tuple[InferenceResult, ...]:
    """Run real inference for a batch of features."""

    return tuple(gpu_infer(device, checkpoint, feature) for feature in features)


def compute_similarity(
    embedding_a: Tuple[float, ...],
    embedding_b: Tuple[float, ...],
) -> float:
    """Compute cosine similarity in the [0, 1] range."""

    if not embedding_a or not embedding_b:
        return 0.0

    length = min(len(embedding_a), len(embedding_b))
    dot = sum(embedding_a[i] * embedding_b[i] for i in range(length))
    norm_a = math.sqrt(sum(value * value for value in embedding_a[:length]))
    norm_b = math.sqrt(sum(value * value for value in embedding_b[:length]))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0

    cosine = max(-1.0, min(1.0, dot / (norm_a * norm_b)))
    return (cosine + 1.0) / 2.0


def contrastive_loss(
    anchor: FeatureVector,
    positive: FeatureVector,
    negative: FeatureVector,
    margin: float = 0.5,
) -> float:
    """Compute a real contrastive hinge loss from feature embeddings."""

    positive_distance = 1.0 - compute_similarity(anchor.values, positive.values)
    negative_distance = 1.0 - compute_similarity(anchor.values, negative.values)
    return max(0.0, positive_distance - negative_distance + margin)


def prepare_incremental_batch(
    new_verified: Tuple[FeatureVector, ...],
    new_rejected: Tuple[FeatureVector, ...],
    new_duplicates: Tuple[FeatureVector, ...],
) -> Tuple[FeatureVector, ...]:
    """Prepare a real incremental batch."""

    return new_verified + new_rejected + new_duplicates


def incremental_update(
    device: GPUDeviceInfo,
    checkpoint: ModelCheckpoint,
    new_features: Tuple[FeatureVector, ...],
    learning_rate: float = 0.0001,
) -> TrainingMetrics:
    """Fine-tune an existing checkpoint for one real epoch."""

    if not new_features:
        raise ValueError("At least one feature vector is required for incremental update")

    model, model_config = _load_checkpoint_model(checkpoint)
    optimizer = _pt_backend.optim.Adam(model.parameters(), lr=learning_rate)
    criterion = _pt_backend.nn.CrossEntropyLoss()
    samples = _to_training_samples(new_features, checkpoint.objective)

    epoch_metrics = _pt_backend.train_single_epoch(
        model,
        optimizer,
        criterion,
        samples,
        _pt_backend.get_torch_device(),
        1,
    )
    precision, recall, f1_score = _classification_metrics(
        model,
        samples,
        _pt_backend.get_torch_device(),
    )
    _CHECKPOINT_MODELS[checkpoint.checkpoint_id] = model

    return TrainingMetrics(
        epoch=epoch_metrics.epoch,
        loss=epoch_metrics.train_loss,
        accuracy=epoch_metrics.train_accuracy,
        precision=precision,
        recall=recall,
        f1_score=f1_score,
        gpu_memory_used_mb=_gpu_memory_used_mb(device),
        time_seconds=epoch_metrics.time_seconds,
    )


def can_training_execute_payloads() -> Tuple[bool, str]:
    return False, "Training cannot execute payloads - read-only data access"


def can_training_access_network() -> Tuple[bool, str]:
    return False, "Training cannot access network for exploitation - data only"


def can_training_modify_evidence() -> Tuple[bool, str]:
    return False, "Training cannot modify evidence - read-only"


def can_training_bypass_governance() -> Tuple[bool, str]:
    return False, "Training cannot bypass governance - governance absolute"


def can_inference_approve_bugs() -> Tuple[bool, str]:
    return False, "Inference cannot approve bugs - advisory only"


def can_inference_submit_reports() -> Tuple[bool, str]:
    return False, "Inference cannot submit reports - human submission required"
