"""Incremental training loop for new ingestion samples."""

from __future__ import annotations

import json
import hashlib
import logging
import math
import os
import re
import time
from contextlib import nullcontext
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import inspect
from typing import Callable, Protocol

import numpy as np
import torch
from sklearn.metrics import accuracy_score, f1_score, precision_score, recall_score, roc_auc_score
from torch.optim import AdamW
from torch.utils.data import DataLoader, Dataset

from backend.ingestion._integrity import log_module_sha256
from backend.bridge.bridge_state import get_bridge_state
from backend.ingestion.normalizer import SampleQualityScorer
from backend.ingestion.models import IngestedSample
from backend.observability.metrics import metrics_registry
from backend.training.adaptive_learner import get_adaptive_learner
from backend.training.class_balancer import ClassBalanceReport, ClassBalancer
from backend.training.feature_extractor import CVEFeatureEngineer, extract
from backend.training.metrics_tracker import MetricsReport, MetricsTracker
from backend.training.model_thresholds import (
    calibrate_positive_threshold,
    compute_binary_metrics,
    load_threshold_artifact,
    save_threshold_artifact,
)
from backend.training.safetensors_store import SafetensorsFeatureStore
from backend.training.state_manager import TrainingMetrics, get_training_state_manager
from backend.training.rl_feedback import get_reward_buffer
from backend.training.training_optimizer import (
    EarlyStopping,
    HardNegativeMiner,
    TrainingOptimiserConfig,
    WarmupCosineScheduler,
)
from impl_v1.phase49.governors.g37_pytorch_backend import (
    BugClassifier,
    ModelConfig,
    create_model_config,
)
from impl_v1.phase49.governors.g38_self_trained_model import can_ai_execute
from training.safetensors_io import load_safetensors, save_safetensors

logger = logging.getLogger("ygb.training.incremental_trainer")

DEFAULT_MODEL_PATH = Path("checkpoints/g38_model_checkpoint.safetensors")
DEFAULT_STATE_PATH = Path("checkpoints/training_state.json")
DEFAULT_BASELINE_PATH = Path("checkpoints/baseline_accuracy.json")
DEFAULT_RAW_DATA_ROOT = Path("data/raw")
DEFAULT_DATASET_INDEX_PATH = Path("checkpoints/raw_data_index.json")
DEFAULT_FEATURE_CACHE_ROOT = Path("checkpoints/feature_cache")
DEFAULT_FEATURE_STORE_ROOT = Path("training/features_safetensors")
DEFAULT_INCREMENTAL_FEATURE_STORE_ROOT = Path(
    "checkpoints/incremental_features_safetensors"
)
MODEL_INPUT_DIM = 512
_IMPACT_RE = re.compile(r"CVSS:(?P<score>[0-9.]+)\|(?P<severity>[^|]+)")
_CVE_ID_RE = re.compile(r"^CVE-\d{4}-\d{4,}$", re.IGNORECASE)
_DEFAULT_COMPAT_FEATURE_EXTRACTOR = extract
_RL_WEIGHT_OFFSET = 1.0
_RL_WEIGHT_FLOOR = 0.1


class AccuracyThresholds:
    MIN_F1 = 0.75
    MIN_PRECISION = 0.70
    MIN_RECALL = 0.65
    MAX_DROP_FROM_BEST = 0.05


@dataclass(frozen=True)
class AccuracySnapshot:
    epoch: int
    accuracy: float
    precision: float
    recall: float
    f1: float
    auc_roc: float
    taken_at: str


class AccuracyHistory:
    def __init__(self) -> None:
        self._snapshots: list[AccuracySnapshot] = []

    def add(self, snapshot: AccuracySnapshot) -> None:
        self._snapshots.append(snapshot)

    def get_best(self) -> AccuracySnapshot:
        if not self._snapshots:
            raise ValueError("accuracy history is empty")
        return max(self._snapshots, key=lambda snapshot: snapshot.f1)

    def get_last(self) -> AccuracySnapshot:
        if not self._snapshots:
            raise ValueError("accuracy history is empty")
        return self._snapshots[-1]

    def should_rollback(self) -> bool:
        if len(self._snapshots) < 2:
            return False
        best_snapshot = self.get_best()
        last_snapshot = self.get_last()
        return (
            best_snapshot.f1 - last_snapshot.f1
        ) > AccuracyThresholds.MAX_DROP_FROM_BEST

    def as_list(self) -> list[AccuracySnapshot]:
        return list(self._snapshots)


@dataclass(frozen=True)
class EpochResult:
    accuracy: float
    precision: float
    recall: float
    f1: float
    eval_loss: float
    samples_processed: int
    epoch_number: int
    rollback: bool
    early_stopped: bool
    prediction_hash: str = ""
    status: str = "COMPLETED"
    metrics_report: MetricsReport | None = None


TrainingResult = EpochResult


@dataclass(frozen=True)
class TrainingLoopResult:
    train_loss: float
    eval_loss: float
    accuracy: float
    precision: float
    recall: float
    f1: float
    auc_roc: float
    positive_threshold: float
    threshold_strategy: str
    predictions: list[int]
    labels: list[int]
    probability_rows: list[list[float]]
    hard_negative_indices: list[int]
    epochs_completed: int
    early_stopped: bool
    metrics_report: MetricsReport | None = None


@dataclass(frozen=True)
class DatasetQualityReport:
    passed: bool
    sample_count: int
    mean_quality_score: float
    unique_cves: int
    severity_distribution: dict[str, float]
    failed_reasons: list[str]


class DatasetQualityError(RuntimeError):
    """Raised when dataset quality validation fails before training."""

    def __init__(self, failed_reasons: list[str]) -> None:
        self.failed_reasons = [str(reason) for reason in failed_reasons]
        super().__init__(
            "; ".join(self.failed_reasons)
            if self.failed_reasons
            else "dataset quality validation failed"
        )


class DatasetQualityGate:
    MIN_SAMPLES = 100
    MIN_QUALITY_SCORE = 0.4
    MIN_UNIQUE_CVES = 50
    MIN_SEVERITY_DISTRIBUTION = {
        "CRITICAL": 0.02,
        "HIGH": 0.05,
        "MEDIUM": 0.05,
        "LOW": 0.01,
        "INFORMATIONAL": 0.0,
    }
    QUORUM_UNKNOWN = "QUORUM_UNKNOWN"
    _SEVERITY_CLASSES = (
        "CRITICAL",
        "HIGH",
        "MEDIUM",
        "LOW",
        "INFORMATIONAL",
    )

    def __init__(
        self,
        *,
        feature_loader: Callable[[IngestedSample], torch.Tensor] | None = None,
    ) -> None:
        self._feature_loader = feature_loader

    @staticmethod
    def _coerce_payload(
        sample: dict[str, object] | IngestedSample,
    ) -> dict[str, object]:
        if isinstance(sample, IngestedSample):
            return SampleQualityScorer._coerce_sample(sample)
        if isinstance(sample, dict):
            return dict(sample)
        raise TypeError(
            "dataset quality validation requires dict or IngestedSample entries"
        )

    @staticmethod
    def _canonical_severity(raw_severity: object) -> str:
        severity = str(raw_severity or "").strip().upper()
        if severity == "INFO":
            return "INFORMATIONAL"
        return severity

    @classmethod
    def _score_sample(cls, sample: dict[str, object] | IngestedSample) -> float:
        payload = cls._coerce_payload(sample)
        explicit_quality_score = payload.get("quality_score")
        if explicit_quality_score not in (None, ""):
            score = float(explicit_quality_score)
            if not math.isfinite(score):
                raise ValueError("quality_score is not finite")
            return score

        text = SampleQualityScorer._extract_text(payload)
        text_length = len(text)
        if text_length <= 1:
            text_length_score = 0.0
        else:
            text_length_score = SampleQualityScorer._clamp(
                math.log(text_length) / math.log(2000)
            )
        has_cvss_score = 1.0 if payload.get("cvss_score") not in (None, "") else 0.0
        has_exploit_info = SampleQualityScorer._exploit_info_score(payload)
        source_trust_score = SampleQualityScorer._source_trust_score(payload)
        return (
            text_length_score
            + has_cvss_score
            + has_exploit_info
            + source_trust_score
        ) / 4.0

    def validate(
        self, samples: list[dict[str, object] | IngestedSample]
    ) -> DatasetQualityReport:
        sample_count = len(samples)
        failed_reasons: list[str] = []
        quality_scores: list[float] = []
        unique_cves: set[str] = set()
        severity_counts = {severity: 0 for severity in self._SEVERITY_CLASSES}

        for index, sample in enumerate(samples):
            try:
                payload = self._coerce_payload(sample)
            except TypeError as exc:
                failed_reasons.append(f"sample_payload_invalid[{index}]: {exc}")
                continue

            cve_id = str(payload.get("cve_id", "") or "").strip().upper()
            if cve_id:
                unique_cves.add(cve_id)

            severity = self._canonical_severity(payload.get("severity", ""))
            if severity in severity_counts:
                severity_counts[severity] += 1

            try:
                quality_scores.append(self._score_sample(payload))
            except (TypeError, ValueError) as exc:
                failed_reasons.append(f"quality_score_invalid[{index}]: {exc}")

            if self._feature_loader is not None and isinstance(sample, IngestedSample):
                try:
                    feature_tensor = self._feature_loader(sample)
                except RuntimeError as exc:
                    failed_reasons.append(f"feature_tensor_load_failed[{index}]: {exc}")
                    continue
                if torch.isnan(feature_tensor).any().item():
                    failed_reasons.append(f"feature_tensor_nan[{index}]")
                if torch.isinf(feature_tensor).any().item():
                    failed_reasons.append(f"feature_tensor_inf[{index}]")

        mean_quality_score = (
            float(sum(quality_scores) / len(quality_scores)) if quality_scores else 0.0
        )
        unique_cve_count = len(unique_cves)
        severity_distribution = {
            severity: (
                float(count) / float(sample_count) if sample_count > 0 else 0.0
            )
            for severity, count in severity_counts.items()
        }

        if sample_count < self.MIN_SAMPLES:
            failed_reasons.append(
                f"sample_count_below_min:{sample_count}<{self.MIN_SAMPLES}"
            )
        if mean_quality_score < self.MIN_QUALITY_SCORE:
            failed_reasons.append(
                "mean_quality_below_min:"
                f"{mean_quality_score:.4f}<{self.MIN_QUALITY_SCORE:.4f}"
            )
        if unique_cve_count < self.MIN_UNIQUE_CVES:
            failed_reasons.append(
                f"unique_cves_below_min:{unique_cve_count}<{self.MIN_UNIQUE_CVES}"
            )
        blocking_reasons = list(failed_reasons)
        for severity in self._SEVERITY_CLASSES:
            minimum_distribution = float(
                self.MIN_SEVERITY_DISTRIBUTION.get(severity, 0.0)
            )
            if severity_counts[severity] == 0 and sample_count < 20:
                failed_reasons.append(f"{self.QUORUM_UNKNOWN}:{severity}=0")
                continue
            if severity_distribution[severity] < minimum_distribution:
                failed_reasons.append(
                    "severity_distribution_below_min:"
                    f"{severity}={severity_distribution[severity]:.4f}"
                )
                blocking_reasons.append(
                    "severity_distribution_below_min:"
                    f"{severity}={severity_distribution[severity]:.4f}"
                )

        return DatasetQualityReport(
            passed=not blocking_reasons,
            sample_count=sample_count,
            mean_quality_score=mean_quality_score,
            unique_cves=unique_cve_count,
            severity_distribution=severity_distribution,
            failed_reasons=failed_reasons,
        )

    def validate_arrays(
        self,
        features: np.ndarray,
        labels: np.ndarray,
        sample_count: int,
    ) -> DatasetQualityReport:
        feature_array = np.asarray(features)
        label_array = np.asarray(labels)
        effective_sample_count = int(sample_count)
        failed_reasons: list[str] = []
        quality_scores: list[float] = []
        unique_feature_hashes: set[str] = set()

        if effective_sample_count < 0:
            failed_reasons.append(
                f"sample_count_invalid:{effective_sample_count}<0"
            )
            effective_sample_count = 0

        if feature_array.ndim != 2:
            failed_reasons.append(
                f"feature_array_shape_invalid:{tuple(feature_array.shape)}"
            )
        if label_array.ndim != 1:
            failed_reasons.append(
                f"label_array_shape_invalid:{tuple(label_array.shape)}"
            )
        if feature_array.ndim == 2 and feature_array.shape[0] != effective_sample_count:
            failed_reasons.append(
                "feature_sample_count_mismatch:"
                f"{feature_array.shape[0]}!={effective_sample_count}"
            )
        if label_array.ndim == 1 and label_array.shape[0] != effective_sample_count:
            failed_reasons.append(
                "label_sample_count_mismatch:"
                f"{label_array.shape[0]}!={effective_sample_count}"
            )
        if not np.issubdtype(label_array.dtype, np.integer):
            failed_reasons.append(f"label_dtype_invalid:{label_array.dtype}")

        rows_to_validate = 0
        if feature_array.ndim == 2 and label_array.ndim == 1:
            rows_to_validate = min(
                feature_array.shape[0],
                label_array.shape[0],
                effective_sample_count,
            )

        for index in range(rows_to_validate):
            feature_row = np.asarray(feature_array[index], dtype=np.float32)
            row_quality = 1.0
            if feature_row.size == 0:
                failed_reasons.append(f"feature_array_invalid[{index}]: empty_row")
                row_quality = 0.0
            elif not np.isfinite(feature_row).all():
                failed_reasons.append(f"feature_array_invalid[{index}]: non_finite")
                row_quality = 0.0
            elif np.all(feature_row == 0.0):
                failed_reasons.append(f"feature_array_invalid[{index}]: all_zero")
                row_quality = 0.0
            elif float(np.var(feature_row)) <= 0.0:
                failed_reasons.append(
                    f"feature_array_invalid[{index}]: zero_variance"
                )
                row_quality = 0.0
            quality_scores.append(row_quality)
            unique_feature_hashes.add(
                hashlib.sha256(
                    np.ascontiguousarray(feature_row).tobytes()
                ).hexdigest()
            )

        mean_quality_score = (
            float(sum(quality_scores) / effective_sample_count)
            if effective_sample_count > 0
            else 0.0
        )
        unique_cve_count = len(unique_feature_hashes)

        severity_distribution: dict[str, float]
        if label_array.ndim == 1 and np.issubdtype(label_array.dtype, np.integer):
            effective_labels = [int(value) for value in label_array[:rows_to_validate].tolist()]
            if set(effective_labels).issubset({0, 1}):
                label_aliases = {0: "NEGATIVE", 1: "POSITIVE"}
                expected_labels = (0, 1)
            else:
                expected_labels = tuple(sorted(set(effective_labels)))
                label_aliases = {
                    label_value: f"LABEL_{label_value}"
                    for label_value in expected_labels
                }
            severity_distribution = {
                label_aliases[label_value]: (
                    float(sum(1 for entry in effective_labels if entry == label_value))
                    / float(effective_sample_count)
                    if effective_sample_count > 0
                    else 0.0
                )
                for label_value in expected_labels
            }
        else:
            severity_distribution = {}

        if effective_sample_count < self.MIN_SAMPLES:
            failed_reasons.append(
                f"sample_count_below_min:{effective_sample_count}<{self.MIN_SAMPLES}"
            )
        if mean_quality_score < self.MIN_QUALITY_SCORE:
            failed_reasons.append(
                "mean_quality_below_min:"
                f"{mean_quality_score:.4f}<{self.MIN_QUALITY_SCORE:.4f}"
            )
        if unique_cve_count < self.MIN_UNIQUE_CVES:
            failed_reasons.append(
                f"unique_cves_below_min:{unique_cve_count}<{self.MIN_UNIQUE_CVES}"
            )
        for label_name, distribution in severity_distribution.items():
            minimum_distribution = float(
                self.MIN_SEVERITY_DISTRIBUTION.get(label_name, 0.1)
            )
            if distribution < minimum_distribution:
                failed_reasons.append(
                    "severity_distribution_below_min:"
                    f"{label_name}={distribution:.4f}"
                )

        return DatasetQualityReport(
            passed=not failed_reasons,
            sample_count=effective_sample_count,
            mean_quality_score=mean_quality_score,
            unique_cves=unique_cve_count,
            severity_distribution=severity_distribution,
            failed_reasons=failed_reasons,
        )


