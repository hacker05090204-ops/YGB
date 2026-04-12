from __future__ import annotations

import os
import json
from pathlib import Path

import numpy as np
import pytest

from backend.training.safetensors_store import CheckpointManager, SafetensorsFeatureStore
from scripts.migrate_json_features_to_safetensors import migrate_paths

torch = pytest.importorskip("torch")


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


def test_safetensors_feature_store_description_sidecar_roundtrip(tmp_path):
    store = SafetensorsFeatureStore(tmp_path / "feature_store")
    store.write(
        "with_descriptions",
        np.linspace(0.1, 1.1, 256, dtype=np.float32).reshape(1, 256),
        np.asarray([1], dtype=np.int64),
        metadata={"sample_cve_id": "CVE-2026-8001", "sample_severity": "HIGH"},
    )
    descriptions = [
        {
            "row_id": "row-1",
            "sample_sha256": "row-1",
            "cve_id": "CVE-2026-8001",
            "severity": "HIGH",
            "raw_text": "A real CVE description recorded beside the shard.",
        }
    ]

    store.write_descriptions("with_descriptions", descriptions)

    assert store.read_descriptions("with_descriptions") == descriptions


def test_delete_shard_removes_description_sidecar(tmp_path):
    store = SafetensorsFeatureStore(tmp_path / "feature_store")
    store.write(
        "deletable",
        np.linspace(0.2, 1.2, 256, dtype=np.float32).reshape(1, 256),
        np.asarray([0], dtype=np.int64),
    )
    store.write_descriptions(
        "deletable",
        [{"row_id": "delete-row", "raw_text": "Delete me truthfully."}],
    )

    deleted = store.delete_shard("deletable")

    assert deleted is True
    assert store.shard_exists("deletable") is False
    assert store.read_descriptions("deletable") == []


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


def test_checkpoint_manager_save_load_roundtrip_preserves_state_dict(tmp_path):
    manager = CheckpointManager(tmp_path / "checkpoints")
    state_dict = {
        "layer.weight": torch.arange(6, dtype=torch.float32).reshape(2, 3),
        "layer.bias": torch.tensor([0.5, -0.5], dtype=torch.float32),
    }

    result = manager.save(
        expert_id=0,
        field_name="web_vulns",
        state_dict=state_dict,
        val_f1=0.8125,
        metadata={"epoch": 3},
    )
    loaded = manager.load(
        expert_id=0,
        field_name="web_vulns",
        checkpoint_path=result["checkpoint_path"],
    )

    assert result["saved"] is True
    assert result["retained"] is True
    assert set(loaded.keys()) == set(state_dict.keys())
    for key, tensor in state_dict.items():
        assert torch.equal(loaded[key], tensor)


def test_checkpoint_manager_worse_checkpoint_does_not_replace_better(tmp_path):
    manager = CheckpointManager(tmp_path / "checkpoints")
    better = manager.save(
        expert_id=0,
        field_name="web_vulns",
        state_dict={"weight": torch.ones(2, 2, dtype=torch.float32)},
        val_f1=0.900,
    )
    worse = manager.save(
        expert_id=0,
        field_name="web_vulns",
        state_dict={"weight": torch.zeros(2, 2, dtype=torch.float32)},
        val_f1=0.400,
    )
    status = manager.status(0, "web_vulns")

    assert better["is_best"] is True
    assert worse["checkpoint_path"]
    assert status["has_checkpoint"] is True
    assert status["best_val_f1"] == pytest.approx(0.900)
    assert status["best_checkpoint_path"] == better["checkpoint_path"]
    assert len(status["checkpoints"]) == 2


def test_checkpoint_manager_cleanup_keeps_exactly_top_three(tmp_path):
    manager = CheckpointManager(tmp_path / "checkpoints")
    saved_results = []
    for val_f1 in (0.100, 0.200, 0.300, 0.400):
        saved_results.append(
            manager.save(
                expert_id=0,
                field_name="web_vulns",
                state_dict={"weight": torch.full((2, 2), val_f1, dtype=torch.float32)},
                val_f1=val_f1,
            )
        )

    status = manager.status(0, "web_vulns")
    retained_scores = [item["val_f1"] for item in status["checkpoints"]]

    assert len(status["checkpoints"]) == 3
    assert retained_scores == pytest.approx([0.400, 0.300, 0.200])
    assert Path(saved_results[0]["checkpoint_path"]).exists() is False


def test_checkpoint_manager_get_all_expert_status_returns_23_entries(tmp_path):
    manager = CheckpointManager(tmp_path / "checkpoints")
    all_status = manager.get_all_expert_status()

    assert len(all_status) == 23
    assert [item["expert_id"] for item in all_status] == list(range(23))


def test_checkpoint_manager_extract_f1_parses_filename_correctly():
    assert CheckpointManager._extract_f1("expert_0_web_vulns_0.750.safetensors") == pytest.approx(0.750)
    assert CheckpointManager._extract_f1(
        "expert_0_web_vulns_f1_0.875000_20260409T155000000000Z.safetensors"
    ) == pytest.approx(0.875)
