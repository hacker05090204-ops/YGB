"""SafeTensors-backed feature shard store for real training artifacts."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import numpy as np
from safetensors import safe_open
from safetensors.numpy import load_file as load_safetensors_file
from safetensors.numpy import save_file as save_safetensors_file


FEATURE_TENSOR_KEY = "features"
LABEL_TENSOR_KEY = "labels"
METADATA_JSON_KEY = "json_metadata"
FEATURE_DIM_METADATA_KEY = "ygb_feature_dim"
FEATURE_DIM = 256


@dataclass(frozen=True)
class FeatureShard:
    """Materialized feature shard payload."""

    features: np.ndarray
    labels: np.ndarray
    metadata: dict[str, Any]

    def __iter__(self) -> Iterable[object]:
        yield self.features
        yield self.labels
        yield self.metadata


class SafetensorsFeatureStore:
    """Single source of truth for feature shards stored as `.safetensors`."""

    def __init__(self, root: Path | str, *, feature_dim: int = FEATURE_DIM) -> None:
        self.root = Path(root)
        self.feature_dim = self._coerce_feature_dim(feature_dim)

    def shard_path(self, shard_name: str | Path) -> Path:
        normalized_name = self._normalize_shard_name(shard_name)
        return self.root / f"{normalized_name}.safetensors"

    def write(
        self,
        shard_name: str | Path,
        features: np.ndarray,
        labels: np.ndarray,
        metadata: dict[str, Any] | None = None,
    ) -> Path:
        target_path = self.shard_path(shard_name)
        target_path.parent.mkdir(parents=True, exist_ok=True)

        feature_array = self._coerce_features_for_write(
            target_path,
            features,
            expected_feature_dim=self.feature_dim,
        )
        label_array = self._coerce_labels_for_write(
            target_path,
            labels,
            expected_rows=feature_array.shape[0],
        )
        metadata_payload = self._serialize_metadata(metadata)
        temp_path = Path(f"{target_path}.tmp")

        try:
            save_safetensors_file(
                {
                    FEATURE_TENSOR_KEY: feature_array,
                    LABEL_TENSOR_KEY: label_array,
                },
                str(temp_path),
                metadata={
                    METADATA_JSON_KEY: metadata_payload,
                    FEATURE_DIM_METADATA_KEY: str(self.feature_dim),
                },
            )
            os.replace(str(temp_path), str(target_path))
        except (OSError, ValueError, TypeError):
            if temp_path.exists():
                temp_path.unlink()
            raise

        return target_path

    def read(self, shard_name: str | Path) -> FeatureShard:
        return self.read_path(
            self.shard_path(shard_name),
            expected_feature_dim=self.feature_dim,
        )

    def list_shards(self) -> list[str]:
        if not self.root.exists():
            return []
        return sorted(path.stem for path in self.root.glob("*.safetensors"))

    def shard_exists(self, shard_name: str | Path) -> bool:
        return self.shard_path(shard_name).exists()

    def delete_shard(self, shard_name: str | Path) -> bool:
        target_path = self.shard_path(shard_name)
        if not target_path.exists():
            return False
        target_path.unlink()
        return True

    def total_samples(self) -> int:
        total = 0
        for shard_name in self.list_shards():
            total += int(self.read(shard_name).labels.shape[0])
        return total

    @classmethod
    def read_path(
        cls,
        path: Path | str,
        *,
        expected_feature_dim: int | None = None,
    ) -> FeatureShard:
        target_path = Path(path)
        if not target_path.exists():
            raise FileNotFoundError(f"Feature shard not found: {target_path}")

        tensors = load_safetensors_file(str(target_path))
        metadata, stored_feature_dim = cls._read_metadata(target_path)
        resolved_feature_dim = cls._resolve_feature_dim(
            target_path,
            expected_feature_dim=expected_feature_dim,
            stored_feature_dim=stored_feature_dim,
        )
        feature_array = np.asarray(tensors.get(FEATURE_TENSOR_KEY))
        label_array = np.asarray(tensors.get(LABEL_TENSOR_KEY))
        cls._validate_loaded_arrays(
            target_path,
            feature_array,
            label_array,
            expected_feature_dim=resolved_feature_dim,
        )
        return FeatureShard(
            features=feature_array,
            labels=label_array,
            metadata=metadata,
        )

    @staticmethod
    def _coerce_feature_dim(feature_dim: int) -> int:
        try:
            parsed = int(feature_dim)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"feature_dim must be a positive integer, got {feature_dim!r}") from exc
        if parsed <= 0:
            raise ValueError(f"feature_dim must be a positive integer, got {parsed}")
        return parsed

    @classmethod
    def _resolve_feature_dim(
        cls,
        path: Path,
        *,
        expected_feature_dim: int | None,
        stored_feature_dim: int | None,
    ) -> int:
        if expected_feature_dim is not None:
            normalized_expected = cls._coerce_feature_dim(expected_feature_dim)
            if (
                stored_feature_dim is not None
                and stored_feature_dim != normalized_expected
            ):
                raise ValueError(
                    f"{path}: stored feature_dim {stored_feature_dim} does not match expected {normalized_expected}"
                )
            return normalized_expected
        if stored_feature_dim is not None:
            return stored_feature_dim
        return FEATURE_DIM

    @staticmethod
    def _normalize_shard_name(shard_name: str | Path) -> str:
        shard_text = str(shard_name).strip()
        if not shard_text:
            raise ValueError("shard_name must not be empty")
        if shard_text.endswith(".safetensors"):
            shard_text = shard_text[: -len(".safetensors")]
        return Path(shard_text).name

    @staticmethod
    def _serialize_metadata(metadata: dict[str, Any] | None) -> str:
        if metadata is None:
            return "{}"
        if not isinstance(metadata, dict):
            raise TypeError("metadata must be a dict with JSON-serializable values")
        return json.dumps(metadata, sort_keys=True)

    @staticmethod
    def _read_metadata(path: Path) -> tuple[dict[str, Any], int | None]:
        with safe_open(str(path), framework="np") as handle:
            metadata = handle.metadata() or {}
        raw_feature_dim = metadata.get(FEATURE_DIM_METADATA_KEY, "")
        feature_dim: int | None = None
        if raw_feature_dim not in (None, ""):
            try:
                feature_dim = SafetensorsFeatureStore._coerce_feature_dim(raw_feature_dim)
            except ValueError as exc:
                raise ValueError(f"{path}: invalid stored feature_dim metadata {raw_feature_dim!r}") from exc
        raw_metadata = metadata.get(METADATA_JSON_KEY, "{}")
        parsed_metadata = json.loads(raw_metadata)
        if not isinstance(parsed_metadata, dict):
            raise ValueError(f"{path}: metadata JSON must decode to an object")
        return parsed_metadata, feature_dim

    @staticmethod
    def _coerce_features_for_write(
        path: Path,
        features: np.ndarray,
        *,
        expected_feature_dim: int,
    ) -> np.ndarray:
        feature_array = np.asarray(features)
        if feature_array.dtype != np.float32:
            raise ValueError(f"{path}: features must have dtype float32, got {feature_array.dtype}")
        if (
            feature_array.ndim != 2
            or feature_array.shape[0] < 1
            or feature_array.shape[1] != expected_feature_dim
        ):
            raise ValueError(
                f"{path}: features must have shape (N, {expected_feature_dim}) with N >= 1, got {feature_array.shape}"
            )
        if not np.isfinite(feature_array).all():
            raise ValueError(f"{path}: features contain NaN/Inf values")
        zero_rows = np.argwhere(np.all(feature_array == 0.0, axis=1))
        if zero_rows.size:
            raise ValueError(f"{path}: all-zero row at index {int(zero_rows[0, 0])}")
        return feature_array

    @staticmethod
    def _coerce_labels_for_write(
        path: Path,
        labels: np.ndarray,
        *,
        expected_rows: int,
    ) -> np.ndarray:
        label_array = np.asarray(labels)
        if label_array.dtype != np.int64:
            raise ValueError(f"{path}: labels must have dtype int64, got {label_array.dtype}")
        if label_array.ndim != 1:
            raise ValueError(f"{path}: labels must have shape (N,), got {label_array.shape}")
        if label_array.shape[0] != expected_rows:
            raise ValueError(
                f"{path}: label length {label_array.shape[0]} does not match feature rows {expected_rows}"
            )
        return label_array

    @staticmethod
    def _validate_loaded_arrays(
        path: Path,
        features: np.ndarray,
        labels: np.ndarray,
        *,
        expected_feature_dim: int,
    ) -> None:
        if features.dtype != np.float32:
            raise ValueError(f"{path}: expected features dtype float32, got {features.dtype}")
        if (
            features.ndim != 2
            or features.shape[0] < 1
            or features.shape[1] != expected_feature_dim
        ):
            raise ValueError(
                f"{path}: expected feature shape (N, {expected_feature_dim}) with N >= 1, got {features.shape}"
            )
        if not np.isfinite(features).all():
            raise ValueError(f"{path}: features contain NaN/Inf values")
        if labels.dtype != np.int64:
            raise ValueError(f"{path}: expected labels dtype int64, got {labels.dtype}")
        if labels.ndim != 1:
            raise ValueError(f"{path}: expected labels shape (N,), got {labels.shape}")
        if labels.shape[0] != features.shape[0]:
            raise ValueError(
                f"{path}: label length {labels.shape[0]} does not match feature rows {features.shape[0]}"
            )
