"""Migrate real learned-feature JSON reports into `.safetensors` feature shards."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys
from typing import Any, Sequence

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.training.safetensors_store import SafetensorsFeatureStore


SOURCE_ROOTS = (
    Path("reports/g38_training"),
    Path("training/learned_features"),
)
OUTPUT_ROOT = Path("training/features_safetensors")
FEATURE_DIM = 256


def _read_json_payload(source_path: Path) -> dict[str, Any]:
    raw_text = source_path.read_text(encoding="utf-8").strip()
    try:
        payload = json.loads(raw_text)
    except json.JSONDecodeError:
        redirected_name = raw_text.strip()
        redirected_path = (source_path.parent / redirected_name).resolve()
        if redirected_name.lower().endswith(".json") and redirected_path.exists():
            return _read_json_payload(redirected_path)
        raise ValueError(f"{source_path}: file is not valid JSON and is not a valid JSON redirect") from None
    if not isinstance(payload, dict):
        raise ValueError(f"{source_path}: expected JSON object payload")
    return payload


def _load_float32_matrix(source_path: Path, value: object) -> np.ndarray | None:
    if value is None:
        return None
    array = np.asarray(value, dtype=np.float32)
    if array.ndim != 2 or array.shape[0] < 1 or array.shape[1] != FEATURE_DIM:
        raise ValueError(
            f"{source_path}: feature matrix must have shape (N, {FEATURE_DIM}), got {array.shape}"
        )
    if not np.isfinite(array).all():
        raise ValueError(f"{source_path}: feature matrix contains NaN/Inf values")
    return array


def _load_int64_labels(
    source_path: Path,
    value: object,
    *,
    expected_rows: int,
) -> np.ndarray | None:
    if value is None:
        return None
    array = np.asarray(value, dtype=np.int64)
    if array.ndim != 1 or array.shape[0] != expected_rows:
        raise ValueError(
            f"{source_path}: labels must have shape ({expected_rows},), got {array.shape}"
        )
    return array


def extract_legacy_feature_payload(
    source_path: Path,
    payload: dict[str, Any],
) -> tuple[np.ndarray, np.ndarray] | None:
    feature_value = None
    for key in ("features", "feature_rows", "vectors", "embeddings"):
        if key in payload:
            feature_value = payload[key]
            break

    features = _load_float32_matrix(source_path, feature_value)
    if features is None:
        return None

    labels = None
    for key in ("labels", "label_rows"):
        if key in payload:
            labels = _load_int64_labels(
                source_path,
                payload[key],
                expected_rows=features.shape[0],
            )
            break
    if labels is None:
        return None
    return features, labels


def iter_json_feature_files(source_roots: Sequence[Path] = SOURCE_ROOTS) -> list[Path]:
    candidates: set[Path] = set()
    for source_root in source_roots:
        if not source_root.exists():
            continue
        candidates.update(source_root.glob("learned_features_*.json"))
    return sorted(candidates)


def _canonical_json_bytes(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def shard_name_for_path(source_path: Path) -> str:
    parent_name = source_path.parent.as_posix().replace("/", "__")
    return f"{parent_name}__{source_path.stem}"


def migrate_paths(
    paths: Sequence[Path],
    *,
    output_root: Path = OUTPUT_ROOT,
) -> dict[str, int]:
    store = SafetensorsFeatureStore(output_root)
    migrated = 0
    skipped = 0
    total_samples = 0

    for source_path in paths:
        payload = _read_json_payload(source_path)

        legacy_payload = extract_legacy_feature_payload(source_path, payload)
        if legacy_payload is None:
            skipped += 1
            continue
        feature_matrix, labels = legacy_payload
        metadata = {
            "source_path": source_path.as_posix(),
            "payload_sha256": hashlib.sha256(_canonical_json_bytes(payload)).hexdigest(),
            "session_id": str(payload.get("session_id", source_path.stem)),
            "label": int(labels[0]),
        }
        store.write(
            shard_name_for_path(source_path),
            feature_matrix,
            labels,
            metadata=metadata,
        )
        migrated += 1
        total_samples += int(labels.shape[0])

    return {
        "migrated": migrated,
        "skipped": skipped,
        "total_samples": total_samples,
        "shards": len(store.list_shards()),
    }


def migrate_json_feature_files(
    source_roots: Sequence[Path] = SOURCE_ROOTS,
    *,
    output_root: Path = OUTPUT_ROOT,
) -> dict[str, int]:
    return migrate_paths(iter_json_feature_files(source_roots), output_root=output_root)


def main() -> int:
    result = migrate_json_feature_files()
    print(
        "Migrated",
        result["migrated"],
        "JSON learned-feature file(s) into",
        OUTPUT_ROOT.as_posix(),
        "and skipped",
        result["skipped"],
        "unsupported file(s)",
        "with",
        result["shards"],
        "shard(s) and",
        result["total_samples"],
        "sample(s)",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
