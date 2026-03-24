"""Tests for verified-only supervised training paths."""

from __future__ import annotations

import inspect
import json
import os
from pathlib import Path

import pytest


def _write_verified_records(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for idx in range(12):
            handle.write(
                json.dumps(
                    {
                        "fingerprint": f"confirmed-{idx:03d}",
                        "category": "SQLI",
                        "severity": "HIGH",
                        "title": f"Confirmed issue {idx}",
                        "description": f"Confirmed evidence {idx}",
                        "url": f"https://example.com/c/{idx}",
                        "verification_status": "CONFIRMED",
                        "actual_positive": True,
                        "validated": True,
                        "validation_source": "proof-verifier",
                        "confidence": 0.97,
                        "evidence": {
                            "payload_tested": True,
                            "response_validated": True,
                        },
                        "created_at": f"2026-03-25T00:00:{idx:02d}+00:00",
                    }
                )
                + "\n"
            )
        for idx in range(12):
            handle.write(
                json.dumps(
                    {
                        "fingerprint": f"rejected-{idx:03d}",
                        "category": "CSRF",
                        "severity": "LOW",
                        "title": f"Rejected issue {idx}",
                        "description": f"Rejected evidence {idx}",
                        "url": f"https://example.com/r/{idx}",
                        "verification_status": "REJECTED_FALSE_POSITIVE",
                        "actual_positive": False,
                        "validated": True,
                        "validation_source": "verification-layer",
                        "confidence": 0.1,
                        "evidence": {
                            "payload_tested": True,
                            "verification_failed": True,
                        },
                        "created_at": f"2026-03-25T00:01:{idx:02d}+00:00",
                    }
                )
                + "\n"
            )


class TestNoSyntheticFallback:
    def test_init_gpu_resources_uses_real_dataset_loader(self):
        from impl_v1.phase49.runtime.auto_trainer import AutoTrainer

        source = inspect.getsource(AutoTrainer._init_gpu_resources)
        assert "real_dataset_loader" in source
        assert "create_training_dataloader" in source
        assert "validate_dataset_integrity" in source

    def test_init_gpu_resources_does_not_import_scaled_generator(self):
        from impl_v1.phase49.runtime.auto_trainer import AutoTrainer

        source = inspect.getsource(AutoTrainer._init_gpu_resources)
        assert "ScaledDatasetGenerator" not in source
        assert "range(512)" not in source
        assert "random.random()" not in source
        assert "random.randint(0, 1)" not in source

    def test_dataset_requires_verified_records(self):
        from impl_v1.training.data.real_dataset_loader import validate_dataset_integrity

        old_value = os.environ.get("YGB_VERIFIED_DATASET_PATHS")
        os.environ["YGB_VERIFIED_DATASET_PATHS"] = ""
        try:
            valid, msg = validate_dataset_integrity()
        finally:
            if old_value is None:
                os.environ.pop("YGB_VERIFIED_DATASET_PATHS", None)
            else:
                os.environ["YGB_VERIFIED_DATASET_PATHS"] = old_value
        assert not valid
        assert "verified" in msg.lower()

    def test_verified_dataset_passes_validation(self, tmp_path: Path):
        from impl_v1.training.data.real_dataset_loader import (
            DatasetConfig,
            validate_dataset_integrity,
        )

        dataset_path = tmp_path / "verified_findings.jsonl"
        _write_verified_records(dataset_path)
        config = DatasetConfig(
            total_samples=24,
            min_verified_samples=10,
            min_class_samples=4,
            dataset_paths=(str(dataset_path),),
        )
        valid, msg = validate_dataset_integrity(config)
        assert valid, msg

    def test_batch_size_still_configured_for_gpu_path(self):
        from impl_v1.phase49.runtime.auto_trainer import AutoTrainer

        source = inspect.getsource(AutoTrainer._init_gpu_resources)
        assert "batch_size=1024" in source


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
