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
from typing import Callable, Protocol

import numpy as np
import torch
from sklearn.metrics import accuracy_score, f1_score, precision_score, recall_score, roc_auc_score
from torch.optim import AdamW
from torch.optim.lr_scheduler import OneCycleLR
from torch.utils.data import DataLoader, Dataset

from backend.ingestion._integrity import log_module_sha256
from backend.bridge.bridge_state import get_bridge_state
from backend.ingestion.normalizer import SampleQualityScorer
from backend.ingestion.models import IngestedSample
from backend.observability.metrics import metrics_registry
from backend.training.feature_extractor import extract
from backend.training.model_thresholds import (
    calibrate_positive_threshold,
    compute_binary_metrics,
    load_threshold_artifact,
    save_threshold_artifact,
)
from backend.training.safetensors_store import SafetensorsFeatureStore
from backend.training.state_manager import TrainingMetrics, get_training_state_manager
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
_IMPACT_RE = re.compile(r"CVSS:(?P<score>[0-9.]+)\|(?P<severity>[^|]+)")
_CVE_ID_RE = re.compile(r"^CVE-\d{4}-\d{4,}$", re.IGNORECASE)


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


TrainingResult = EpochResult


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
    MIN_SEVERITY_DISTRIBUTION = 0.1
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
        for severity in self._SEVERITY_CLASSES:
            if severity_distribution[severity] < self.MIN_SEVERITY_DISTRIBUTION:
                failed_reasons.append(
                    "severity_distribution_below_min:"
                    f"{severity}={severity_distribution[severity]:.4f}"
                )

        return DatasetQualityReport(
            passed=not failed_reasons,
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
            if distribution < self.MIN_SEVERITY_DISTRIBUTION:
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

    def __init__(self, trainer: "IncrementalTrainer", samples: list[IngestedSample], indices: list[int]) -> None:
        self._trainer = trainer
        self._samples = samples
        self._indices = tuple(indices)

    def __len__(self) -> int:
        return len(self._indices)

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
            else project_root / DEFAULT_FEATURE_STORE_ROOT
        )
        self.feature_store = SafetensorsFeatureStore(self.feature_store_root)
        self._indexed_raw_samples_cache: list[tuple[str, IngestedSample]] | None = None
        self._invalid_sample_warnings: set[str] = set()
        self._invalid_sample_count: int = 0
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.model_config = create_model_config(
            input_dim=512,
            output_dim=2,
            hidden_dims=(1024, 512, 256, 128),
            dropout=0.3,
            learning_rate=3e-4,
            batch_size=256,
            epochs=1,
            seed=42,
        )
        self.training_state = self._load_training_state()
        self.baseline_state = self._load_baseline_state()
        self.baseline_accuracy = float(self.baseline_state["baseline_accuracy"])
        self.positive_threshold = float(self.baseline_state["positive_threshold"])
        self.state_manager = get_training_state_manager()
        self.model = self._load_or_initialize_model()
        self.dataset_quality_gate = DatasetQualityGate(
            feature_loader=self._load_or_compute_feature
        )
        self._last_dataset_quality_report: DatasetQualityReport | None = None
        self._accuracy_history = AccuracyHistory()

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
        if tuple(feature_cpu.shape) != (512,):
            raise RuntimeError(
                f"REAL_DATA_REQUIRED: feature tensor must have shape (512,), got {tuple(feature_cpu.shape)}"
            )
        compressed = feature_cpu.reshape(256, 2).mean(dim=1).numpy().astype(np.float32, copy=False)
        return compressed.reshape(1, 256)

    @staticmethod
    def _expand_feature_tensor(stored_feature: np.ndarray) -> torch.Tensor:
        feature_row = np.asarray(stored_feature)
        if feature_row.dtype != np.float32 or feature_row.shape != (256,):
            raise ValueError(
                f"stored feature row must have shape (256,) and dtype float32, got {feature_row.shape}/{feature_row.dtype}"
            )
        expanded = np.repeat(feature_row, 2).astype(np.float32, copy=False)
        return torch.from_numpy(expanded.copy())

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
            "original_feature_dim": 512,
            "stored_feature_dim": 256,
            "compression": "pairwise_mean_repeat_v1",
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
            if shard.features.shape != (1, 256) or not stats_available:
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
            return self._expand_feature_tensor(shard.features[0])
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

        raw_feature = extract(sample).detach().cpu().to(dtype=torch.float32)
        feature, stats_payload = self._normalize_feature_tensor(raw_feature)
        if tuple(feature.shape) != (512,):
            raise RuntimeError(
                f"REAL_DATA_REQUIRED: feature extractor returned invalid shape {tuple(feature.shape)}"
            )
        try:
            self.feature_store.write(
                sample.sha256_hash,
                self._compress_feature_tensor(feature),
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
        self, samples: list[IngestedSample]
    ) -> tuple[DataLoader, DataLoader]:
        if self.num_workers > 0 and can_ai_execute()[0]:
            raise RuntimeError("GUARD")
        quality_report = self.dataset_quality_gate.validate(samples)
        self._last_dataset_quality_report = quality_report
        if not quality_report.passed:
            raise DatasetQualityError(quality_report.failed_reasons)

        indices = list(range(len(samples)))
        eval_count = min(len(indices) - 1, max(2, int(len(indices) * 0.1)))
        eval_indices = self._deterministic_indices(len(indices), eval_count)
        eval_index_set = set(eval_indices)
        train_indices = [index for index in indices if index not in eval_index_set]
        if not train_indices or not eval_indices:
            raise RuntimeError(
                "REAL_DATA_REQUIRED: Deterministic train/validation split failed"
            )

        train_dataset = _StreamingFeatureDataset(self, samples, train_indices)
        eval_dataset = _StreamingFeatureDataset(self, samples, eval_indices)
        train_generator = torch.Generator().manual_seed(self.model_config.seed)
        train_loader = DataLoader(
            train_dataset,
            batch_size=256,
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

    def _step_optimizer(self, optimizer: torch.optim.Optimizer, scaler) -> None:
        if scaler is not None:
            scaler.unscale_(optimizer)
            torch.nn.utils.clip_grad_norm_(self.model.parameters(), 1.0)
            scaler.step(optimizer)
            scaler.update()
        else:
            torch.nn.utils.clip_grad_norm_(self.model.parameters(), 1.0)
            optimizer.step()
        optimizer.zero_grad(set_to_none=True)

    def get_accuracy_history(self) -> list[AccuracySnapshot]:
        return self._accuracy_history.as_list()

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
            for features, batch_labels in benchmark_loader:
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

    def run_incremental_epoch(self) -> EpochResult:
        samples = self.load_new_samples()
        epoch_number = int(self.training_state.get("epoch_number", 0)) + 1
        if len(samples) < 10:
            logger.info("insufficient samples")
            return EpochResult(
                0.0, 0.0, 0.0, 0.0, 0.0, len(samples), epoch_number, False, False
            )

        train_loader, eval_loader = self.build_dataset(samples)
        optimizer = AdamW(self.model.parameters(), lr=3e-4, weight_decay=0.01)
        scheduler = OneCycleLR(
            optimizer,
            max_lr=3e-4,
            steps_per_epoch=max(len(train_loader), 1),
            epochs=1,
            pct_start=0.3,
        )
        scaler = torch.amp.GradScaler("cuda") if self.device.type == "cuda" else None
        criterion = torch.nn.CrossEntropyLoss()
        previous_state = {
            name: tensor.detach().cpu().clone()
            for name, tensor in self.model.state_dict().items()
        }

        start_time = time.perf_counter()
        self.model.train()
        optimizer.zero_grad(set_to_none=True)
        accum_steps = 4
        step_count = 0
        for step_count, (features, labels) in enumerate(train_loader, start=1):
            features = features.to(self.device)
            labels = labels.to(self.device)
            autocast_context = (
                torch.amp.autocast("cuda")
                if self.device.type == "cuda"
                else nullcontext()
            )
            with autocast_context:
                outputs = self.model(features)
                loss = criterion(outputs, labels)
                scaled_loss = loss / accum_steps
            self._backward_pass(scaled_loss, scaler)

            if step_count % accum_steps == 0:
                self._step_optimizer(optimizer, scaler)
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
            self._step_optimizer(optimizer, scaler)
            scheduler.step()

        self.model.eval()
        eval_losses: list[float] = []
        predictions: list[int] = []
        labels_out: list[int] = []
        probability_rows: list[list[float]] = []
        with torch.no_grad():
            for features, labels in eval_loader:
                features = features.to(self.device)
                labels = labels.to(self.device)
                logits = self.model(features)
                probs = torch.softmax(logits, dim=1)
                eval_losses.append(float(criterion(logits, labels).item()))
                labels_out.extend(labels.cpu().tolist())
                probability_rows.extend(probs.cpu().tolist())

        positive_probabilities = [float(row[1]) for row in probability_rows]
        threshold_metrics = calibrate_positive_threshold(
            labels_out,
            positive_probabilities,
            fallback_threshold=self.positive_threshold,
        )
        positive_threshold = float(threshold_metrics["threshold"])
        predictions = list(threshold_metrics["predictions"])
        prediction_hash = self._hash_predictions(predictions, probability_rows)
        accuracy = float(threshold_metrics["accuracy"])
        precision = float(threshold_metrics["precision"])
        recall = float(threshold_metrics["recall"])
        f1 = float(threshold_metrics["f1"])
        auc_roc = self._compute_auc_roc(labels_out, positive_probabilities)
        eval_loss = float(sum(eval_losses) / max(len(eval_losses), 1))
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
            validate_promotion_readiness,
        )

        promotion_ready = validate_promotion_readiness(snapshot)
        result_status = "COMPLETED"

        if precision < AccuracyThresholds.MIN_PRECISION:
            logger.critical(
                "precision below minimum threshold: precision=%.4f min_precision=%.4f",
                precision,
                AccuracyThresholds.MIN_PRECISION,
            )
        if recall < AccuracyThresholds.MIN_RECALL:
            logger.warning(
                "recall below minimum threshold: recall=%.4f min_recall=%.4f",
                recall,
                AccuracyThresholds.MIN_RECALL,
            )
        if f1 < AccuracyThresholds.MIN_F1:
            result_status = "BLOCKED_LOW_ACCURACY"
            logger.critical(
                "final f1 below minimum threshold, blocking promotion: f1=%.4f min_f1=%.4f",
                f1,
                AccuracyThresholds.MIN_F1,
            )
        elif not promotion_ready:
            result_status = "PROMOTION_BLOCKED"

        logger.info(
            "incremental_threshold_calibrated",
            extra={
                "event": "incremental_threshold_calibrated",
                "threshold": positive_threshold,
                "strategy": str(threshold_metrics["strategy"]),
                "eval_samples": len(labels_out),
                "precision": precision,
                "recall": recall,
                "f1": f1,
                "prediction_hash": prediction_hash,
            },
        )

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
            )

        early_stopped = False
        best_eval_loss = self.training_state.get("best_eval_loss")
        no_improve_count = int(self.training_state.get("no_improve_count", 0))
        if promotion_ready and (
            best_eval_loss is None or eval_loss < float(best_eval_loss)
        ):
            best_eval_loss = eval_loss
            no_improve_count = 0
            self._save_model_state(self.model.state_dict(), epoch_number=epoch_number)
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
            if no_improve_count >= 3:
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
        )


MODULE_SHA256 = log_module_sha256(__file__, logger, __name__)
