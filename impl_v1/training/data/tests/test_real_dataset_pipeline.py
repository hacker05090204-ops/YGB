"""Tests for verified dataset loading."""

from __future__ import annotations

import json
from pathlib import Path

import pytest


def _write_verified_records(path: Path, total: int = 80) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    records = []
    for idx in range(total // 2):
        records.append(
            {
                "fingerprint": f"confirmed-{idx:03d}",
                "category": "SQLI" if idx % 2 == 0 else "XSS",
                "severity": "HIGH",
                "title": f"Confirmed issue {idx}",
                "description": f"Confirmed vulnerability evidence {idx}",
                "url": f"https://example.com/item/{idx}",
                "verification_status": "CONFIRMED",
                "actual_positive": True,
                "validated": True,
                "validation_source": "proof-verifier",
                "confidence": 0.98,
                "evidence": {
                    "payload_tested": True,
                    "response_validated": True,
                    "sql_errors": ["sql syntax"],
                },
                "created_at": f"2026-03-25T00:00:{idx:02d}+00:00",
            }
        )
    for idx in range(total // 2):
        records.append(
            {
                "fingerprint": f"rejected-{idx:03d}",
                "category": "IDOR" if idx % 2 == 0 else "CSRF",
                "severity": "LOW",
                "title": f"Rejected issue {idx}",
                "description": f"Rejected vulnerability candidate {idx}",
                "url": f"https://example.com/view/{idx}",
                "verification_status": "REJECTED_FALSE_POSITIVE",
                "actual_positive": False,
                "validated": True,
                "validation_source": "verification-layer",
                "confidence": 0.2,
                "evidence": {
                    "payload_tested": True,
                    "verification_failed": True,
                    "needs_manual_review": False,
                },
                "created_at": f"2026-03-25T00:01:{idx:02d}+00:00",
            }
        )
    with path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record) + "\n")


class TestRealDatasetPipeline:
    def test_dataset_uses_verified_samples(self, tmp_path: Path):
        from impl_v1.training.data.real_dataset_loader import (
            DatasetConfig,
            RealTrainingDataset,
            validate_dataset_integrity,
        )

        dataset_path = tmp_path / "verified_findings.jsonl"
        _write_verified_records(dataset_path)
        config = DatasetConfig(
            total_samples=80,
            min_verified_samples=20,
            min_class_samples=10,
            dataset_paths=(str(dataset_path),),
        )

        valid, msg = validate_dataset_integrity(config)
        assert valid, msg

        dataset = RealTrainingDataset(config=config, is_holdout=False)
        stats = dataset.get_statistics()
        assert stats["total"] >= 20
        assert stats["positive"] >= 10
        assert stats["negative"] >= 10
        assert set(stats["sources"]) == {"proof-verifier", "verification-layer"}

    def test_no_forbidden_fields(self, tmp_path: Path):
        from impl_v1.training.data.real_dataset_loader import (
            DatasetConfig,
            RealTrainingDataset,
            validate_no_forbidden_fields,
        )

        dataset_path = tmp_path / "verified_findings.jsonl"
        _write_verified_records(dataset_path, total=20)
        dataset = RealTrainingDataset(
            config=DatasetConfig(
                total_samples=20,
                min_verified_samples=5,
                min_class_samples=2,
                dataset_paths=(str(dataset_path),),
            )
        )
        for sample in dataset.samples:
            assert validate_no_forbidden_fields(sample.features)
            assert "severity" not in sample.features
            assert "actual_positive" not in sample.features

    def test_feature_encoding_256_dim(self, tmp_path: Path):
        from impl_v1.training.data.real_dataset_loader import (
            DatasetConfig,
            RealTrainingDataset,
        )

        dataset_path = tmp_path / "verified_findings.jsonl"
        _write_verified_records(dataset_path, total=20)
        dataset = RealTrainingDataset(
            config=DatasetConfig(
                total_samples=20,
                min_verified_samples=5,
                min_class_samples=2,
                dataset_paths=(str(dataset_path),),
            ),
            feature_dim=256,
        )

        features, label = dataset[0]
        assert features.shape[0] == 256
        assert label.item() in {0, 1}

    def test_dataloader_creation(self, tmp_path: Path):
        from impl_v1.training.data.real_dataset_loader import (
            DatasetConfig,
            create_training_dataloader,
            validate_dataset_integrity,
        )

        dataset_path = tmp_path / "verified_findings.jsonl"
        _write_verified_records(dataset_path, total=40)
        config = DatasetConfig(
            total_samples=40,
            min_verified_samples=10,
            min_class_samples=4,
            dataset_paths=(str(dataset_path),),
        )
        valid, msg = validate_dataset_integrity(config)
        assert valid, msg

        import os

        old_value = os.environ.get("YGB_VERIFIED_DATASET_PATHS")
        os.environ["YGB_VERIFIED_DATASET_PATHS"] = str(dataset_path)
        try:
            train_loader, holdout_loader, stats = create_training_dataloader(
                batch_size=32,
                num_workers=0,
                pin_memory=True,
            )
        finally:
            if old_value is None:
                os.environ.pop("YGB_VERIFIED_DATASET_PATHS", None)
            else:
                os.environ["YGB_VERIFIED_DATASET_PATHS"] = old_value

        assert stats["pin_memory"] is True
        assert stats["effective_train_batch_size"] >= 1
        assert len(train_loader.dataset) > 0
        assert len(holdout_loader.dataset) > 0

    def test_dataset_determinism(self, tmp_path: Path):
        from impl_v1.training.data.real_dataset_loader import (
            DatasetConfig,
            RealTrainingDataset,
        )

        dataset_path = tmp_path / "verified_findings.jsonl"
        _write_verified_records(dataset_path, total=20)
        config = DatasetConfig(
            total_samples=20,
            min_verified_samples=5,
            min_class_samples=2,
            dataset_paths=(str(dataset_path),),
        )
        ds1 = RealTrainingDataset(config=config, seed=42)
        ds2 = RealTrainingDataset(config=config, seed=42)
        for idx in range(min(5, len(ds1))):
            f1, l1 = ds1[idx]
            f2, l2 = ds2[idx]
            assert (f1 == f2).all()
            assert l1 == l2

    def test_governance_field_stripping(self):
        from impl_v1.training.data.real_dataset_loader import strip_forbidden_fields

        clean = strip_forbidden_fields(
            {
                "category": "SQLI",
                "severity": "HIGH",
                "accepted": True,
                "payload_tested": True,
                "actual_positive": True,
            }
        )
        assert "category" in clean
        assert "payload_tested" in clean
        assert "severity" not in clean
        assert "accepted" not in clean
        assert "actual_positive" not in clean


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