class _StreamingFeatureDataset(Dataset):
    """Lazy real-data dataset backed by extracted or cached features."""

    def __init__(
        self,
        trainer: "IncrementalTrainer",
        samples: list[IngestedSample],
        indices: list[int],
        *,
        return_dataset_index: bool = False,
    ) -> None:
        self._trainer = trainer
        self._samples = samples
        self._indices = tuple(indices)
        self._return_dataset_index = bool(return_dataset_index)

    def __len__(self) -> int:
        return len(self._indices)

    @property
    def sample_indices(self) -> tuple[int, ...]:
        return self._indices

    def __getitem__(self, item: int) -> tuple[torch.Tensor, torch.Tensor]:
        sample = self._samples[self._indices[item]]
        features = self._trainer._load_or_compute_feature(sample)
        is_valid, reason = self._trainer._validate_feature_tensor(features)
        if not is_valid:
            self._trainer._record_invalid_sample(sample, reason)
            raise RuntimeError(
                f"REAL_DATA_REQUIRED: invalid feature tensor for {sample.sha256_hash} ({reason})"
            )
        label = torch.tensor(self._trainer._label_for_sample(sample), dtype=torch.long)
        if self._return_dataset_index:
            return features, label, torch.tensor(item, dtype=torch.long)
        return features, label


class InvalidationSource(Protocol):
    def get_changed_dirs(self) -> set[Path]:
        ...


class DirectoryMtimeSource:
    def __init__(self, raw_data_root: Path, cached_directories: dict[str, object] | None = None) -> None:
        self._raw_data_root = raw_data_root
        self._cached_directories = cached_directories if isinstance(cached_directories, dict) else {}

    def _iter_candidate_sample_dirs(self) -> list[Path]:
        if not self._raw_data_root.exists():
            return []
        candidate_dirs: list[Path] = [self._raw_data_root]
        try:
            source_dirs = sorted(path for path in self._raw_data_root.iterdir() if path.is_dir())
        except OSError:
            return candidate_dirs
        for source_dir in source_dirs:
            candidate_dirs.append(source_dir)
            try:
                child_dirs = sorted(path for path in source_dir.iterdir() if path.is_dir())
            except OSError:
                continue
            candidate_dirs.extend(child_dirs)
        return candidate_dirs

    def get_changed_dirs(self) -> set[Path]:
        changed_dirs: set[Path] = set()
        for candidate_dir in self._iter_candidate_sample_dirs():
            try:
                dir_stat = candidate_dir.stat()
            except OSError:
                changed_dirs.add(candidate_dir)
                continue
            cached_mtime = self._cached_directories.get(str(candidate_dir))
            if cached_mtime != dir_stat.st_mtime_ns:
                changed_dirs.add(candidate_dir)
        return changed_dirs


