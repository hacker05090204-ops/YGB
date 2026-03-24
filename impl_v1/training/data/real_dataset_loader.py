"""Verified dataset loader for accuracy-first training.

The supervised pipeline accepts only validated outcomes and rejects synthetic,
noisy, or unverified samples.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Optional, Tuple

import torch
from torch.utils.data import DataLoader, Dataset

try:
    from torch.utils.data.distributed import DistributedSampler
except ImportError:  # pragma: no cover
    DistributedSampler = None

from impl_v1.training.data.verified_dataset import (
    VerifiedFindingRecord,
    encode_verified_record,
    load_verified_records,
    split_verified_records,
    verified_dataset_statistics,
)


FORBIDDEN_FIELDS = frozenset(
    [
        "valid",
        "accepted",
        "rejected",
        "severity",
        "platform_decision",
        "decision",
        "outcome",
        "verified",
        "actual_positive",
        "proof_status",
    ]
)

_DATASET_CACHE: dict[
    tuple[int, int, int, float, tuple[str, ...], bool],
    tuple[list["TrainingSample"], torch.Tensor, torch.Tensor, dict[str, Any]],
] = {}
_VALIDATION_CACHE: dict[tuple[int, int, float, tuple[str, ...]], tuple[bool, str]] = {}


@dataclass(frozen=True)
class DatasetConfig:
    """Configuration for verified supervised training data."""

    total_samples: int = 5000
    holdout_fraction: float = 0.2
    min_verified_samples: int = 50
    min_class_samples: int = 10
    feature_dim: int = 256
    dataset_paths: tuple[str, ...] = tuple()


@dataclass(frozen=True)
class TrainingSample:
    """Single verified training sample."""

    id: str
    features: dict[str, Any]
    label: int
    fingerprint: str
    validation_source: str
    is_holdout: bool
    is_duplicate: bool


def _config_paths(config: DatasetConfig) -> tuple[str, ...]:
    if config.dataset_paths:
        return tuple(config.dataset_paths)
    env_value = os.getenv("YGB_VERIFIED_DATASET_PATHS", "").strip()
    if not env_value:
        return tuple()
    return tuple(item.strip() for item in env_value.split(os.pathsep) if item.strip())


def strip_forbidden_fields(data: dict) -> dict:
    """Remove governance-forbidden outcome fields."""
    return {k: v for k, v in data.items() if k.lower() not in FORBIDDEN_FIELDS}


def validate_no_forbidden_fields(data: dict) -> bool:
    """Ensure no forbidden labels/outcomes leak into features."""
    return all(key.lower() not in FORBIDDEN_FIELDS for key in data.keys())


def _record_to_feature_payload(record: VerifiedFindingRecord) -> dict[str, Any]:
    return strip_forbidden_fields(
        {
            "category": record.category,
            "title": record.title,
            "description": record.description,
            "url": record.url,
            "payload_tested": bool(record.evidence.get("payload_tested")),
            "sql_errors_count": len(record.evidence.get("sql_errors") or []),
            "reflected_parameters_count": len(
                record.evidence.get("reflected_parameters") or []
            ),
            "needs_manual_review": bool(record.evidence.get("needs_manual_review")),
            "validation_source": record.validation_source,
            "duplicate_hint": bool(record.duplicate),
        }
    )


def _load_split_records(
    config: DatasetConfig,
) -> tuple[list[VerifiedFindingRecord], list[VerifiedFindingRecord]]:
    paths = _config_paths(config)
    records = load_verified_records(paths or None)
    if config.total_samples > 0 and len(records) > config.total_samples:
        records = records[-config.total_samples :]
    return split_verified_records(records, holdout_fraction=config.holdout_fraction)


class RealTrainingDataset(Dataset):
    """PyTorch dataset backed only by validated finding outcomes."""

    def __init__(
        self,
        config: DatasetConfig = None,
        seed: int = 42,
        feature_dim: int = 256,
        is_holdout: bool = False,
    ):
        self.config = config or DatasetConfig(feature_dim=feature_dim)
        self.seed = seed
        self.feature_dim = feature_dim or self.config.feature_dim
        self.is_holdout = is_holdout
        cache_key = (
            self.config.total_samples,
            seed,
            self.feature_dim,
            self.config.holdout_fraction,
            _config_paths(self.config),
            is_holdout,
        )

        cached = _DATASET_CACHE.get(cache_key)
        if cached is not None:
            (
                self.samples,
                self._features_tensor,
                self._labels_tensor,
                self._stats,
            ) = cached
            return

        train_records, holdout_records = _load_split_records(self.config)
        selected = holdout_records if is_holdout else train_records

        self.samples: list[TrainingSample] = []
        features_list: list[list[float]] = []
        labels_list: list[int] = []

        for record in selected:
            feature_payload = _record_to_feature_payload(record)
            self.samples.append(
                TrainingSample(
                    id=record.fingerprint,
                    features=feature_payload,
                    label=1 if record.actual_positive else 0,
                    fingerprint=record.fingerprint,
                    validation_source=record.validation_source,
                    is_holdout=is_holdout,
                    is_duplicate=record.duplicate,
                )
            )
            features_list.append(encode_verified_record(record, self.feature_dim))
            labels_list.append(1 if record.actual_positive else 0)

        if features_list:
            self._features_tensor = torch.tensor(features_list, dtype=torch.float32)
            self._labels_tensor = torch.tensor(labels_list, dtype=torch.long)
        else:
            self._features_tensor = torch.empty(
                (0, self.feature_dim), dtype=torch.float32
            )
            self._labels_tensor = torch.empty((0,), dtype=torch.long)

        self._stats = verified_dataset_statistics(selected)
        self._stats["feature_dim"] = self.feature_dim
        self._stats["is_holdout"] = self.is_holdout

        _DATASET_CACHE[cache_key] = (
            self.samples,
            self._features_tensor,
            self._labels_tensor,
            self._stats,
        )

    def __len__(self) -> int:
        return len(self.samples)

    def __getitem__(self, idx: int) -> Tuple[torch.Tensor, torch.Tensor]:
        return self._features_tensor[idx], self._labels_tensor[idx]

    def get_statistics(self) -> dict:
        return dict(self._stats)


def create_training_dataloader(
    batch_size: int = 1024,
    num_workers: int = 4,
    pin_memory: bool = True,
    prefetch_factor: int = 2,
    seed: int = 42,
) -> Tuple[DataLoader, DataLoader, dict]:
    """Create DataLoaders from validated findings only."""
    config = DatasetConfig()
    train_dataset = RealTrainingDataset(config=config, seed=seed, is_holdout=False)
    holdout_dataset = RealTrainingDataset(config=config, seed=seed, is_holdout=True)

    if len(train_dataset) == 0 or len(holdout_dataset) == 0:
        raise ValueError(
            "Verified dataset unavailable. Provide validated records via YGB_VERIFIED_DATASET_PATHS or reports/verified_findings.jsonl"
        )

    distributed_enabled = bool(
        DistributedSampler is not None
        and torch.distributed.is_available()
        and torch.distributed.is_initialized()
        and torch.distributed.get_world_size() > 1
    )
    train_sampler = (
        DistributedSampler(train_dataset, shuffle=True) if distributed_enabled else None
    )
    holdout_sampler = (
        DistributedSampler(holdout_dataset, shuffle=False)
        if distributed_enabled
        else None
    )

    effective_train_batch = max(1, min(batch_size, len(train_dataset)))
    effective_holdout_batch = max(1, min(batch_size, len(holdout_dataset)))

    train_loader = DataLoader(
        train_dataset,
        batch_size=effective_train_batch,
        shuffle=train_sampler is None,
        num_workers=num_workers,
        pin_memory=pin_memory,
        prefetch_factor=prefetch_factor if num_workers > 0 else None,
        persistent_workers=num_workers > 0,
        drop_last=len(train_dataset) >= effective_train_batch
        and effective_train_batch > 1,
        sampler=train_sampler,
    )

    holdout_loader = DataLoader(
        holdout_dataset,
        batch_size=effective_holdout_batch,
        shuffle=False,
        num_workers=num_workers,
        pin_memory=pin_memory,
        prefetch_factor=prefetch_factor if num_workers > 0 else None,
        persistent_workers=num_workers > 0,
        sampler=holdout_sampler,
    )

    stats = {
        "train": train_dataset.get_statistics(),
        "holdout": holdout_dataset.get_statistics(),
        "batch_size": batch_size,
        "effective_train_batch_size": effective_train_batch,
        "effective_holdout_batch_size": effective_holdout_batch,
        "num_workers": num_workers,
        "pin_memory": pin_memory,
        "distributed": distributed_enabled,
    }
    return train_loader, holdout_loader, stats


def validate_dataset_integrity(
    config: Optional[DatasetConfig] = None,
) -> Tuple[bool, str]:
    """Validate the supervised dataset before training starts."""
    cfg = config or DatasetConfig()
    cache_key = (
        cfg.total_samples,
        cfg.min_verified_samples,
        cfg.holdout_fraction,
        _config_paths(cfg),
    )
    if cache_key in _VALIDATION_CACHE:
        return _VALIDATION_CACHE[cache_key]

    try:
        train_dataset = RealTrainingDataset(config=cfg, is_holdout=False)
        holdout_dataset = RealTrainingDataset(config=cfg, is_holdout=True)
        train_stats = train_dataset.get_statistics()
        holdout_stats = holdout_dataset.get_statistics()

        if train_stats["total"] < cfg.min_verified_samples:
            result = (
                False,
                f"Insufficient verified samples: {train_stats['total']} < {cfg.min_verified_samples}",
            )
            _VALIDATION_CACHE[cache_key] = result
            return result

        if train_stats["positive"] < cfg.min_class_samples:
            result = (
                False,
                f"Insufficient verified positives: {train_stats['positive']} < {cfg.min_class_samples}",
            )
            _VALIDATION_CACHE[cache_key] = result
            return result

        if train_stats["negative"] < cfg.min_class_samples:
            result = (
                False,
                f"Insufficient verified negatives: {train_stats['negative']} < {cfg.min_class_samples}",
            )
            _VALIDATION_CACHE[cache_key] = result
            return result

        if holdout_stats["total"] == 0:
            result = (False, "Holdout split is empty; cannot evaluate accuracy")
            _VALIDATION_CACHE[cache_key] = result
            return result

        for sample in train_dataset.samples[:20]:
            if not validate_no_forbidden_fields(sample.features):
                result = (
                    False,
                    "Forbidden outcome fields leaked into training features",
                )
                _VALIDATION_CACHE[cache_key] = result
                return result

        result = (
            True,
            "Verified dataset valid: "
            f"train={train_stats['total']} holdout={holdout_stats['total']} "
            f"positives={train_stats['positive']} negatives={train_stats['negative']}",
        )
        _VALIDATION_CACHE[cache_key] = result
        return result
    except Exception as exc:  # pragma: no cover - defensive validation path
        result = (False, f"Verified dataset validation failed: {exc}")
        _VALIDATION_CACHE[cache_key] = result
        return result
