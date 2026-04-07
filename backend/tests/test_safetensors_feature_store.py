from __future__ import annotations

import os
import json
from pathlib import Path

import numpy as np
import pytest

from backend.training.safetensors_store import SafetensorsFeatureStore
from scripts.migrate_json_features_to_safetensors import migrate_paths


def test_safetensors_feature_store_roundtrip_preserves_values_exactly(tmp_path):
    store = SafetensorsFeatureStore(tmp_path / "feature_store")
    features = np.arange(512, dtype=np.float32).reshape(2, 256)
    labels = np.asarray([1, 0], dtype=np.int64)
    metadata = {"source": "roundtrip", "epoch": 7}

    store.write("roundtrip", features, labels, metadata=metadata)
    loaded_features, loaded_labels, loaded_metadata = store.read("roundtrip")

    assert np.array_equal(loaded_features, features)
    assert np.array_equal(loaded_labels, labels)
    assert loaded_metadata == metadata
    assert store.list_shards() == ["roundtrip"]
    assert store.total_samples() == 2


def test_safetensors_feature_store_rejects_nan_on_write(tmp_path):
    store = SafetensorsFeatureStore(tmp_path / "feature_store")
    features = np.ones((1, 256), dtype=np.float32)
    features[0, 8] = np.nan
    labels = np.asarray([1], dtype=np.int64)

    with pytest.raises(ValueError, match="NaN/Inf"):
        store.write("nan_row", features, labels)


def test_safetensors_feature_store_rejects_all_zero_row_on_write(tmp_path):
    store = SafetensorsFeatureStore(tmp_path / "feature_store")
    features = np.ones((2, 256), dtype=np.float32)
    features[1, :] = 0.0
    labels = np.asarray([1, 0], dtype=np.int64)

    with pytest.raises(ValueError, match="all-zero row"):
        store.write("zero_row", features, labels)


def test_safetensors_feature_store_missing_shard_raises_file_not_found(tmp_path):
    store = SafetensorsFeatureStore(tmp_path / "feature_store")

    with pytest.raises(FileNotFoundError):
        store.read("missing")


def test_safetensors_feature_store_atomic_write_uses_tmp_then_rename(tmp_path, monkeypatch):
    store = SafetensorsFeatureStore(tmp_path / "feature_store")
    features = np.ones((1, 256), dtype=np.float32)
    labels = np.asarray([1], dtype=np.int64)
    replace_calls: list[tuple[str, str]] = []
    original_replace = os.replace

    def tracking_replace(src: str, dst: str) -> None:
        replace_calls.append((src, dst))
        original_replace(src, dst)

    monkeypatch.setattr("backend.training.safetensors_store.os.replace", tracking_replace)

    final_path = store.write("atomic", features, labels, metadata={"case": "atomic"})

    assert final_path.exists()
    assert replace_calls == [
        (
            str(final_path.with_name(final_path.name + ".tmp")),
            str(final_path),
        )
    ]


def test_migration_script_runs_against_real_repository_json_files(tmp_path):
    candidate_paths = []
    for source_root in (Path("training/learned_features"), Path("reports/g38_training")):
        candidate_paths.extend(sorted(source_root.glob("learned_features_*.json"))[:1])

    assert candidate_paths, "expected real learned-feature JSON files in the repository"

    result = migrate_paths(candidate_paths, output_root=tmp_path / "features_safetensors")
    store = SafetensorsFeatureStore(tmp_path / "features_safetensors")

    assert result["migrated"] >= 0
    assert result["skipped"] >= 0
    assert result["migrated"] + result["skipped"] == len(candidate_paths)
    assert result["shards"] == result["migrated"]
    assert result["total_samples"] == store.total_samples()


def test_migration_script_migrates_temp_json_feature_payload(tmp_path):
    source_path = tmp_path / "legacy_features.json"
    payload = {
        "session_id": "TEMP-001",
        "features": np.arange(512, dtype=np.float32).reshape(2, 256).tolist(),
        "labels": np.asarray([1, 0], dtype=np.int64).tolist(),
    }
    source_path.write_text(json.dumps(payload), encoding="utf-8")

    result = migrate_paths([source_path], output_root=tmp_path / "features_safetensors")
    store = SafetensorsFeatureStore(tmp_path / "features_safetensors")
    shard_name = f"{source_path.parent.as_posix().replace('/', '__')}__{source_path.stem}"
    features, labels, metadata = store.read(shard_name)

    assert result["migrated"] == 1
    assert result["skipped"] == 0
    assert result["total_samples"] == 2
    assert np.array_equal(features, np.arange(512, dtype=np.float32).reshape(2, 256))
    assert np.array_equal(labels, np.asarray([1, 0], dtype=np.int64))
    assert metadata["session_id"] == "TEMP-001"