class IncrementalTrainer:
    def __init__(
        self,
        model_path: str | Path = DEFAULT_MODEL_PATH,
        state_path: str | Path = DEFAULT_STATE_PATH,
        baseline_path: str | Path = DEFAULT_BASELINE_PATH,
        raw_data_root: str | Path = DEFAULT_RAW_DATA_ROOT,
        dataset_index_path: str | Path | None = None,
        feature_cache_root: str | Path | None = None,
        num_workers: int = 4,
        feature_store_root: str | Path | None = None,
    ) -> None:
        self.model_path = Path(model_path)
        self.state_path = Path(state_path)
        self.baseline_path = Path(baseline_path)
        self.raw_data_root = Path(raw_data_root)
        self.feature_engineer = CVEFeatureEngineer(raw_data_root=self.raw_data_root)
        self.dataset_index_path = (
            Path(dataset_index_path)
            if dataset_index_path is not None
            else self.state_path.parent / DEFAULT_DATASET_INDEX_PATH.name
        )
        self.feature_cache_root = (
            Path(feature_cache_root)
            if feature_cache_root is not None
            else self.state_path.parent / DEFAULT_FEATURE_CACHE_ROOT.name
        )
        self.num_workers = num_workers
        project_root = self.state_path.parent.parent
        self.feature_store_root = (
            Path(feature_store_root)
            if feature_store_root is not None
            else project_root / DEFAULT_INCREMENTAL_FEATURE_STORE_ROOT
        )
        self.feature_store = SafetensorsFeatureStore(
            self.feature_store_root,
            feature_dim=self.feature_engineer.output_dim,
        )
        self._indexed_raw_samples_cache: list[tuple[str, IngestedSample]] | None = None
        self._invalid_sample_warnings: set[str] = set()
        self._invalid_sample_count: int = 0
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.model_config = create_model_config(
            input_dim=MODEL_INPUT_DIM,
            output_dim=2,
            hidden_dims=(1024, 512, 256, 128),
            dropout=0.3,
            learning_rate=3e-4,
            batch_size=256,
            epochs=1,
            seed=42,
        )
        self.optimizer_config = TrainingOptimiserConfig(
            learning_rate=float(self.model_config.learning_rate),
            max_epochs=max(int(self.model_config.epochs), 5),
            shuffle_seed=int(self.model_config.seed),
            accumulation_steps=1,
        )
        self.training_state = self._load_training_state()
        self.baseline_state = self._load_baseline_state()
        self.baseline_accuracy = float(self.baseline_state["baseline_accuracy"])
        self.positive_threshold = float(self.baseline_state["positive_threshold"])
        self.state_manager = get_training_state_manager()
        self.model = self._load_or_initialize_model()
        checkpoint_root = self.state_path.parent
        self.adaptive_learner = get_adaptive_learner(
            state_path=checkpoint_root / "adaptive_learning_state.json",
            ewc_state_path=checkpoint_root / "adaptive_ewc_state.safetensors",
        )
        self.adaptive_learner.attach_model(self.model)
        self.dataset_quality_gate = DatasetQualityGate(
            feature_loader=self._load_or_compute_feature
        )
        self._last_dataset_quality_report: DatasetQualityReport | None = None
        self._accuracy_history = AccuracyHistory()
        self._last_epoch_mean_ewc_loss = 0.0
        self.class_balancer = ClassBalancer()
        self.metrics_tracker = MetricsTracker(
            label_names={0: "NEGATIVE", 1: "POSITIVE"}
        )
        self._last_balance_report: ClassBalanceReport | None = None
        self._last_metrics_report: MetricsReport | None = None
        self._reward_buffer = get_reward_buffer()

    def _load_training_state(self) -> dict[str, object]:
        if not self.state_path.exists():
            self._atomic_write_json(
                self.state_path,
                {
                    "last_training_time": datetime.fromtimestamp(
                        0, timezone.utc
                    ).isoformat(),
                    "epoch_number": 0,
                    "best_eval_loss": None,
                    "no_improve_count": 0,
                },
            )
        return json.loads(self.state_path.read_text(encoding="utf-8"))

    def _load_baseline_state(self) -> dict[str, object]:
        payload = load_threshold_artifact(self.baseline_path)
        if not self.baseline_path.exists():
            self._atomic_write_json(self.baseline_path, payload)
        return payload

    def _atomic_write_json(self, path: Path, payload: object) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = path.with_suffix(f"{path.suffix}.tmp")
        temp_path.write_text(
            json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8"
        )
        os.replace(temp_path, path)

    @staticmethod
    def _sample_to_payload(sample: IngestedSample) -> dict[str, object]:
        return {
            "source": sample.source,
            "raw_text": sample.raw_text,
            "url": sample.url,
            "cve_id": sample.cve_id,
            "severity": sample.severity,
            "tags": list(sample.tags),
            "ingested_at": sample.ingested_at.isoformat(),
            "sha256_hash": sample.sha256_hash,
            "token_count": sample.token_count,
            "lang": sample.lang,
        }

    def _feature_cache_path(self, sample: IngestedSample) -> Path:
        return self.feature_store.shard_path(sample.sha256_hash)

    def _write_feature_cache(self, path: Path, feature: torch.Tensor) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = path.with_suffix(f"{path.suffix}.tmp")
        with open(temp_path, "wb") as handle:
            np.save(handle, feature.detach().cpu().numpy(), allow_pickle=False)
        os.replace(temp_path, path)

    @staticmethod
    def _compress_feature_tensor(feature: torch.Tensor) -> np.ndarray:
        feature_cpu = feature.detach().cpu().to(dtype=torch.float32).reshape(-1)
        if tuple(feature_cpu.shape) != (CVEFeatureEngineer.FEATURE_DIM,):
            raise RuntimeError(
                "REAL_DATA_REQUIRED: feature tensor must have shape "
                f"({CVEFeatureEngineer.FEATURE_DIM},), got {tuple(feature_cpu.shape)}"
            )
        return feature_cpu.numpy().astype(np.float32, copy=False).reshape(
            1, CVEFeatureEngineer.FEATURE_DIM
        )

    @staticmethod
    def _expand_feature_tensor(stored_feature: np.ndarray) -> torch.Tensor:
        feature_row = np.asarray(stored_feature)
        if (
            feature_row.dtype != np.float32
            or feature_row.shape != (CVEFeatureEngineer.FEATURE_DIM,)
        ):
            raise ValueError(
                "stored feature row must have shape "
                f"({CVEFeatureEngineer.FEATURE_DIM},) and dtype float32, got "
                f"{feature_row.shape}/{feature_row.dtype}"
            )
        return torch.from_numpy(feature_row.copy())

    @staticmethod
    def _expand_to_model_feature(feature: torch.Tensor) -> torch.Tensor:
        feature_cpu = feature.detach().cpu().to(dtype=torch.float32).reshape(-1)
        if tuple(feature_cpu.shape) == (MODEL_INPUT_DIM,):
            return feature_cpu
        if tuple(feature_cpu.shape) == (CVEFeatureEngineer.FEATURE_DIM,):
            expanded = torch.zeros(MODEL_INPUT_DIM, dtype=torch.float32)
            expanded[: CVEFeatureEngineer.FEATURE_DIM] = feature_cpu
            return expanded
        if tuple(feature_cpu.shape) == (256,):
            expanded = torch.repeat_interleave(feature_cpu, 2).to(dtype=torch.float32)
            if tuple(expanded.shape) != (MODEL_INPUT_DIM,):
                raise RuntimeError(
                    f"REAL_DATA_REQUIRED: legacy expanded feature must have shape ({MODEL_INPUT_DIM},), got {tuple(expanded.shape)}"
                )
            return expanded
        raise RuntimeError(
            "REAL_DATA_REQUIRED: unsupported feature tensor shape "
            f"{tuple(feature_cpu.shape)}"
        )

    def _feature_store_metadata(
        self,
        sample: IngestedSample,
        stats_payload: dict[str, object],
    ) -> dict[str, object]:
        return {
            "sample_sha256": sample.sha256_hash,
            "sample_source": sample.source,
            "sample_cve_id": sample.cve_id,
            "sample_severity": sample.severity,
            "sample_ingested_at": sample.ingested_at.isoformat(),
            "sample_token_count": sample.token_count,
            "label": self._label_for_sample(sample),
            "original_feature_dim": int(stats_payload.get("source_feature_dim", 0)),
            "stored_feature_dim": CVEFeatureEngineer.FEATURE_DIM,
            "model_input_dim": MODEL_INPUT_DIM,
            "compression": "none",
            "stats": stats_payload,
        }

    def _load_feature_from_store(
        self,
        sample: IngestedSample,
        cache_path: Path,
    ) -> torch.Tensor | None:
        if not cache_path.exists():
            return None

        try:
            shard = self.feature_store.read(sample.sha256_hash)
            stats_available = isinstance(shard.metadata.get("stats"), dict)
            if (
                shard.features.shape != (1, CVEFeatureEngineer.FEATURE_DIM)
                or not stats_available
            ):
                logger.warning(
                    "feature_cache_invalid",
                    extra={
                        "event": "feature_cache_invalid",
                        "path": str(cache_path),
                        "shape": tuple(shard.features.shape),
                        "stats_present": stats_available,
                    },
                )
                return None
            cached_feature = self._expand_feature_tensor(shard.features[0])
            return self._expand_to_model_feature(cached_feature)
        except (FileNotFoundError, OSError, ValueError, TypeError) as exc:
            logger.warning(
                "feature_cache_unavailable",
                extra={
                    "event": "feature_cache_unavailable",
                    "path": str(cache_path),
                    "reason": type(exc).__name__,
                },
            )
            return None

    @staticmethod
    def _normalize_feature_tensor(
        feature: torch.Tensor,
    ) -> tuple[torch.Tensor, dict[str, object]]:
        feature_cpu = feature.detach().cpu().to(dtype=torch.float32)
        array = feature_cpu.numpy()
        mean = float(array.mean())
        std = float(array.std())
        safe_std = std if std > 1e-8 else 1.0
        z_scores = (array - mean) / safe_std
        clipped = np.clip(z_scores, -3.0, 3.0).astype(np.float32)
        normalized = torch.from_numpy(clipped)
        stats = {
            "mean": mean,
            "std": std,
            "safe_std": safe_std,
            "clip_min": -3.0,
            "clip_max": 3.0,
        }
        return normalized, stats

    def _extract_training_feature(self, sample: IngestedSample) -> torch.Tensor:
        active_extractor = extract
        if active_extractor is _DEFAULT_COMPAT_FEATURE_EXTRACTOR:
            return self.feature_engineer.extract(sample)
        compatibility_feature = active_extractor(sample)
        return torch.as_tensor(compatibility_feature, dtype=torch.float32)

    def _prepare_cached_and_model_feature(
        self,
        raw_feature: torch.Tensor,
    ) -> tuple[torch.Tensor, torch.Tensor, dict[str, object]]:
        raw_feature_cpu = torch.as_tensor(raw_feature, dtype=torch.float32).detach().cpu().reshape(-1)
        source_dim = int(raw_feature_cpu.numel())
        stats: dict[str, object]
        compatibility_mode: str | None = None

        if source_dim == CVEFeatureEngineer.FEATURE_DIM:
            cached_feature, stats = self._normalize_feature_tensor(raw_feature_cpu)
            model_feature = self._expand_to_model_feature(cached_feature)
        elif source_dim == MODEL_INPUT_DIM:
            model_feature, stats = self._normalize_feature_tensor(raw_feature_cpu)
            cached_feature = model_feature[: CVEFeatureEngineer.FEATURE_DIM].clone()
            compatibility_mode = "legacy_512_slice"
        elif source_dim == 256:
            normalized_legacy_feature, stats = self._normalize_feature_tensor(raw_feature_cpu)
            model_feature = self._expand_to_model_feature(normalized_legacy_feature)
            cached_feature = torch.cat(
                [
                    normalized_legacy_feature,
                    torch.zeros(CVEFeatureEngineer.DOMAIN_SIGNAL_DIM, dtype=torch.float32),
                ],
                dim=0,
            )
            compatibility_mode = "legacy_256_repeat"
        else:
            raise RuntimeError(
                "REAL_DATA_REQUIRED: feature extractor returned invalid shape "
                f"{tuple(raw_feature_cpu.shape)}"
            )

        stats["source_feature_dim"] = source_dim
        stats["stored_feature_dim"] = CVEFeatureEngineer.FEATURE_DIM
        stats["model_input_dim"] = MODEL_INPUT_DIM
        if compatibility_mode is not None:
            stats["compatibility_mode"] = compatibility_mode
        return cached_feature, model_feature, stats

    @staticmethod
    def _validate_feature_tensor(feature: torch.Tensor) -> tuple[bool, str]:
        if torch.isnan(feature).any().item():
            return False, "nan_detected"
        if torch.isinf(feature).any().item():
            return False, "inf_detected"
        if bool(torch.count_nonzero(feature).item()) is False:
            return False, "all_zero"
        flattened = feature.detach().reshape(-1).cpu().to(dtype=torch.float32)
        if flattened.numel() > 0 and torch.all(flattened == flattened[0]).item():
            logger.warning(
                "feature_tensor_all_same_value_rejected",
                extra={
                    "event": "feature_tensor_all_same_value_rejected",
                    "value": float(flattened[0].item()),
                    "numel": int(flattened.numel()),
                },
            )
            return False, "all_same_value"
        variance = float(flattened.var(unbiased=False).item()) if flattened.numel() else 0.0
        if variance <= 0.0:
            logger.warning(
                "feature_tensor_zero_variance_rejected",
                extra={
                    "event": "feature_tensor_zero_variance_rejected",
                    "variance": variance,
                    "numel": int(flattened.numel()),
                },
            )
            return False, "zero_variance"
        return True, "ok"

    def _record_invalid_sample(self, sample: IngestedSample, reason: str) -> None:
        self._invalid_sample_count += 1
        warning_key = f"{sample.sha256_hash}:{reason}"
        if warning_key in self._invalid_sample_warnings:
            return
        self._invalid_sample_warnings.add(warning_key)
        logger.warning(
            "invalid_feature_sample_rejected",
            extra={
                "event": "invalid_feature_sample_rejected",
                "sample_sha256": sample.sha256_hash,
                "reason": reason,
                "source": sample.source,
                "url": sample.url[:256],
            },
        )

    def _load_or_compute_feature(self, sample: IngestedSample) -> torch.Tensor:
        cache_path = self._feature_cache_path(sample)
        cached_feature = self._load_feature_from_store(sample, cache_path)
        if cached_feature is not None:
            return cached_feature

        raw_feature = self._extract_training_feature(sample)
        cached_feature, feature, stats_payload = self._prepare_cached_and_model_feature(
            raw_feature
        )
        is_valid, reason = self._validate_feature_tensor(feature)
        if not is_valid:
            self._record_invalid_sample(sample, reason)
            raise RuntimeError(
                "REAL_DATA_REQUIRED: feature extractor returned invalid feature tensor "
                f"{reason}"
            )
        try:
            self.feature_store.write(
                sample.sha256_hash,
                self._compress_feature_tensor(cached_feature),
                np.asarray([self._label_for_sample(sample)], dtype=np.int64),
                metadata=self._feature_store_metadata(sample, stats_payload),
            )
        except (OSError, ValueError, TypeError) as exc:
            logger.warning(
                "feature_cache_write_failed",
                extra={
                    "event": "feature_cache_write_failed",
                    "path": str(cache_path),
                    "reason": type(exc).__name__,
                },
            )
        return feature

    def _safe_parse_raw_sample_file(self, sample_path: Path) -> IngestedSample | None:
        try:
            payload = json.loads(sample_path.read_text(encoding="utf-8"))
            return self._parse_sample(payload)
        except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
            logger.warning(
                "raw_sample_skipped",
                extra={
                    "event": "raw_sample_skipped",
                    "path": str(sample_path),
                    "reason": type(exc).__name__,
                },
            )
            return None

    def _load_dataset_index_payload(self) -> dict[str, object] | None:
        if not self.dataset_index_path.exists():
            return None
        try:
            payload = json.loads(self.dataset_index_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning(
                "dataset_index_unavailable",
                extra={
                    "event": "dataset_index_unavailable",
                    "path": str(self.dataset_index_path),
                    "reason": type(exc).__name__,
                },
            )
            return None
        if not isinstance(payload, dict):
            logger.warning(
                "dataset_index_invalid",
                extra={
                    "event": "dataset_index_invalid",
                    "path": str(self.dataset_index_path),
                    "reason": "not_a_dict",
                },
            )
            return None
        return payload

    def _deserialize_dataset_index(
        self, payload: dict[str, object]
    ) -> list[tuple[str, IngestedSample]]:
        entries = payload.get("entries", [])
        if not isinstance(entries, list):
            logger.warning(
                "dataset_index_invalid",
                extra={
                    "event": "dataset_index_invalid",
                    "path": str(self.dataset_index_path),
                    "reason": "entries_not_list",
                },
            )
            return []

        samples: list[tuple[str, IngestedSample]] = []
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            sample_payload = entry.get("sample")
            sample_path = str(entry.get("path", "") or "")
            if not sample_path or not isinstance(sample_payload, dict):
                continue
            try:
                sample = self._parse_sample(sample_payload)
            except (KeyError, TypeError, ValueError) as exc:
                logger.warning(
                    "dataset_index_entry_rejected",
                    extra={
                        "event": "dataset_index_entry_rejected",
                        "path": sample_path,
                        "reason": type(exc).__name__,
                    },
                )
                continue
            samples.append((sample_path, sample))
        return samples

    def _iter_candidate_sample_dirs(self) -> list[Path]:
        if not self.raw_data_root.exists():
            return []

        candidate_dirs: list[Path] = [self.raw_data_root]
        try:
            source_dirs = sorted(path for path in self.raw_data_root.iterdir() if path.is_dir())
        except OSError as exc:
            logger.warning(
                "dataset_index_source_scan_failed",
                extra={
                    "event": "dataset_index_source_scan_failed",
                    "path": str(self.raw_data_root),
                    "reason": type(exc).__name__,
                },
            )
            return candidate_dirs

        for source_dir in source_dirs:
            candidate_dirs.append(source_dir)
            try:
                child_dirs = sorted(path for path in source_dir.iterdir() if path.is_dir())
            except OSError as exc:
                logger.warning(
                    "dataset_index_child_scan_failed",
                    extra={
                        "event": "dataset_index_child_scan_failed",
                        "path": str(source_dir),
                        "reason": type(exc).__name__,
                    },
                )
                continue
            candidate_dirs.extend(child_dirs)
        return candidate_dirs

    def _refresh_dataset_index(
        self, invalidation_source: InvalidationSource | None = None
    ) -> list[tuple[str, IngestedSample]]:
        cached_payload = self._load_dataset_index_payload() or {}
        cached_entries = cached_payload.get("entries", [])
        cached_by_path: dict[str, dict[str, object]] = {}
        cached_by_dir: dict[str, list[dict[str, object]]] = {}
        cached_dirs = cached_payload.get("directories", {})
        if isinstance(cached_entries, list):
            for entry in cached_entries:
                if not isinstance(entry, dict):
                    continue
                entry_path = str(entry.get("path", "") or "")
                if entry_path:
                    cached_by_path[entry_path] = entry
                    directory = str(entry.get("directory", "") or "")
                    if directory:
                        cached_by_dir.setdefault(directory, []).append(entry)

        indexed_samples: list[tuple[str, IngestedSample]] = []
        index_entries: list[dict[str, object]] = []
        directory_entries: dict[str, int] = {}

        active_invalidation_source = invalidation_source or DirectoryMtimeSource(
            self.raw_data_root,
            cached_directories=cached_dirs if isinstance(cached_dirs, dict) else None,
        )
        changed_dirs = active_invalidation_source.get_changed_dirs()

        for candidate_dir in self._iter_candidate_sample_dirs():
            try:
                dir_stat = candidate_dir.stat()
            except OSError as exc:
                logger.warning(
                    "dataset_index_directory_stat_failed",
                    extra={
                        "event": "dataset_index_directory_stat_failed",
                        "path": str(candidate_dir),
                        "reason": type(exc).__name__,
                    },
                )
                continue

            dir_key = str(candidate_dir)
            directory_entries[dir_key] = dir_stat.st_mtime_ns
            if candidate_dir not in changed_dirs:
                for entry in cached_by_dir.get(dir_key, []):
                    sample_payload = entry.get("sample")
                    sample_path_str = str(entry.get("path", "") or "")
                    if not sample_path_str or not isinstance(sample_payload, dict):
                        continue
                    try:
                        sample = self._parse_sample(sample_payload)
                    except (KeyError, TypeError, ValueError) as exc:
                        logger.warning(
                            "dataset_index_entry_rejected",
                            extra={
                                "event": "dataset_index_entry_rejected",
                                "path": sample_path_str,
                                "reason": type(exc).__name__,
                            },
                        )
                        continue
                    indexed_samples.append((sample_path_str, sample))
                    index_entries.append(dict(entry))
                continue

            try:
                sample_paths = sorted(candidate_dir.glob("*.json"))
            except OSError as exc:
                logger.warning(
                    "raw_sample_directory_scan_failed",
                    extra={
                        "event": "raw_sample_directory_scan_failed",
                        "path": str(candidate_dir),
                        "reason": type(exc).__name__,
                    },
                )
                continue

            for sample_path in sample_paths:
                if sample_path.name == "dedup_index.json":
                    continue

                try:
                    stat = sample_path.stat()
                except OSError as exc:
                    logger.warning(
                        "raw_sample_stat_failed",
                        extra={
                            "event": "raw_sample_stat_failed",
                            "path": str(sample_path),
                            "reason": type(exc).__name__,
                        },
                    )
                    continue

                sample: IngestedSample | None = None
                cached_entry = cached_by_path.get(str(sample_path))
                cached_mtime_ns = cached_entry.get("mtime_ns") if cached_entry else None
                if cached_entry and cached_mtime_ns == stat.st_mtime_ns:
                    sample_payload = cached_entry.get("sample")
                    if isinstance(sample_payload, dict):
                        try:
                            sample = self._parse_sample(sample_payload)
                        except (KeyError, TypeError, ValueError) as exc:
                            logger.warning(
                                "dataset_index_entry_rejected",
                                extra={
                                    "event": "dataset_index_entry_rejected",
                                    "path": str(sample_path),
                                    "reason": type(exc).__name__,
                                },
                            )

                if sample is None:
                    sample = self._safe_parse_raw_sample_file(sample_path)
                if sample is None:
                    continue

                sample_path_str = str(sample_path)
                indexed_samples.append((sample_path_str, sample))
                index_entries.append(
                    {
                        "path": sample_path_str,
                        "directory": dir_key,
                        "mtime_ns": stat.st_mtime_ns,
                        "sample": self._sample_to_payload(sample),
                    }
                )

        self._atomic_write_json(
            self.dataset_index_path,
            {
                "schema_version": 2,
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "raw_data_root": str(self.raw_data_root),
                "directories": directory_entries,
                "entries": index_entries,
            },
        )
        self._indexed_raw_samples_cache = list(indexed_samples)
        return list(indexed_samples)

    def _get_indexed_raw_samples(
        self, *, refresh: bool = False
    ) -> list[tuple[str, IngestedSample]]:
        if refresh:
            return self._refresh_dataset_index()
        if self._indexed_raw_samples_cache is not None:
            return list(self._indexed_raw_samples_cache)

        cached_payload = self._load_dataset_index_payload()
        if cached_payload is not None:
            self._indexed_raw_samples_cache = self._deserialize_dataset_index(cached_payload)
            if self._indexed_raw_samples_cache:
                return list(self._indexed_raw_samples_cache)

        return self._refresh_dataset_index()

    @staticmethod
    def _deterministic_indices(total: int, limit: int) -> list[int]:
        if total <= 0 or limit <= 0:
            return []
        if limit >= total:
            return list(range(total))
        return [int((index * total) / limit) for index in range(limit)]

    @staticmethod
    def _hash_predictions(
        predictions: list[int], probabilities: list[list[float]]
    ) -> str:
        payload = {
            "predictions": [int(prediction) for prediction in predictions],
            "probabilities": [
                [round(float(value), 8) for value in row] for row in probabilities
            ],
        }
        encoded = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode(
            "utf-8"
        )
        return hashlib.sha256(encoded).hexdigest()

    def _load_or_initialize_model(self) -> torch.nn.Module:
        if BugClassifier is None:
            raise RuntimeError("BugClassifier runtime unavailable")
        model = BugClassifier(self.model_config).to(self.device)
        if not self.model_path.exists():
            migrated = self._restore_legacy_checkpoint()
            if not migrated:
                self._save_model_state(model.state_dict(), epoch_number=0)
                return model

        state_dict = load_safetensors(str(self.model_path), device=self.device.type)
        load_result = model.load_state_dict(state_dict, strict=False)
        if load_result.missing_keys or load_result.unexpected_keys:
            logger.info(
                "incremental_trainer_checkpoint_load",
                extra={
                    "event": "incremental_trainer_checkpoint_load",
                    "missing_keys": list(load_result.missing_keys),
                    "unexpected_keys": list(load_result.unexpected_keys),
                },
            )
        return model

    def _restore_legacy_checkpoint(self) -> bool:
        checkpoints_root = self.model_path.parent
        legacy_candidates = sorted(
            checkpoints_root.glob("*.pt"),
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        )
        if not legacy_candidates:
            return False

        from scripts.migrate_checkpoint_to_v2 import migrate_checkpoint

        migrated = migrate_checkpoint(str(legacy_candidates[0]), str(self.model_path))
        logger.info(
            "legacy_checkpoint_restored",
            extra={
                "event": "legacy_checkpoint_restored",
                "source_path": str(legacy_candidates[0]),
                "output_path": str(self.model_path),
                "mapped_keys": len(migrated["mapped_keys"]),
                "unmapped_keys": len(migrated["unmapped_keys"]),
            },
        )
        return True

    def _save_model_state(
        self, state_dict: dict[str, torch.Tensor], epoch_number: int
    ) -> None:
        metadata = {"epoch_number": str(epoch_number)}
        save_safetensors(state_dict, str(self.model_path), metadata=metadata)

    def _persist_checkpoint_metrics(
        self,
        *,
        accuracy: float,
        precision: float,
        recall: float,
        f1: float,
        positive_threshold: float,
    ) -> None:
        payload = save_threshold_artifact(
            self.baseline_path,
            baseline_accuracy=max(self.baseline_accuracy, accuracy),
            positive_threshold=positive_threshold,
            checkpoint_accuracy=accuracy,
            checkpoint_precision=precision,
            checkpoint_recall=recall,
            checkpoint_f1=f1,
        )
        self.baseline_state = payload
        self.baseline_accuracy = float(payload["baseline_accuracy"])
        self.positive_threshold = float(payload["positive_threshold"])

    def _parse_sample(self, payload: dict[str, object]) -> IngestedSample:
        ingested_at = datetime.fromisoformat(
            str(payload["ingested_at"]).replace("Z", "+00:00")
        )
        return IngestedSample(
            source=str(payload["source"]),
            raw_text=str(payload["raw_text"]),
            url=str(payload["url"]),
            cve_id=str(payload.get("cve_id", "")),
            severity=str(payload.get("severity", "UNKNOWN")),
            tags=tuple(payload.get("tags", [])),
            ingested_at=ingested_at,
            sha256_hash=str(payload["sha256_hash"]),
            token_count=int(payload["token_count"]),
            lang=str(payload.get("lang", "en")),
        )

    def load_new_samples(self) -> list[IngestedSample]:
        last_training_time = datetime.fromisoformat(
            str(self.training_state["last_training_time"]).replace("Z", "+00:00")
        )
        samples: list[IngestedSample] = []
        for _, sample in self._get_indexed_raw_samples(refresh=True):
            if sample.ingested_at > last_training_time:
                samples.append(sample)
        if samples:
            logger.info(
                "incremental_samples_loaded",
                extra={
                    "event": "incremental_samples_loaded",
                    "count": len(samples),
                    "source": "data_raw",
                },
            )
            return samples

        bridge_limit = max(
            1000, int(os.environ.get("YGB_BRIDGE_TRAIN_MAX_SAMPLES", "5000"))
        )
        bridge_samples = self._load_bridge_samples(max_samples=bridge_limit)
        logger.info(
            "incremental_samples_loaded",
            extra={
                "event": "incremental_samples_loaded",
                "count": len(bridge_samples),
                "source": "bridge_state",
            },
        )
        return bridge_samples

    def load_evaluation_samples(
        self, max_samples: int
    ) -> tuple[list[IngestedSample], str]:
        samples = [sample for _, sample in self._get_indexed_raw_samples(refresh=False)]

        if samples:
            if len(samples) > max_samples:
                sample_indices = self._deterministic_indices(len(samples), max_samples)
                samples = [samples[index] for index in sample_indices]
            return samples, "data_raw"

        return self._load_bridge_samples(max_samples=max_samples), "bridge_state"

    @staticmethod
    def _label_for_sample(sample: IngestedSample) -> int:
        return 1 if sample.severity in {"CRITICAL", "HIGH", "MEDIUM"} else 0

    @staticmethod
    def _severity_from_bridge_record(payload: dict[str, object]) -> str:
        impact = str(payload.get("impact", ""))
        match = _IMPACT_RE.search(impact)
        if not match:
            return "UNKNOWN"
        severity = match.group("severity").strip().upper()
        if severity and severity != "UNKNOWN":
            return severity
        score = float(match.group("score"))
        if score >= 9.0:
            return "CRITICAL"
        if score >= 7.0:
            return "HIGH"
        if score >= 4.0:
            return "MEDIUM"
        if score > 0.0:
            return "LOW"
        return "UNKNOWN"

    def _validate_or_reject_bridge_row(
        self, row: dict[str, object]
    ) -> IngestedSample | None:
        source_tag = str(row.get("source_tag", "") or "").strip()
        if not source_tag or source_tag.upper() == "UNKNOWN":
            logger.warning(
                "INVALID LEGACY DATA - rejected: bridge source_tag missing",
                extra={"event": "bridge_row_rejected", "reason": "source_tag_missing"},
            )
            return None

        row_timestamp = str(row.get("ingested_at", "") or "").strip()
        if not row_timestamp:
            logger.warning(
                "INVALID LEGACY DATA - rejected: bridge row ingested_at missing",
                extra={"event": "bridge_row_rejected", "reason": "ingested_at_missing"},
            )
            return None

        row_sha256_hash = str(row.get("sha256_hash", "") or "").strip()
        if len(row_sha256_hash) != 64:
            logger.warning(
                "INVALID LEGACY DATA - rejected: bridge row sha256_hash missing",
                extra={"event": "bridge_row_rejected", "reason": "sha256_hash_missing"},
            )
            return None

        endpoint = str(row.get("endpoint", "") or "").strip()
        if not _CVE_ID_RE.fullmatch(endpoint):
            logger.warning(
                "INVALID LEGACY DATA - rejected: bridge endpoint is not a canonical CVE id",
                extra={
                    "event": "bridge_row_rejected",
                    "reason": "invalid_endpoint",
                    "endpoint": endpoint or "<missing>",
                },
            )
            return None

        text = " ".join(
            str(row.get(field, ""))
            for field in ("endpoint", "parameters", "exploit_vector")
            if str(row.get(field, "")).strip()
        ).strip()
        if not text:
            logger.warning(
                "INVALID LEGACY DATA - rejected: bridge row text fields missing",
                extra={"event": "bridge_row_rejected", "reason": "text_missing"},
            )
            return None

        try:
            ingested_at = datetime.fromisoformat(row_timestamp.replace("Z", "+00:00"))
        except ValueError:
            logger.warning(
                "INVALID LEGACY DATA - rejected: bridge row ingested_at invalid",
                extra={
                    "event": "bridge_row_rejected",
                    "reason": "ingested_at_invalid",
                    "value": row_timestamp,
                },
            )
            return None

        severity = self._severity_from_bridge_record(row)
        return IngestedSample(
            source=source_tag,
            raw_text=text,
            url=f"https://nvd.nist.gov/vuln/detail/{endpoint.upper()}",
            cve_id=endpoint.upper(),
            severity=severity,
            tags=tuple(),
            ingested_at=ingested_at,
            sha256_hash=row_sha256_hash,
            token_count=len(text.split()),
            lang="en",
        )

    def _load_bridge_samples(self, max_samples: int) -> list[IngestedSample]:
        bridge_state = get_bridge_state()
        rows = bridge_state.read_samples(max_samples=max_samples)
        samples: list[IngestedSample] = []
        for row in rows:
            sample = self._validate_or_reject_bridge_row(row)
            if sample is not None:
                samples.append(sample)
        return samples

    def build_dataset(
        self,
        samples: list[IngestedSample],
        *,
        include_train_dataset_indices: bool = False,
    ) -> tuple[DataLoader, DataLoader]:
        if self.num_workers > 0 and can_ai_execute()[0]:
            raise RuntimeError("GUARD")
        quality_report = self.dataset_quality_gate.validate(samples)
        self._last_dataset_quality_report = quality_report
        if not quality_report.passed:
            raise DatasetQualityError(quality_report.failed_reasons)

        indices = list(range(len(samples)))
        rng = np.random.default_rng(42)
        shuffled_indices = list(indices)
        rng.shuffle(shuffled_indices)
        eval_count = min(
            len(indices) - 1,
            max(1, int(round(len(indices) * self.optimizer_config.validation_split))),
        )
        eval_indices = list(shuffled_indices[:eval_count])
        train_indices = list(shuffled_indices[eval_count:])
        if not train_indices or not eval_indices:
            raise RuntimeError(
                "REAL_DATA_REQUIRED: Deterministic train/validation split failed"
            )
        train_labels = [self._label_for_sample(samples[index]) for index in train_indices]
        self._last_balance_report = self.class_balancer.balance_indices(
            sample_indices=train_indices,
            labels=train_labels,
        )
        balanced_train_indices = list(self._last_balance_report.oversampled_indices)
        logger.info(
            "incremental class balancing train_counts=%s class_weights=%s added_repeats=%d",
            self._last_balance_report.class_counts,
            {
                label: round(weight, 6)
                for label, weight in self._last_balance_report.class_weights.items()
            },
            self._last_balance_report.added_indices,
        )

        val_class_distribution = {severity: 0 for severity in DatasetQualityGate._SEVERITY_CLASSES}
        for eval_index in eval_indices:
            severity = self.dataset_quality_gate._canonical_severity(
                samples[eval_index].severity
            )
            if severity in val_class_distribution:
                val_class_distribution[severity] += 1
        logger.debug(
            "incremental validation split size=%d class_distribution=%s",
            len(eval_indices),
            val_class_distribution,
        )

        train_dataset = _StreamingFeatureDataset(
            self,
            samples,
            balanced_train_indices,
            return_dataset_index=include_train_dataset_indices,
        )
        eval_dataset = _StreamingFeatureDataset(self, samples, eval_indices)
        train_generator = torch.Generator().manual_seed(self.model_config.seed)
        train_loader = DataLoader(
            train_dataset,
            batch_size=int(self.model_config.batch_size),
            shuffle=True,
            num_workers=self.num_workers,
            pin_memory=self.device.type == "cuda",
            persistent_workers=self.num_workers > 0,
            generator=train_generator,
        )
        eval_loader = DataLoader(
            eval_dataset,
            batch_size=512,
            shuffle=False,
            num_workers=self.num_workers,
            pin_memory=self.device.type == "cuda",
            persistent_workers=self.num_workers > 0,
        )
        return train_loader, eval_loader

    def _restore_previous_state(self, previous_state: dict[str, torch.Tensor]) -> None:
        self.model.load_state_dict(previous_state, strict=False)
        self._save_model_state(
            previous_state, epoch_number=int(self.training_state.get("epoch_number", 0))
        )

    def _backward_pass(self, scaled_loss: torch.Tensor, scaler) -> None:
        if scaler is not None:
            scaler.scale(scaled_loss).backward()
            return
        scaled_loss.backward()

    def _clip_gradients(
        self,
        optimizer: torch.optim.Optimizer,
        scaler,
        *,
        gradient_clip_norm: float = 1.0,
    ) -> None:
        if scaler is not None:
            scaler.unscale_(optimizer)
        torch.nn.utils.clip_grad_norm_(
            self.model.parameters(),
            float(gradient_clip_norm),
        )

    def _step_optimizer(
        self,
        optimizer: torch.optim.Optimizer,
        scaler,
        *,
        gradient_clip_norm: float = 1.0,
        gradients_clipped: bool = False,
    ) -> None:
        if scaler is not None:
            if not gradients_clipped:
                scaler.unscale_(optimizer)
                torch.nn.utils.clip_grad_norm_(
                    self.model.parameters(), float(gradient_clip_norm)
                )
            scaler.step(optimizer)
            scaler.update()
        else:
            if not gradients_clipped:
                torch.nn.utils.clip_grad_norm_(
                    self.model.parameters(), float(gradient_clip_norm)
                )
            optimizer.step()
        optimizer.zero_grad(set_to_none=True)

    @staticmethod
    def _clone_model_state(
        state_dict: dict[str, torch.Tensor],
    ) -> dict[str, torch.Tensor]:
        return {
            name: tensor.detach().cpu().clone()
            for name, tensor in state_dict.items()
        }

    @staticmethod
    def _current_learning_rate(
        optimizer: torch.optim.Optimizer,
        scheduler,
    ) -> float:
        get_last_lr = getattr(scheduler, "get_last_lr", None)
        if callable(get_last_lr):
            last_learning_rates = list(get_last_lr())
            if last_learning_rates:
                return float(last_learning_rates[0])
        return float(optimizer.param_groups[0]["lr"])

    @staticmethod
    def _merge_hard_negative_weights(
        sample_weights: np.ndarray | None,
        *,
        dataset_length: int,
        hard_negative_indices: list[int],
        hard_negative_weight: float,
    ) -> np.ndarray | None:
        if not hard_negative_indices:
            return sample_weights
        effective_weights = (
            sample_weights.copy()
            if sample_weights is not None
            else np.ones(dataset_length, dtype=np.float32)
        )
        for dataset_index in hard_negative_indices:
            if 0 <= int(dataset_index) < dataset_length:
                effective_weights[int(dataset_index)] *= float(hard_negative_weight)
        return effective_weights

    @staticmethod
    def _loader_supports_dataset_indices(train_loader: DataLoader) -> bool:
        dataset = getattr(train_loader, "dataset", None)
        if dataset is None:
            return False
        dataset_flag = getattr(dataset, "_return_dataset_index", None)
        if isinstance(dataset_flag, bool):
            return dataset_flag
        tensors = getattr(dataset, "tensors", None)
        if isinstance(tensors, tuple):
            return len(tensors) == 3
        try:
            first_item = dataset[0]
        except (IndexError, KeyError, TypeError, RuntimeError, ValueError):
            return False
        return isinstance(first_item, (list, tuple)) and len(first_item) == 3

    def _evaluate_loader(
        self,
        eval_loader: DataLoader,
        criterion,
    ) -> dict[str, object]:
        self.model.eval()
        eval_losses: list[float] = []
        labels_out: list[int] = []
        probability_rows: list[list[float]] = []
        with torch.no_grad():
            for batch in eval_loader:
                features, labels, _ = self._unpack_batch(batch)
                features = features.to(self.device)
                labels = labels.to(self.device)
                logits = self.model(features)
                probabilities = torch.softmax(logits, dim=1)
                eval_losses.append(float(criterion(logits, labels).item()))
                labels_out.extend(labels.detach().cpu().tolist())
                probability_rows.extend(probabilities.detach().cpu().tolist())
        positive_probabilities = [float(row[1]) for row in probability_rows]
        threshold_metrics = calibrate_positive_threshold(
            labels_out,
            positive_probabilities,
            fallback_threshold=self.positive_threshold,
        )
        metrics_report = self.metrics_tracker.update(
            labels=labels_out,
            predictions=list(threshold_metrics["predictions"]),
        )
        return {
            "eval_loss": float(sum(eval_losses) / max(len(eval_losses), 1)),
            "labels": labels_out,
            "probability_rows": probability_rows,
            "positive_threshold": float(threshold_metrics["threshold"]),
            "threshold_strategy": str(threshold_metrics["strategy"]),
            "predictions": list(threshold_metrics["predictions"]),
            "accuracy": float(threshold_metrics["accuracy"]),
            "precision": float(threshold_metrics["precision"]),
            "recall": float(threshold_metrics["recall"]),
            "f1": float(threshold_metrics["f1"]),
            "auc_roc": self._compute_auc_roc(labels_out, positive_probabilities),
            "metrics_report": metrics_report,
        }

    def _train_single_epoch(
        self,
        train_loader: DataLoader,
        optimizer: torch.optim.Optimizer,
        scheduler,
        criterion,
        scaler,
        *,
        sample_weights: list[float] | np.ndarray | None = None,
        hard_negative_miner: HardNegativeMiner | None = None,
        accumulation_steps: int = 4,
        gradient_clip_norm: float = 1.0,
        amp_enabled: bool = False,
    ) -> float:
        resolved_sample_weights = (
            self._coerce_sample_weights(sample_weights, len(train_loader.dataset))
            if sample_weights is not None
            else None
        )
        self.adaptive_learner.attach_model(self.model)
        self.model.train()
        optimizer.zero_grad(set_to_none=True)
        requested_accumulation_steps = max(int(accumulation_steps), 1)
        if requested_accumulation_steps != 1:
            logger.info(
                "gradient accumulation disabled to preserve per-backward clipping honesty requested=%d effective=1",
                requested_accumulation_steps,
            )
        accum_steps = 1
        step_count = 0
        epoch_losses: list[float] = []
        epoch_ewc_losses: list[float] = []
        if hard_negative_miner is not None:
            hard_negative_miner.reset()
        for step_count, batch in enumerate(train_loader, start=1):
            features, labels, dataset_indices = self._unpack_batch(batch)
            features = features.to(self.device)
            labels = labels.to(self.device)
            autocast_context = (
                torch.cuda.amp.autocast(enabled=True)
                if amp_enabled
                else nullcontext()
            )
            with autocast_context:
                outputs = self.model(features)
                batch_losses = criterion(outputs, labels)
                if not torch.is_tensor(batch_losses):
                    raise TypeError("training criterion must return a tensor")
                if resolved_sample_weights is None:
                    loss = (
                        batch_losses.mean()
                        if batch_losses.ndim > 0
                        else batch_losses
                    )
                else:
                    if batch_losses.ndim == 0:
                        raise ValueError(
                            "sample_weights require a criterion with reduction='none'"
                        )
                    if dataset_indices is None:
                        raise ValueError(
                            "sample_weights require dataset indices in the training batches"
                        )
                    batch_index_array = np.asarray(
                        dataset_indices.detach().cpu().tolist(),
                        dtype=np.int64,
                    )
                    batch_weight_values = torch.as_tensor(
                        resolved_sample_weights[batch_index_array],
                        dtype=batch_losses.dtype,
                        device=batch_losses.device,
                    )
                    if batch_weight_values.shape[0] != labels.shape[0]:
                        raise ValueError(
                            "sample weight batch length does not match label batch length"
                        )
                    loss = torch.sum(batch_losses * batch_weight_values) / torch.sum(
                        batch_weight_values
                    )
                ewc_loss = self.adaptive_learner.get_ewc_loss()
                if not torch.is_tensor(ewc_loss):
                    ewc_loss = torch.as_tensor(
                        float(ewc_loss),
                        dtype=loss.dtype,
                        device=loss.device,
                    )
                else:
                    ewc_loss = ewc_loss.to(device=loss.device, dtype=loss.dtype)
                total_loss = loss + ewc_loss
                scaled_loss = total_loss / accum_steps
            if hard_negative_miner is not None:
                if batch_losses.ndim == 0:
                    batch_loss_values = torch.full(
                        (labels.shape[0],),
                        float(batch_losses.detach().item()),
                        dtype=torch.float32,
                    )
                else:
                    batch_loss_values = batch_losses.detach().reshape(-1).to(
                        dtype=torch.float32
                    )
                hard_negative_miner.update(
                    losses=batch_loss_values.cpu().tolist(),
                    labels=labels.detach().cpu().tolist(),
                    positive_probabilities=torch.softmax(outputs.detach(), dim=1)[:, 1]
                    .cpu()
                    .tolist(),
                    dataset_indices=(
                        dataset_indices.detach().cpu().tolist()
                        if dataset_indices is not None
                        else None
                    ),
                )
            self._backward_pass(scaled_loss, scaler)
            self._clip_gradients(
                optimizer,
                scaler,
                gradient_clip_norm=gradient_clip_norm,
            )
            epoch_losses.append(float(total_loss.detach().item()))
            epoch_ewc_losses.append(float(ewc_loss.detach().item()))

            if step_count % accum_steps == 0:
                self._step_optimizer(
                    optimizer,
                    scaler,
                    gradient_clip_norm=gradient_clip_norm,
                    gradients_clipped=True,
                )
                scheduler.step()

            if step_count % 50 == 0:
                logger.info(
                    "incremental_training_step",
                    extra={
                        "event": "incremental_training_step",
                        "step": step_count,
                        "loss": float(loss.item()),
                    },
                )

        if step_count and step_count % accum_steps != 0:
            self._step_optimizer(
                optimizer,
                scaler,
                gradient_clip_norm=gradient_clip_norm,
            )
            scheduler.step()
        self._last_epoch_mean_ewc_loss = float(
            sum(epoch_ewc_losses) / max(len(epoch_ewc_losses), 1)
        )
        logger.debug(
            "incremental training epoch mean_ewc_loss=%.8f batch_count=%d",
            self._last_epoch_mean_ewc_loss,
            len(epoch_ewc_losses),
        )
        return float(sum(epoch_losses) / max(len(epoch_losses), 1))

    def get_accuracy_history(self) -> list[AccuracySnapshot]:
        return self._accuracy_history.as_list()

    @staticmethod
    def _unpack_batch(
        batch: object,
    ) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor | None]:
        if not isinstance(batch, (list, tuple)):
            raise TypeError("training batch must be a tuple or list")
        if len(batch) == 2:
            features, labels = batch
            return features, labels, None
        if len(batch) == 3:
            features, labels, dataset_indices = batch
            return features, labels, dataset_indices
        raise ValueError(f"training batch must contain 2 or 3 items, got {len(batch)}")

    @staticmethod
    def _coerce_sample_weights(
        sample_weights: list[float] | np.ndarray,
        expected_length: int,
    ) -> np.ndarray:
        weight_array = np.asarray(sample_weights, dtype=np.float32)
        if weight_array.ndim != 1:
            raise ValueError("sample_weights must be a 1D sequence of positive floats")
        if weight_array.shape[0] != expected_length:
            raise ValueError(
                f"sample_weights length {weight_array.shape[0]} does not match expected {expected_length}"
            )
        if not np.isfinite(weight_array).all():
            raise ValueError("sample_weights must be finite positive floats")
        if np.any(weight_array <= 0.0):
            raise ValueError("sample_weights must be strictly positive floats")
        return weight_array

    @staticmethod
    def _reward_to_sample_weight(reward: float) -> float:
        reward_value = float(reward)
        if not math.isfinite(reward_value):
            raise ValueError("reward-derived sample weights require finite reward values")
        return float(max(_RL_WEIGHT_FLOOR, _RL_WEIGHT_OFFSET + reward_value))

    @staticmethod
    def _weight_statistics(weight_values: np.ndarray) -> tuple[float, float, float]:
        if weight_values.size == 0:
            return 1.0, 1.0, 1.0
        return (
            float(weight_values.mean()),
            float(weight_values.min()),
            float(weight_values.max()),
        )

    def _resolve_native_reward_weight_lookup(
        self,
        samples: list[IngestedSample],
    ) -> dict[str, float] | None:
        weighted_rewards = self._reward_buffer.get_weighted_signals()
        total_signals = len(weighted_rewards)
        if not weighted_rewards:
            logger.info(
                "incremental_rl_reward_weights matched_samples=0 total_signals=0 reason=no_reward_signals"
            )
            return None

        matched_sample_weights: dict[str, float] = {}
        matched_reward_values: list[float] = []
        for sample_id in sorted({sample.sha256_hash for sample in samples}):
            reward_value = weighted_rewards.get(sample_id)
            if reward_value is None:
                continue
            reward_float = float(reward_value)
            matched_reward_values.append(reward_float)
            matched_sample_weights[sample_id] = self._reward_to_sample_weight(reward_float)

        if not matched_sample_weights:
            logger.info(
                "incremental_rl_reward_weights matched_samples=0 total_signals=%d reason=no_matching_samples",
                total_signals,
            )
            return None

        reward_values = np.asarray(matched_reward_values, dtype=np.float32)
        sample_weight_values = np.asarray(
            list(matched_sample_weights.values()), dtype=np.float32
        )
        reward_mean, reward_min, reward_max = self._weight_statistics(reward_values)
        weight_mean, weight_min, weight_max = self._weight_statistics(
            sample_weight_values
        )
        logger.info(
            "incremental_rl_reward_weights matched_samples=%d total_signals=%d reward_mean=%.6f reward_min=%.6f reward_max=%.6f weight_mean=%.6f weight_min=%.6f weight_max=%.6f",
            len(matched_sample_weights),
            total_signals,
            reward_mean,
            reward_min,
            reward_max,
            weight_mean,
            weight_min,
            weight_max,
        )
        return matched_sample_weights

    def _merge_incremental_sample_weight_sources(
        self,
        native_reward_weights: dict[str, float] | None,
        sample_weights: dict[str, float] | list[float] | np.ndarray | None,
    ) -> dict[str, float] | list[float] | np.ndarray | None:
        if native_reward_weights is None:
            return sample_weights
        if sample_weights is None:
            return native_reward_weights
        if isinstance(sample_weights, dict):
            override_entries = 0
            changed_overrides = 0
            merged_weights = dict(native_reward_weights)
            for raw_key, raw_value in sample_weights.items():
                key = str(raw_key)
                value = float(raw_value)
                native_value = native_reward_weights.get(key)
                if native_value is not None:
                    override_entries += 1
                    if not math.isclose(
                        value,
                        float(native_value),
                        rel_tol=1e-6,
                        abs_tol=1e-6,
                    ):
                        changed_overrides += 1
                merged_weights[key] = value
            logger.info(
                "incremental_sample_weight_sources native_entries=%d external_entries=%d override_entries=%d changed_overrides=%d merge_strategy=external_dict_overrides",
                len(native_reward_weights),
                len(sample_weights),
                override_entries,
                changed_overrides,
            )
            return merged_weights

        try:
            external_length = len(sample_weights)
        except TypeError:
            external_length = -1
        logger.info(
            "incremental_sample_weight_sources native_entries=%d external_length=%d merge_strategy=external_sequence_overrides_native",
            len(native_reward_weights),
            external_length,
        )
        return sample_weights

    def _log_native_reward_weighting(
        self,
        *,
        samples: list[IngestedSample],
        train_loader: DataLoader,
        native_reward_weights: dict[str, float] | None,
        resolved_train_sample_weights: np.ndarray | None,
    ) -> None:
        total_train_rows = len(train_loader.dataset)
        if not native_reward_weights:
            logger.info(
                "incremental_rl_weighting matched_samples=0 matched_rows=0 total_train_rows=%d overall_weight_mean=1.000000 overall_weight_min=1.000000 overall_weight_max=1.000000 effective_weight_mean=1.000000 effective_weight_min=1.000000 effective_weight_max=1.000000 reason=no_native_reward_weights",
                total_train_rows,
            )
            return

        dataset = getattr(train_loader, "dataset", None)
        matched_row_indices: list[int] = []
        if isinstance(dataset, _StreamingFeatureDataset):
            for row_index, sample_index in enumerate(dataset.sample_indices):
                if samples[sample_index].sha256_hash in native_reward_weights:
                    matched_row_indices.append(row_index)

        overall_weights = (
            np.asarray(resolved_train_sample_weights, dtype=np.float32)
            if resolved_train_sample_weights is not None
            else np.ones(total_train_rows, dtype=np.float32)
        )
        matched_weights = (
            overall_weights[np.asarray(matched_row_indices, dtype=np.int64)]
            if matched_row_indices
            else np.empty((0,), dtype=np.float32)
        )
        overall_mean, overall_min, overall_max = self._weight_statistics(overall_weights)
        matched_mean, matched_min, matched_max = self._weight_statistics(matched_weights)
        logger.info(
            "incremental_rl_weighting matched_samples=%d matched_rows=%d total_train_rows=%d overall_weight_mean=%.6f overall_weight_min=%.6f overall_weight_max=%.6f effective_weight_mean=%.6f effective_weight_min=%.6f effective_weight_max=%.6f",
            len(native_reward_weights),
            len(matched_row_indices),
            total_train_rows,
            overall_mean,
            overall_min,
            overall_max,
            matched_mean,
            matched_min,
            matched_max,
        )

    def _resolve_train_sample_weights(
        self,
        samples: list[IngestedSample],
        train_loader: DataLoader,
        sample_weights: dict[str, float] | list[float] | np.ndarray | None,
    ) -> np.ndarray | None:
        if sample_weights is None:
            return None
        dataset = getattr(train_loader, "dataset", None)
        if dataset is None:
            raise ValueError("train_loader must expose a dataset when sample_weights are provided")
        expected_length = len(dataset)
        if isinstance(sample_weights, dict):
            if not isinstance(dataset, _StreamingFeatureDataset):
                raise ValueError(
                    "sample_weights dict requires the streaming training dataset for sample-id alignment"
                )
            aligned_weights = [
                float(sample_weights.get(samples[index].sha256_hash, 1.0))
                for index in dataset.sample_indices
            ]
            return self._coerce_sample_weights(aligned_weights, expected_length)
        try:
            raw_length = len(sample_weights)
        except TypeError as exc:
            raise ValueError("sample_weights must be a dict or 1D sequence") from exc
        if isinstance(dataset, _StreamingFeatureDataset) and raw_length == len(samples):
            aligned_weights = [float(sample_weights[index]) for index in dataset.sample_indices]
            return self._coerce_sample_weights(aligned_weights, expected_length)
        return self._coerce_sample_weights(sample_weights, expected_length)

    def train(
        self,
        train_loader: DataLoader,
        optimizer: torch.optim.Optimizer,
        scheduler,
        criterion,
        scaler,
        *,
        sample_weights: list[float] | np.ndarray | None = None,
        val_loader: DataLoader | None = None,
        eval_criterion=None,
        optimiser_config: TrainingOptimiserConfig | None = None,
        return_history: bool = False,
    ) -> float | TrainingLoopResult:
        active_config = optimiser_config or self.optimizer_config
        if val_loader is None and not return_history:
            return self._train_single_epoch(
                train_loader,
                optimizer,
                scheduler,
                criterion,
                scaler,
                sample_weights=sample_weights,
                accumulation_steps=active_config.accumulation_steps,
                gradient_clip_norm=active_config.gradient_clip_norm,
                amp_enabled=active_config.amp_enabled(self.device),
            )
        if val_loader is None or eval_criterion is None:
            raise ValueError(
                "val_loader and eval_criterion are required when return_history is enabled"
            )

        self.metrics_tracker.reset()
        base_sample_weights = (
            self._coerce_sample_weights(sample_weights, len(train_loader.dataset))
            if sample_weights is not None
            else None
        )
        hard_negative_target_count = active_config.resolved_hard_negative_count(
            len(train_loader.dataset)
        )
        supports_dataset_indices = self._loader_supports_dataset_indices(train_loader)
        hard_negative_miner = HardNegativeMiner(
            max_hard_examples=max(hard_negative_target_count, 1)
        )
        early_stopper = EarlyStopping(
            patience=active_config.patience,
            min_delta=active_config.min_delta,
            mode="min",
        )
        best_model_state = self._clone_model_state(self.model.state_dict())
        best_result: TrainingLoopResult | None = None
        current_hard_negative_indices: list[int] = []
        epochs_completed = 0
        for epoch_index in range(active_config.max_epochs):
            effective_sample_weights = base_sample_weights
            if supports_dataset_indices:
                effective_sample_weights = self._merge_hard_negative_weights(
                    base_sample_weights,
                    dataset_length=len(train_loader.dataset),
                    hard_negative_indices=current_hard_negative_indices,
                    hard_negative_weight=active_config.hard_negative_weight,
                )
            train_loss = self._train_single_epoch(
                train_loader,
                optimizer,
                scheduler,
                criterion,
                scaler,
                sample_weights=effective_sample_weights,
                hard_negative_miner=hard_negative_miner,
                accumulation_steps=active_config.accumulation_steps,
                gradient_clip_norm=active_config.gradient_clip_norm,
                amp_enabled=active_config.amp_enabled(self.device),
            )
            evaluation = self._evaluate_loader(val_loader, eval_criterion)
            current_hard_negative_indices = hard_negative_miner.get_hard_indices(
                count=hard_negative_target_count
            )
            current_result = TrainingLoopResult(
                train_loss=float(train_loss),
                eval_loss=float(evaluation["eval_loss"]),
                accuracy=float(evaluation["accuracy"]),
                precision=float(evaluation["precision"]),
                recall=float(evaluation["recall"]),
                f1=float(evaluation["f1"]),
                auc_roc=float(evaluation["auc_roc"]),
                positive_threshold=float(evaluation["positive_threshold"]),
                threshold_strategy=str(evaluation["threshold_strategy"]),
                predictions=list(evaluation["predictions"]),
                labels=list(evaluation["labels"]),
                probability_rows=list(evaluation["probability_rows"]),
                hard_negative_indices=list(current_hard_negative_indices),
                epochs_completed=epoch_index + 1,
                early_stopped=False,
                metrics_report=evaluation["metrics_report"],
            )
            epochs_completed = epoch_index + 1
            learning_rate = self._current_learning_rate(optimizer, scheduler)
            mean_ewc_loss = float(getattr(self, "_last_epoch_mean_ewc_loss", 0.0))
            logger.info(
                "epoch %d/%d | lr=%.2e | train_loss=%.3f | val_loss=%.3f | f1=%.2f | precision=%.2f | recall=%.2f | ewc_loss=%.3f",
                epochs_completed,
                active_config.max_epochs,
                learning_rate,
                current_result.train_loss,
                current_result.eval_loss,
                current_result.f1,
                current_result.precision,
                current_result.recall,
                mean_ewc_loss,
            )
            improved = early_stopper.is_improvement(current_result.eval_loss)
            if improved or best_result is None:
                best_model_state = self._clone_model_state(self.model.state_dict())
                best_result = current_result
            if early_stopper.step(current_result.eval_loss):
                break
        self.model.load_state_dict(best_model_state, strict=False)
        if best_result is None:
            raise RuntimeError("training loop completed without validation results")
        return TrainingLoopResult(
            train_loss=best_result.train_loss,
            eval_loss=best_result.eval_loss,
            accuracy=best_result.accuracy,
            precision=best_result.precision,
            recall=best_result.recall,
            f1=best_result.f1,
            auc_roc=best_result.auc_roc,
            positive_threshold=best_result.positive_threshold,
            threshold_strategy=best_result.threshold_strategy,
            predictions=list(best_result.predictions),
            labels=list(best_result.labels),
            probability_rows=list(best_result.probability_rows),
            hard_negative_indices=list(best_result.hard_negative_indices),
            epochs_completed=epochs_completed,
            early_stopped=early_stopper.stopped,
            metrics_report=best_result.metrics_report,
        )

    def _current_class_weight_tensor(self) -> torch.Tensor | None:
        if self._last_balance_report is None or not self._last_balance_report.class_weights:
            return None
        class_weight_tensor = self._last_balance_report.weights_tensor(
            num_classes=int(self.model_config.output_dim)
        )
        device_type = str(getattr(self.device, "type", self.device)).lower()
        if device_type == "cuda" and torch.cuda.is_available():
            return class_weight_tensor.to(self.device)
        return class_weight_tensor

    def get_metrics_history(self) -> list[MetricsReport]:
        return self.metrics_tracker.history

    @staticmethod
    def _compute_auc_roc(
        labels: list[int], positive_probabilities: list[float]
    ) -> float:
        try:
            return float(roc_auc_score(labels, positive_probabilities))
        except ValueError as exc:
            logger.warning(
                "auc_roc_unavailable_from_current_eval_set: %s",
                exc,
            )
            return math.nan

    def _load_best_checkpoint(self) -> None:
        if not self.model_path.exists():
            raise FileNotFoundError(
                f"best checkpoint unavailable for rollback at {self.model_path}"
            )
        try:
            reloaded_state = load_safetensors(
                str(self.model_path), device=self.device.type
            )
            self.model.load_state_dict(reloaded_state, strict=False)
        except Exception as exc:
            logger.error("failed to load best checkpoint for rollback: %s", exc)
            raise

    def _checkpoint_field_name(self) -> str:
        return re.sub(r"[^A-Za-z0-9_]+", "_", self.model_path.stem).strip("_") or "model"

    def _save_named_checkpoint(self, *, epoch_number: int, f1: float) -> Path:
        checkpoint_path = self.model_path.parent / (
            f"checkpoint_{self._checkpoint_field_name()}_{epoch_number}_{f1:.3f}.pt"
        )
        torch.save(self.model.state_dict(), checkpoint_path)
        return checkpoint_path

    def benchmark_current_model(self, max_samples: int = 1500) -> dict[str, object]:
        samples, source = self.load_evaluation_samples(max_samples=max_samples)
        if not samples:
            raise RuntimeError("No real samples available for benchmark")

        self._invalid_sample_count = 0
        self._invalid_sample_warnings.clear()
        benchmark_dataset = _StreamingFeatureDataset(
            self,
            samples,
            list(range(len(samples))),
        )
        benchmark_loader = DataLoader(
            benchmark_dataset,
            batch_size=512,
            shuffle=False,
            num_workers=self.num_workers,
            pin_memory=self.device.type == "cuda",
            persistent_workers=self.num_workers > 0,
        )

        self.model.eval()
        positive_probabilities: list[float] = []
        labels: list[int] = []
        eval_losses: list[float] = []
        criterion = torch.nn.CrossEntropyLoss()
        with torch.no_grad():
            for batch in benchmark_loader:
                features, batch_labels, _ = self._unpack_batch(batch)
                features = features.to(self.device)
                batch_labels_device = batch_labels.to(self.device)
                logits = self.model(features)
                probs = torch.softmax(logits, dim=1)[:, 1].detach().cpu().tolist()
                positive_probabilities.extend(
                    float(probability) for probability in probs
                )
                labels.extend(batch_labels.cpu().tolist())
                eval_losses.append(float(criterion(logits, batch_labels_device).item()))

        live_metrics = compute_binary_metrics(
            labels, positive_probabilities, self.positive_threshold
        )
        calibrated_metrics = calibrate_positive_threshold(
            labels,
            positive_probabilities,
            fallback_threshold=self.positive_threshold,
        )
        ranked_pairs = sorted(
            zip(positive_probabilities, labels),
            key=lambda item: item[0],
            reverse=True,
        )

        def _precision_at_k(k: int) -> float:
            top = ranked_pairs[: min(k, len(ranked_pairs))]
            if not top:
                return 0.0
            positives = sum(1 for _, label in top if int(label) == 1)
            return float(positives / len(top))

        reciprocal_rank = 0.0
        for rank, (_, label) in enumerate(ranked_pairs, start=1):
            if int(label) == 1:
                reciprocal_rank = 1.0 / float(rank)
                break

        loss = float(sum(eval_losses) / max(len(eval_losses), 1))
        metrics_registry.set_gauge("benchmark_loss", loss)
        metrics_registry.set_gauge("benchmark_precision_at_5", _precision_at_k(5))
        metrics_registry.set_gauge("benchmark_precision_at_10", _precision_at_k(10))
        metrics_registry.set_gauge("benchmark_mrr", reciprocal_rank)
        metrics_registry.set_gauge("benchmark_f1", float(calibrated_metrics["f1"]))
        return {
            "samples": len(samples),
            "source": source,
            "loss": loss,
            "threshold": float(live_metrics["threshold"]),
            "accuracy": float(live_metrics["accuracy"]),
            "precision": float(live_metrics["precision"]),
            "recall": float(live_metrics["recall"]),
            "f1": float(live_metrics["f1"]),
            "precision_at_5": _precision_at_k(5),
            "precision_at_10": _precision_at_k(10),
            "mrr": reciprocal_rank,
            "rejected_samples": self._invalid_sample_count,
            "recommended_threshold": float(calibrated_metrics["threshold"]),
            "recommended_strategy": str(calibrated_metrics["strategy"]),
            "recommended_f1": float(calibrated_metrics["f1"]),
        }

    def run_incremental_epoch(
        self,
        sample_weights: dict[str, float] | list[float] | np.ndarray | None = None,
    ) -> EpochResult:
        samples = self.load_new_samples()
        epoch_number = int(self.training_state.get("epoch_number", 0)) + 1
        if len(samples) < 10:
            logger.info("insufficient samples")
            return EpochResult(
                0.0, 0.0, 0.0, 0.0, 0.0, len(samples), epoch_number, False, False
            )

        build_dataset_signature = inspect.signature(self.build_dataset)
        if "include_train_dataset_indices" in build_dataset_signature.parameters:
            train_loader, eval_loader = self.build_dataset(
                samples,
                include_train_dataset_indices=True,
            )
        else:
            train_loader, eval_loader = self.build_dataset(samples)
        native_reward_weights = self._resolve_native_reward_weight_lookup(samples)
        merged_sample_weights = self._merge_incremental_sample_weight_sources(
            native_reward_weights,
            sample_weights,
        )
        resolved_train_sample_weights = self._resolve_train_sample_weights(
            samples,
            train_loader,
            merged_sample_weights,
        )
        self._log_native_reward_weighting(
            samples=samples,
            train_loader=train_loader,
            native_reward_weights=native_reward_weights,
            resolved_train_sample_weights=resolved_train_sample_weights,
        )
        optimizer = AdamW(
            self.model.parameters(),
            lr=self.optimizer_config.learning_rate,
            weight_decay=0.01,
        )
        optimizer_steps_per_epoch = max(
            1,
            math.ceil(
                max(len(train_loader), 1) / self.optimizer_config.accumulation_steps
            ),
        )
        total_scheduler_steps = max(
            1,
            optimizer_steps_per_epoch * self.optimizer_config.max_epochs,
        )
        scheduler = WarmupCosineScheduler(
            optimizer,
            total_steps=total_scheduler_steps,
            warmup_steps=self.optimizer_config.resolved_warmup_steps(
                total_scheduler_steps
            ),
            min_lr=self.optimizer_config.min_learning_rate,
            warmup_start_factor=self.optimizer_config.warmup_start_factor,
        )
        amp_enabled = self.optimizer_config.amp_enabled(self.device)
        if self.optimizer_config.use_amp and not amp_enabled:
            logger.info(
                "CUDA AMP requested but unavailable on device=%s; using full precision",
                getattr(self.device, "type", self.device),
            )
        scaler = (
            torch.cuda.amp.GradScaler(enabled=True)
            if amp_enabled
            else None
        )
        label_smoothing = float(self.optimizer_config.label_smoothing)
        logger.info(
            "incremental_label_smoothing_configured epoch=%d label_smoothing=%.6f",
            epoch_number,
            label_smoothing,
        )
        train_criterion = torch.nn.CrossEntropyLoss(
            weight=self._current_class_weight_tensor(),
            reduction="none",
            label_smoothing=label_smoothing,
        )
        eval_criterion = torch.nn.CrossEntropyLoss()
        previous_state = self._clone_model_state(self.model.state_dict())

        start_time = time.perf_counter()
        training_loop_result = self.train(
            train_loader,
            optimizer,
            scheduler,
            train_criterion,
            scaler,
            sample_weights=resolved_train_sample_weights,
            val_loader=eval_loader,
            eval_criterion=eval_criterion,
            optimiser_config=self.optimizer_config,
            return_history=True,
        )

        labels_out = list(training_loop_result.labels)
        probability_rows = list(training_loop_result.probability_rows)
        positive_threshold = float(training_loop_result.positive_threshold)
        predictions = list(training_loop_result.predictions)
        prediction_hash = self._hash_predictions(predictions, probability_rows)
        accuracy = float(training_loop_result.accuracy)
        precision = float(training_loop_result.precision)
        recall = float(training_loop_result.recall)
        f1 = float(training_loop_result.f1)
        auc_roc = float(training_loop_result.auc_roc)
        eval_loss = float(training_loop_result.eval_loss)
        metrics_report = training_loop_result.metrics_report
        self._last_metrics_report = metrics_report
        duration_ms = (time.perf_counter() - start_time) * 1000
        snapshot = AccuracySnapshot(
            epoch=epoch_number,
            accuracy=accuracy,
            precision=precision,
            recall=recall,
            f1=f1,
            auc_roc=auc_roc,
            taken_at=datetime.now(timezone.utc).isoformat(),
        )
        self._accuracy_history.add(snapshot)

        from backend.training.runtime_status_validator import (
            PromotionReadinessError,
            validate_promotion_readiness,
        )

        governance_error: PromotionReadinessError | None = None
        promotion_ready = False
        try:
            validate_promotion_readiness(snapshot)
            promotion_ready = True
            result_status = "COMPLETED"
        except PromotionReadinessError as exc:
            governance_error = exc
            result_status = exc.status
            logger.critical(
                "incremental epoch governance hard block: status=%s epoch=%d f1=%.4f precision=%.4f recall=%.4f",
                exc.status,
                epoch_number,
                f1,
                precision,
                recall,
            )

        logger.info(
            "incremental_threshold_calibrated",
            extra={
                "event": "incremental_threshold_calibrated",
                "threshold": positive_threshold,
                "strategy": training_loop_result.threshold_strategy,
                "eval_samples": len(labels_out),
                "precision": precision,
                "recall": recall,
                "f1": f1,
                "prediction_hash": prediction_hash,
            },
        )
        if metrics_report is not None:
            logger.info(
                "incremental per-class validation worst=%s f1=%.4f best=%s f1=%.4f",
                metrics_report.worst_class.name,
                metrics_report.worst_class.f1,
                metrics_report.best_class.name,
                metrics_report.best_class.f1,
            )

        if governance_error is not None:
            logger.info(
                "restoring previous model state after governance hard block for epoch=%d",
                epoch_number,
            )
            metrics_registry.increment("training_governance_block", 1.0)
            self._restore_previous_state(previous_state)
            raise governance_error

        if self._accuracy_history.should_rollback():
            best_snapshot = self._accuracy_history.get_best()
            last_snapshot = self._accuracy_history.get_last()
            logger.warning(
                "f1 rollback triggered, restoring best checkpoint: last_f1=%.4f best_f1=%.4f max_drop=%.4f",
                last_snapshot.f1,
                best_snapshot.f1,
                AccuracyThresholds.MAX_DROP_FROM_BEST,
            )
            metrics_registry.increment("training_rollback", 1.0)
            self._load_best_checkpoint()
            return EpochResult(
                accuracy=accuracy,
                precision=precision,
                recall=recall,
                f1=f1,
                eval_loss=eval_loss,
                samples_processed=len(samples),
                epoch_number=epoch_number,
                rollback=True,
                early_stopped=False,
                prediction_hash=prediction_hash,
                status=result_status,
                metrics_report=metrics_report,
            )

        if accuracy < self.baseline_accuracy - 0.05:
            logger.critical("accuracy dropped > 5%, rolling back")
            metrics_registry.increment("training_rollback", 1.0)
            self._restore_previous_state(previous_state)
            return EpochResult(
                accuracy=accuracy,
                precision=precision,
                recall=recall,
                f1=f1,
                eval_loss=eval_loss,
                samples_processed=len(samples),
                epoch_number=epoch_number,
                rollback=True,
                early_stopped=False,
                prediction_hash=prediction_hash,
                status=result_status,
                metrics_report=metrics_report,
            )

        early_stopped = bool(training_loop_result.early_stopped)
        best_eval_loss = self.training_state.get("best_eval_loss")
        no_improve_count = int(self.training_state.get("no_improve_count", 0))
        if promotion_ready and (
            best_eval_loss is None or eval_loss < float(best_eval_loss)
        ):
            best_eval_loss = eval_loss
            no_improve_count = 0
            self._save_model_state(self.model.state_dict(), epoch_number=epoch_number)
            self._save_named_checkpoint(epoch_number=epoch_number, f1=f1)
            self._persist_checkpoint_metrics(
                accuracy=accuracy,
                precision=precision,
                recall=recall,
                f1=f1,
                positive_threshold=positive_threshold,
            )
        else:
            if not promotion_ready:
                logger.warning(
                    "model promotion blocked by readiness validation: status=%s f1=%.4f precision=%.4f recall=%.4f",
                    result_status,
                    f1,
                    precision,
                    recall,
                )
            no_improve_count += 1
            if no_improve_count >= self.optimizer_config.patience:
                early_stopped = True
                logger.info("early stopping triggered")
                reloaded_state = load_safetensors(
                    str(self.model_path), device=self.device.type
                )
                self.model.load_state_dict(reloaded_state, strict=False)

        gpu_metrics = self.state_manager.get_gpu_metrics(force_emit=True)
        self.state_manager.emit_training_metrics(
            TrainingMetrics(
                status="training",
                elapsed_seconds=duration_ms / 1000.0,
                last_accuracy=accuracy,
                gpu_usage_percent=gpu_metrics.get("gpu_usage_percent"),
                gpu_memory_used_mb=gpu_metrics.get("gpu_memory_used_mb"),
            ),
            calibration_labels=labels_out,
            calibration_probabilities=[row[1] for row in probability_rows],
            distribution=probability_rows,
            epoch_number=epoch_number,
        )
        metrics_registry.set_gauge("model_precision", precision)
        metrics_registry.set_gauge("model_recall", recall)
        metrics_registry.set_gauge("model_f1", f1)
        metrics_registry.set_gauge("training_samples_processed", float(len(samples)))
        metrics_registry.set_gauge("training_epoch_number", float(epoch_number))

        self.training_state = {
            "last_training_time": max(
                sample.ingested_at for sample in samples
            ).isoformat(),
            "epoch_number": epoch_number,
            "best_eval_loss": best_eval_loss,
            "no_improve_count": no_improve_count,
            "prediction_hash": prediction_hash,
            "metrics_report": metrics_report.to_dict() if metrics_report is not None else None,
        }
        self._atomic_write_json(self.state_path, self.training_state)

        return EpochResult(
            accuracy=accuracy,
            precision=precision,
            recall=recall,
            f1=f1,
            eval_loss=eval_loss,
            samples_processed=len(samples),
            epoch_number=epoch_number,
            rollback=False,
            early_stopped=early_stopped,
            prediction_hash=prediction_hash,
            status=result_status,
            metrics_report=metrics_report,
        )


MODULE_SHA256 = log_module_sha256(__file__, logger, __name__)
