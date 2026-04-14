from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest
from safetensors.numpy import save_file as save_safetensors_file

import backend.training.compression_engine as compression_engine


def _write_checkpoint(path: Path) -> Path:
    save_safetensors_file(
        {
            "dense.weight": np.zeros((1024, 1024), dtype=np.float32),
            "dense.bias": np.full((1024,), 7.0, dtype=np.float32),
        },
        str(path),
        metadata={"epoch": "3", "tag": "phase3"},
    )
    return path


def test_compress_checkpoint_round_trip_preserves_exact_bytes(tmp_path: Path) -> None:
    checkpoint_path = _write_checkpoint(tmp_path / "checkpoint.safetensors")

    result = compression_engine.compress_checkpoint(checkpoint_path)
    restored = compression_engine.decompress_checkpoint(
        result.artifact_path,
        tmp_path / "restored.safetensors",
    )
    metadata = json.loads(result.metadata_path.read_text(encoding="utf-8"))

    assert result.artifact_path.exists()
    assert result.metadata_path.exists()
    assert result.kind == "file"
    assert restored.output_path.read_bytes() == checkpoint_path.read_bytes()
    assert metadata["entries"][0]["relative_path"] == checkpoint_path.name
    assert metadata["compressed_size"] == result.compressed_size
    assert result.compression_ratio > 1.5


def test_compress_directory_round_trip_preserves_files(tmp_path: Path) -> None:
    source_dir = tmp_path / "checkpoint_bundle"
    source_dir.mkdir()
    checkpoint_path = _write_checkpoint(source_dir / "model.safetensors")
    sidecar_path = source_dir / "training_state.json"
    sidecar_path.write_text('{"epoch": 3, "status": "ok"}\n', encoding="utf-8")

    result = compression_engine.compress_directory(source_dir)
    restored_dir = tmp_path / "restored_bundle"
    restored = compression_engine.decompress_checkpoint(result.artifact_path, restored_dir)

    assert result.kind == "directory"
    assert (restored.output_path / checkpoint_path.name).read_bytes() == checkpoint_path.read_bytes()
    assert (restored.output_path / sidecar_path.name).read_text(encoding="utf-8") == sidecar_path.read_text(encoding="utf-8")


def test_compress_checkpoint_falls_back_to_gzip_when_zstd_missing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    checkpoint_path = _write_checkpoint(tmp_path / "fallback_checkpoint.safetensors")
    monkeypatch.setattr(compression_engine, "_get_zstd_module", lambda: None)

    result = compression_engine.compress_checkpoint(checkpoint_path, algorithm="zstd")

    assert result.algorithm == "gzip"
    assert result.fallback_reason is not None
    assert "zstandard" in result.fallback_reason
