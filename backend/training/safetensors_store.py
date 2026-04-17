"""SafeTensors-backed feature shard store for real training artifacts."""

from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone
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
CHECKPOINT_METADATA_JSON_KEY = "ygb_checkpoint_metadata"
LEGACY_CHECKPOINT_METADATA_JSON_KEY = "checkpoint_metadata_json"
CHECKPOINT_SCHEMA_VERSION = 1
DEFAULT_TOP_K_CHECKPOINTS = 3


logger = logging.getLogger(__name__)
DESCRIPTION_SIDECAR_SUFFIX = ".descriptions.jsonl"


def _atomic_write_json_file(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = Path(f"{path}.tmp")
    with open(temp_path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(str(temp_path), str(path))


def _atomic_write_text_file(path: Path, payload: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = Path(f"{path}.tmp")
    with open(temp_path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(str(temp_path), str(path))


def _write_sha256_sidecar(path: Path, sha256: str) -> Path:
    checksum = str(sha256 or "").strip().lower()
    if len(checksum) != 64 or any(ch not in "0123456789abcdef" for ch in checksum):
        raise ValueError(f"invalid SHA-256 checksum for {path}: {sha256!r}")
    sidecar_path = Path(f"{path}.sha256")
    _atomic_write_text_file(sidecar_path, f"{checksum}\n")
    return sidecar_path


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
        self._total_samples_cache: int | None = None

    def _invalidate_total_samples_cache(self) -> None:
        self._total_samples_cache = None

    def shard_path(self, shard_name: str | Path) -> Path:
        normalized_name = self._normalize_shard_name(shard_name)
        return self.root / f"{normalized_name}.safetensors"

    def description_path(self, shard_name: str | Path) -> Path:
        normalized_name = self._normalize_shard_name(shard_name)
        return self.root / f"{normalized_name}{DESCRIPTION_SIDECAR_SUFFIX}"

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

        self._invalidate_total_samples_cache()

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

    def write_descriptions(
        self,
        shard_name: str | Path,
        descriptions: list[dict[str, Any]],
    ) -> Path:
        if not isinstance(descriptions, list):
            raise TypeError("descriptions must be a list of JSON-serializable dict records")
        serialized_lines: list[str] = []
        for index, record in enumerate(descriptions):
            if not isinstance(record, dict):
                raise TypeError(
                    f"description record at index {index} must be a dict, got {type(record).__name__}"
                )
            normalized_record = {str(key): value for key, value in record.items()}
            try:
                serialized_lines.append(
                    json.dumps(normalized_record, ensure_ascii=False, sort_keys=True)
                )
            except TypeError as exc:
                raise TypeError(
                    f"description record at index {index} is not JSON-serializable"
                ) from exc
        payload = "\n".join(serialized_lines)
        if serialized_lines:
            payload += "\n"
        target_path = self.description_path(shard_name)
        _atomic_write_text_file(target_path, payload)
        return target_path

    def read_descriptions(self, shard_name: str | Path) -> list[dict[str, Any]]:
        target_path = self.description_path(shard_name)
        if not target_path.exists():
            return []
        descriptions: list[dict[str, Any]] = []
        with open(target_path, "r", encoding="utf-8") as handle:
            for line_number, raw_line in enumerate(handle, start=1):
                line = raw_line.strip()
                if not line:
                    continue
                try:
                    parsed = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise ValueError(
                        f"{target_path}: invalid JSON on line {line_number}"
                    ) from exc
                if not isinstance(parsed, dict):
                    raise ValueError(
                        f"{target_path}: description line {line_number} must decode to an object"
                    )
                descriptions.append(parsed)
        return descriptions

    def shard_exists(self, shard_name: str | Path) -> bool:
        return self.shard_path(shard_name).exists()

    def delete_shard(self, shard_name: str | Path) -> bool:
        target_path = self.shard_path(shard_name)
        description_path = self.description_path(shard_name)
        deleted = False
        if target_path.exists():
            target_path.unlink()
            deleted = True
        if description_path.exists():
            description_path.unlink()
        if deleted:
            self._invalidate_total_samples_cache()
        return deleted

    def total_samples(self) -> int:
        if self._total_samples_cache is not None:
            return int(self._total_samples_cache)
        total = 0
        for shard_name in self.list_shards():
            total += int(self.read(shard_name).labels.shape[0])
        self._total_samples_cache = int(total)
        return int(total)

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


class CheckpointManager:
    """Safetensors-backed expert checkpoint manager with top-k retention."""

    def __init__(
        self,
        root: Path | str = "checkpoints",
        *,
        keep_top_k: int = DEFAULT_TOP_K_CHECKPOINTS,
        expert_fields: Iterable[str] | None = None,
    ) -> None:
        self.root = Path(root)
        self.experts_root = self.root / "experts"
        self.registry_path = self.root / "expert_checkpoint_registry.json"
        self.keep_top_k = self._coerce_keep_top_k(keep_top_k)
        if expert_fields is None:
            from impl_v1.phase49.moe import EXPERT_FIELDS

            expert_fields = EXPERT_FIELDS
        self.expert_fields = tuple(str(field_name) for field_name in expert_fields)

    def save_expert_checkpoint(
        self,
        *,
        expert_id: int,
        field_name: str,
        state_dict: dict[str, Any],
        val_f1: float,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return self.save(
            expert_id=expert_id,
            field_name=field_name,
            state_dict=state_dict,
            val_f1=val_f1,
            metadata=metadata,
        )

    def load_best_checkpoint(
        self,
        *,
        expert_id: int,
        field_name: str,
        device: str = "cpu",
    ) -> dict[str, Any]:
        return self.load(
            expert_id=expert_id,
            field_name=field_name,
            device=device,
        )

    def save(
        self,
        *,
        expert_id: int,
        field_name: str,
        state_dict: dict[str, Any],
        val_f1: float,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        expert_id_value, field_name_value = self._validate_expert_identity(
            expert_id,
            field_name,
        )
        val_f1_value = self._coerce_float(val_f1, field_name="val_f1")
        metadata_payload = metadata or {}
        if not isinstance(metadata_payload, dict):
            raise TypeError("metadata must be a dict with JSON-serializable values")
        epoch_value = self._coerce_epoch(metadata_payload.get("epoch", 0))
        normalized_state_dict = self._normalize_checkpoint_state_dict(state_dict)
        inferred_metadata = self._infer_moe_classifier_metadata(normalized_state_dict)

        registry = self._load_registry()
        registry_key = self._registry_key(expert_id_value, field_name_value)
        existing_entry = registry["experts"].get(registry_key)
        existing_records = self._collect_checkpoint_records(
            expert_id_value,
            field_name_value,
            existing_entry,
        )
        retained_existing_records, stale_records = self._prune_records(existing_records)
        self._delete_removed_records(stale_records)

        if len(retained_existing_records) >= self.keep_top_k:
            worst_retained = retained_existing_records[-1]
            if val_f1_value <= float(worst_retained["val_f1"]):
                normalized_entry = self._entry_from_records(
                    expert_id_value,
                    field_name_value,
                    retained_existing_records,
                )
                if existing_entry != normalized_entry:
                    registry["experts"][registry_key] = normalized_entry
                    self._save_registry(registry)
                status = self._status_from_records(
                    expert_id_value,
                    field_name_value,
                    retained_existing_records,
                )
                logger.info(
                    "Skipped worse expert checkpoint expert_id=%s field_name=%s val_f1=%.6f retained_best=%.6f",
                    expert_id_value,
                    field_name_value,
                    val_f1_value,
                    float(status.get("best_val_f1") or 0.0),
                )
                return {
                    "saved": False,
                    "retained": False,
                    "checkpoint_path": "",
                    "is_best": False,
                    **status,
                }

        checkpoint_path = self._next_checkpoint_path(
            expert_id_value,
            field_name_value,
            epoch_value,
            val_f1_value,
        )
        checkpoint_metadata = {
            **inferred_metadata,
            "expert_id": expert_id_value,
            "field_name": field_name_value,
            "epoch": epoch_value,
            "val_f1": val_f1_value,
            "created_at": self._timestamp_now(),
            **metadata_payload,
        }
        checkpoint_file_hash, tensor_hash = self._write_checkpoint(
            checkpoint_path,
            normalized_state_dict,
            metadata=checkpoint_metadata,
        )
        checkpoint_metadata = {
            **checkpoint_metadata,
            "checkpoint_sha256": checkpoint_file_hash,
            "tensor_hash": tensor_hash,
            "sha256_sidecar_path": self._serialize_path(Path(f"{checkpoint_path}.sha256")),
        }

        new_record = {
            "checkpoint_path": self._serialize_path(checkpoint_path),
            "val_f1": val_f1_value,
            "created_at": str(checkpoint_metadata["created_at"]),
            "metadata": checkpoint_metadata,
        }
        retained_records, removed_records = self._prune_records(
            retained_existing_records + [new_record]
        )
        self._delete_removed_records(removed_records)

        normalized_entry = self._entry_from_records(
            expert_id_value,
            field_name_value,
            retained_records,
        )
        registry["experts"][registry_key] = normalized_entry
        self._save_registry(registry)

        status = self._status_from_records(
            expert_id_value,
            field_name_value,
            retained_records,
        )
        retained_path = self._serialize_path(checkpoint_path)
        logger.info(
            "Saved expert checkpoint expert_id=%s field_name=%s val_f1=%.6f path=%s best=%s",
            expert_id_value,
            field_name_value,
            val_f1_value,
            retained_path,
            normalized_entry["best_checkpoint_path"] == retained_path,
        )
        return {
            "saved": True,
            "retained": any(
                item["checkpoint_path"] == retained_path for item in retained_records
            ),
            "checkpoint_path": retained_path,
            "checkpoint_sha256": checkpoint_file_hash,
            "tensor_hash": tensor_hash,
            "is_best": normalized_entry["best_checkpoint_path"] == retained_path,
            **status,
        }

    @staticmethod
    def _normalize_checkpoint_state_dict(state_dict: dict[str, Any]) -> dict[str, Any]:
        normalized: dict[str, Any] = {}
        for key, value in dict(state_dict).items():
            if hasattr(value, "detach") and hasattr(value, "cpu"):
                normalized[key] = value.detach().cpu()
            else:
                normalized[key] = value
        return normalized

    def load(
        self,
        *,
        expert_id: int,
        field_name: str,
        checkpoint_path: str | Path | None = None,
        device: str = "cpu",
    ) -> dict[str, Any]:
        expert_id_value, field_name_value = self._validate_expert_identity(
            expert_id,
            field_name,
        )
        if checkpoint_path is None:
            status = self.status(expert_id_value, field_name_value)
            resolved_path_text = str(status.get("best_checkpoint_path", "") or "")
            if not resolved_path_text:
                raise FileNotFoundError(
                    f"No retained checkpoint for expert_id={expert_id_value} field_name={field_name_value}"
                )
            resolved_path = Path(resolved_path_text)
        else:
            resolved_path = Path(checkpoint_path)

        if not resolved_path.exists():
            raise FileNotFoundError(f"Checkpoint not found: {resolved_path}")

        from impl_v1.training.checkpoints.checkpoint_hardening import (
            HardenedCheckpointManager,
        )
        from training.safetensors_io import load_safetensors

        HardenedCheckpointManager._require_verified_file_hash(resolved_path)
        return load_safetensors(str(resolved_path), device=device)

    def status(self, expert_id: int, field_name: str) -> dict[str, Any]:
        expert_id_value, field_name_value = self._validate_expert_identity(
            expert_id,
            field_name,
        )
        registry = self._load_registry()
        registry_key = self._registry_key(expert_id_value, field_name_value)
        existing_entry = registry["experts"].get(registry_key)
        existing_records = self._collect_checkpoint_records(
            expert_id_value,
            field_name_value,
            existing_entry,
        )
        retained_records, removed_records = self._prune_records(existing_records)
        self._delete_removed_records(removed_records)
        normalized_entry = self._entry_from_records(
            expert_id_value,
            field_name_value,
            retained_records,
        )
        if existing_entry != normalized_entry:
            if normalized_entry["checkpoints"]:
                registry["experts"][registry_key] = normalized_entry
            else:
                registry["experts"].pop(registry_key, None)
            self._save_registry(registry)
        return self._status_from_records(
            expert_id_value,
            field_name_value,
            retained_records,
        )

    def get_all_expert_status(self) -> list[dict[str, Any]]:
        registry = self._load_registry()
        statuses: list[dict[str, Any]] = []
        changed = False
        for expert_id, field_name in enumerate(self.expert_fields):
            registry_key = self._registry_key(expert_id, field_name)
            existing_entry = registry["experts"].get(registry_key)
            existing_records = self._collect_checkpoint_records(
                expert_id,
                field_name,
                existing_entry,
            )
            retained_records, removed_records = self._prune_records(existing_records)
            self._delete_removed_records(removed_records)
            normalized_entry = self._entry_from_records(
                expert_id,
                field_name,
                retained_records,
            )
            if existing_entry != normalized_entry:
                if normalized_entry["checkpoints"]:
                    registry["experts"][registry_key] = normalized_entry
                else:
                    registry["experts"].pop(registry_key, None)
                changed = True
            statuses.append(
                self._status_from_records(
                    expert_id,
                    field_name,
                    retained_records,
                )
            )
        if changed:
            self._save_registry(registry)
        return statuses

    @staticmethod
    def _coerce_keep_top_k(keep_top_k: int) -> int:
        parsed = int(keep_top_k)
        if parsed <= 0:
            raise ValueError(f"keep_top_k must be >= 1, got {parsed}")
        return parsed

    @staticmethod
    def _registry_key(expert_id: int, field_name: str) -> str:
        return f"{int(expert_id)}:{str(field_name)}"

    @staticmethod
    def _serialize_path(path: Path) -> str:
        return path.as_posix()

    @staticmethod
    def _timestamp_now() -> str:
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _coerce_float(value: Any, *, field_name: str) -> float:
        try:
            parsed = float(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{field_name} must be a finite float, got {value!r}") from exc
        if not np.isfinite(parsed):
            raise ValueError(f"{field_name} must be a finite float, got {parsed!r}")
        return parsed

    @staticmethod
    def _coerce_epoch(value: Any) -> int:
        try:
            epoch_value = int(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"epoch must be an integer, got {value!r}") from exc
        if epoch_value < 0:
            raise ValueError(f"epoch must be >= 0, got {epoch_value}")
        return epoch_value

    def _validate_expert_identity(
        self,
        expert_id: int,
        field_name: str,
    ) -> tuple[int, str]:
        expert_id_value = int(expert_id)
        field_name_value = str(field_name or "").strip()
        if not field_name_value:
            raise ValueError("field_name is required")
        if not 0 <= expert_id_value < len(self.expert_fields):
            raise ValueError(f"Invalid expert_id={expert_id_value}")
        expected_field_name = self.expert_fields[expert_id_value]
        if field_name_value != expected_field_name:
            raise ValueError(
                f"Expert-field mismatch: expert_id={expert_id_value} expects {expected_field_name}, got {field_name_value}"
            )
        return expert_id_value, field_name_value

    def _load_registry(self) -> dict[str, Any]:
        if not self.registry_path.exists():
            return {
                "schema_version": CHECKPOINT_SCHEMA_VERSION,
                "experts": {},
            }

        with open(self.registry_path, "r", encoding="utf-8") as handle:
            raw_registry = json.load(handle)
        if not isinstance(raw_registry, dict):
            raise ValueError(
                f"Checkpoint registry must be a JSON object, got {type(raw_registry).__name__}"
            )

        raw_entries = raw_registry.get("experts")
        if not isinstance(raw_entries, dict):
            raw_entries = {
                key: value
                for key, value in raw_registry.items()
                if key != "schema_version"
            }

        normalized_entries: dict[str, Any] = {}
        for key, value in raw_entries.items():
            normalized = self._normalize_registry_entry(str(key), value)
            normalized_entries[self._registry_key(normalized["expert_id"], normalized["field_name"])] = normalized
        return {
            "schema_version": CHECKPOINT_SCHEMA_VERSION,
            "experts": normalized_entries,
        }

    def _save_registry(self, registry: dict[str, Any]) -> None:
        normalized_payload = {
            "schema_version": CHECKPOINT_SCHEMA_VERSION,
            "experts": dict(sorted(registry.get("experts", {}).items())),
        }
        _atomic_write_json_file(self.registry_path, normalized_payload)

    def _normalize_registry_entry(self, registry_key: str, value: Any) -> dict[str, Any]:
        raw_value = value if isinstance(value, dict) else {}
        parsed_expert_id, parsed_field_name = self._parse_registry_key(registry_key)
        expert_id_value = int(raw_value.get("expert_id", parsed_expert_id))
        field_name_value = str(raw_value.get("field_name", parsed_field_name) or "").strip()
        if not field_name_value and 0 <= expert_id_value < len(self.expert_fields):
            field_name_value = self.expert_fields[expert_id_value]
        expert_id_value, field_name_value = self._validate_expert_identity(
            expert_id_value,
            field_name_value,
        )

        raw_records = raw_value.get("checkpoints")
        if not isinstance(raw_records, list):
            raw_records = []
            legacy_path = str(
                raw_value.get("best_checkpoint_path")
                or raw_value.get("checkpoint_path")
                or ""
            ).strip()
            legacy_f1 = raw_value.get("best_val_f1")
            if legacy_f1 is None:
                legacy_f1 = raw_value.get("val_f1")
            if legacy_path:
                raw_records.append(
                    {
                        "checkpoint_path": legacy_path,
                        "val_f1": legacy_f1,
                        "created_at": str(raw_value.get("updated_at", "") or ""),
                        "metadata": {
                            "expert_id": expert_id_value,
                            "field_name": field_name_value,
                        },
                    }
                )

        normalized_records = [
            normalized
            for normalized in (
                self._normalize_checkpoint_record(record) for record in raw_records
            )
            if normalized is not None
        ]
        retained_records = self._sort_checkpoint_records(normalized_records)[: self.keep_top_k]
        return self._entry_from_records(
            expert_id_value,
            field_name_value,
            retained_records,
        )

    @staticmethod
    def _parse_registry_key(registry_key: str) -> tuple[int, str]:
        raw_expert_id, _, raw_field_name = str(registry_key).partition(":")
        if not raw_expert_id or not raw_field_name:
            raise ValueError(f"Invalid checkpoint registry key: {registry_key!r}")
        return int(raw_expert_id), raw_field_name

    def _normalize_checkpoint_record(
        self,
        record: dict[str, Any],
    ) -> dict[str, Any] | None:
        checkpoint_path_text = str(record.get("checkpoint_path", "") or "").strip()
        if not checkpoint_path_text:
            return None
        checkpoint_path = Path(checkpoint_path_text)
        if not checkpoint_path.exists():
            return None

        raw_val_f1 = record.get("val_f1")
        if raw_val_f1 in (None, ""):
            raw_val_f1 = self._extract_f1(checkpoint_path.name)
        if raw_val_f1 in (None, ""):
            return None
        val_f1_value = self._coerce_float(raw_val_f1, field_name="val_f1")

        metadata = record.get("metadata")
        if not isinstance(metadata, dict):
            metadata = self._read_checkpoint_metadata(checkpoint_path)

        created_at = str(record.get("created_at", "") or "").strip()
        if not created_at:
            created_at = str(metadata.get("created_at", "") or "").strip()
        if not created_at:
            created_at = datetime.fromtimestamp(
                checkpoint_path.stat().st_mtime,
                tz=timezone.utc,
            ).isoformat()

        return {
            "checkpoint_path": self._serialize_path(checkpoint_path),
            "val_f1": val_f1_value,
            "created_at": created_at,
            "metadata": metadata,
        }

    def _read_checkpoint_metadata(self, checkpoint_path: Path) -> dict[str, Any]:
        with safe_open(str(checkpoint_path), framework="np") as handle:
            metadata = handle.metadata() or {}
        raw_metadata = metadata.get(CHECKPOINT_METADATA_JSON_KEY)
        if raw_metadata in (None, ""):
            raw_metadata = metadata.get(LEGACY_CHECKPOINT_METADATA_JSON_KEY, "{}")
        parsed_metadata = json.loads(raw_metadata)
        if not isinstance(parsed_metadata, dict):
            raise ValueError(
                f"{checkpoint_path}: checkpoint metadata must decode to an object"
            )
        return parsed_metadata

    def _collect_checkpoint_records(
        self,
        expert_id: int,
        field_name: str,
        existing_entry: dict[str, Any] | None,
    ) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []
        if isinstance(existing_entry, dict):
            for record in existing_entry.get("checkpoints", []):
                normalized = self._normalize_checkpoint_record(record)
                if normalized is not None:
                    records.append(normalized)

        for checkpoint_path in self._discover_checkpoint_paths(expert_id, field_name):
            normalized = self._normalize_checkpoint_record(
                {
                    "checkpoint_path": self._serialize_path(checkpoint_path),
                }
            )
            if normalized is not None:
                records.append(normalized)

        return self._sort_checkpoint_records(records)

    def _discover_checkpoint_paths(
        self,
        expert_id: int,
        field_name: str,
    ) -> list[Path]:
        discovered: list[Path] = []
        for pattern in (
            f"expert_{expert_id:02d}_{field_name}_e*_f1*.safetensors",
            f"expert_{expert_id}_{field_name}_*.safetensors",
        ):
            discovered.extend(list(self.root.glob(pattern)))
        expert_dir = self.experts_root / f"{expert_id:02d}_{field_name}"
        if expert_dir.exists():
            discovered.extend(sorted(expert_dir.glob("*.safetensors")))
        unique_paths: list[Path] = []
        seen: set[str] = set()
        for checkpoint_path in discovered:
            serialized_path = self._serialize_path(checkpoint_path)
            if serialized_path in seen:
                continue
            seen.add(serialized_path)
            unique_paths.append(checkpoint_path)
        return unique_paths

    def _sort_checkpoint_records(
        self,
        records: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        deduplicated: dict[str, dict[str, Any]] = {}
        for record in records:
            checkpoint_path = str(record["checkpoint_path"])
            previous = deduplicated.get(checkpoint_path)
            if previous is None:
                deduplicated[checkpoint_path] = dict(record)
                continue
            candidate = [previous, dict(record)]
            candidate.sort(
                key=lambda item: (
                    float(item["val_f1"]),
                    str(item["created_at"]),
                    str(item["checkpoint_path"]),
                ),
                reverse=True,
            )
            deduplicated[checkpoint_path] = candidate[0]
        return sorted(
            deduplicated.values(),
            key=lambda item: (
                float(item["val_f1"]),
                str(item["created_at"]),
                str(item["checkpoint_path"]),
            ),
            reverse=True,
        )

    def _entry_from_records(
        self,
        expert_id: int,
        field_name: str,
        records: list[dict[str, Any]],
    ) -> dict[str, Any]:
        retained_records = self._sort_checkpoint_records(list(records))[: self.keep_top_k]
        best_record = retained_records[0] if retained_records else None
        updated_at = (
            max(str(record.get("created_at", "") or "") for record in retained_records)
            if retained_records
            else ""
        )
        return {
            "expert_id": int(expert_id),
            "field_name": str(field_name),
            "best_val_f1": (
                float(best_record["val_f1"]) if best_record is not None else None
            ),
            "best_checkpoint_path": (
                str(best_record["checkpoint_path"]) if best_record is not None else ""
            ),
            "checkpoints": retained_records,
            "updated_at": updated_at,
        }

    def _status_from_records(
        self,
        expert_id: int,
        field_name: str,
        records: list[dict[str, Any]],
    ) -> dict[str, Any]:
        retained_records = self._sort_checkpoint_records(list(records))[: self.keep_top_k]
        best_record = retained_records[0] if retained_records else None
        return {
            "expert_id": int(expert_id),
            "field_name": str(field_name),
            "has_checkpoint": best_record is not None,
            "best_val_f1": (
                float(best_record["val_f1"]) if best_record is not None else None
            ),
            "best_checkpoint_path": (
                str(best_record["checkpoint_path"]) if best_record is not None else ""
            ),
            "checkpoints": retained_records,
        }

    def _next_checkpoint_path(
        self,
        expert_id: int,
        field_name: str,
        epoch: int,
        val_f1: float,
    ) -> Path:
        self.root.mkdir(parents=True, exist_ok=True)
        return self.root / (
            f"expert_{expert_id:02d}_{field_name}_e{int(epoch)}_f1{val_f1:.4f}.safetensors"
        )

    def _write_checkpoint(
        self,
        checkpoint_path: Path,
        state_dict: dict[str, Any],
        *,
        metadata: dict[str, Any],
    ) -> tuple[str, str]:
        from training.safetensors_io import save_safetensors

        metadata_json = json.dumps(metadata, sort_keys=True)
        metadata_payload = {
            CHECKPOINT_METADATA_JSON_KEY: metadata_json,
            LEGACY_CHECKPOINT_METADATA_JSON_KEY: metadata_json,
        }
        checkpoint_file_hash, tensor_hash = save_safetensors(
            state_dict,
            str(checkpoint_path),
            metadata=metadata_payload,
        )
        _write_sha256_sidecar(checkpoint_path, checkpoint_file_hash)
        return checkpoint_file_hash, tensor_hash

    def _prune_records(
        self,
        records: list[dict[str, Any]],
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        sorted_records = self._sort_checkpoint_records(records)
        retained_records = sorted_records[: self.keep_top_k]
        removed_records = sorted_records[self.keep_top_k :]
        return retained_records, removed_records

    @staticmethod
    def _delete_removed_records(records: list[dict[str, Any]]) -> None:
        for record in records:
            checkpoint_path = Path(str(record["checkpoint_path"]))
            if checkpoint_path.exists():
                checkpoint_path.unlink()
                logger.info("Deleted pruned expert checkpoint: %s", checkpoint_path.as_posix())
            sidecar_path = Path(f"{checkpoint_path}.sha256")
            if sidecar_path.exists():
                sidecar_path.unlink()

    @staticmethod
    def _infer_moe_classifier_metadata(state_dict: dict[str, Any]) -> dict[str, Any]:
        input_proj = state_dict.get("input_proj.weight")
        classifier_weight = state_dict.get("classifier.weight")
        router_weight = state_dict.get("moe.router.w_gate.weight")
        expert_fc1_weight = state_dict.get("moe.experts.0.fc1.weight")
        required_tensors = (
            input_proj,
            classifier_weight,
            router_weight,
            expert_fc1_weight,
        )
        if not all(hasattr(tensor, "shape") for tensor in required_tensors):
            return {}

        depth_indices: list[int] = []
        depth_prefix = "moe.experts.0.depth_layers."
        depth_suffix = ".fc1.weight"
        for key in state_dict:
            if not key.startswith(depth_prefix) or not key.endswith(depth_suffix):
                continue
            index_text = key[len(depth_prefix) : -len(depth_suffix)]
            if index_text.isdigit():
                depth_indices.append(int(index_text))

        expert_depth = 1 + (max(depth_indices) + 1 if depth_indices else 0)
        return {
            "architecture": "MoEClassifier",
            "architecture_format": "moe_classifier_expert_v2",
            "input_dim": int(input_proj.shape[1]),
            "output_dim": int(classifier_weight.shape[0]),
            "d_model": int(input_proj.shape[0]),
            "n_experts": int(router_weight.shape[0]),
            "expert_hidden_dim": int(expert_fc1_weight.shape[0]),
            "expert_depth": int(expert_depth),
        }

    @staticmethod
    def _extract_f1(path_or_name: str | Path) -> float | None:
        filename = Path(path_or_name).name
        legacy_match = re.search(
            r"_(?P<f1>\d+(?:\.\d+)?)(?=\.safetensors$)",
            filename,
        )
        if legacy_match is not None:
            return float(legacy_match.group("f1"))
        named_match = re.search(
            r"(?:^|_)f1_?(?P<f1>\d+(?:\.\d+)?)(?=(_|\.safetensors$))",
            filename,
        )
        if named_match is not None:
            return float(named_match.group("f1"))
        return None
