"""
Test Real Dataset Pipeline
===========================

Validates:
- Dataset loading with 20K+ samples
- No forbidden fields
- Class balance within 10%
- Feature encoding to 256-dim
- DataLoader with pin_memory
"""

import pytest
import sys
import os
import errno
import hashlib
import json
from datetime import datetime, timezone

import numpy as np

# Add parent path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))))


class TestRealDatasetPipeline:
    """Tests for real dataset loader."""
    
    def test_dataset_minimum_samples(self):
        """Dataset must have at least 18000 training samples."""
        from impl_v1.training.data.real_dataset_loader import (
            RealTrainingDataset,
            DatasetConfig,
        )
        
        dataset = RealTrainingDataset(
            config=DatasetConfig(total_samples=20000),
            is_holdout=False,
        )
        
        stats = dataset.get_statistics()
        assert stats["total"] >= 18000, f"Insufficient samples: {stats['total']}"
    
    def test_no_forbidden_fields(self):
        """No forbidden fields (severity, accepted, rejected, etc.) in samples."""
        from impl_v1.training.data.real_dataset_loader import (
            RealTrainingDataset,
            validate_no_forbidden_fields,
            DatasetConfig,
        )
        
        dataset = RealTrainingDataset(config=DatasetConfig(total_samples=100))
        
        for sample in dataset.samples:
            assert validate_no_forbidden_fields(sample.features), \
                f"Forbidden field found in sample {sample.id}"
    
    def test_class_balance(self):
        """Classes must be balanced within 10%."""
        from impl_v1.training.data.real_dataset_loader import (
            RealTrainingDataset,
            DatasetConfig,
        )
        
        dataset = RealTrainingDataset(config=DatasetConfig(total_samples=10000))
        stats = dataset.get_statistics()
        
        positive_ratio = stats["positive"] / stats["total"]
        assert 0.40 <= positive_ratio <= 0.60, \
            f"Class imbalance: {positive_ratio:.2%} positive"
    
    def test_feature_encoding_256_dim(self):
        """Features must encode to 256-dim vectors."""
        from impl_v1.training.data.real_dataset_loader import (
            RealTrainingDataset,
            DatasetConfig,
        )
        
        dataset = RealTrainingDataset(
            config=DatasetConfig(total_samples=100),
            feature_dim=256,
        )
        
        features, label = dataset[0]
        assert features.shape[0] == 256, f"Expected 256-dim, got {features.shape[0]}"
    
    def test_dataloader_creation(self):
        """DataLoader must be created with pin_memory."""
        from impl_v1.training.data.real_dataset_loader import (
            create_training_dataloader,
        )
        
        train_loader, holdout_loader, stats = create_training_dataloader(
            batch_size=32,
            num_workers=0,  # For testing
            pin_memory=True,
        )
        
        assert stats["pin_memory"] is True
        assert stats["batch_size"] == 32
        assert stats["train"]["total"] >= 18000
    
    def test_dataset_determinism(self):
        """Dataset generation must be deterministic."""
        from impl_v1.training.data.real_dataset_loader import (
            RealTrainingDataset,
            DatasetConfig,
        )
        
        ds1 = RealTrainingDataset(config=DatasetConfig(total_samples=100), seed=42)
        ds2 = RealTrainingDataset(config=DatasetConfig(total_samples=100), seed=42)
        
        for i in range(10):
            f1, l1 = ds1[i]
            f2, l2 = ds2[i]
            assert (f1 == f2).all(), f"Features differ at index {i}"
            assert l1 == l2, f"Labels differ at index {i}"
    
    def test_governance_field_stripping(self):
        """Forbidden fields must be stripped from data."""
        from impl_v1.training.data.real_dataset_loader import strip_forbidden_fields
        
        dirty_data = {
            "type": "standard",
            "severity": "HIGH",  # FORBIDDEN
            "accepted": True,  # FORBIDDEN
            "difficulty": 0.5,
        }
        
        clean = strip_forbidden_fields(dirty_data)
        
        assert "type" in clean
        assert "difficulty" in clean
        assert "severity" not in clean
        assert "accepted" not in clean

    def test_ingestion_encoder_uses_parameters_content(self):
        """Changing parameters should change the encoded representation."""
        from impl_v1.training.data.real_dataset_loader import IngestionPipelineDataset

        dataset = IngestionPipelineDataset.__new__(IngestionPipelineDataset)
        dataset.feature_dim = 256
        features = {
            "signal_strength": 0.82,
            "response_ratio": 0.61,
            "difficulty": 0.18,
            "noise": 0.05,
            "endpoint_entropy": 0.74,
            "exploit_complexity": 0.69,
            "impact_severity": 0.87,
            "fingerprint_density": 0.63,
            "parameter_ratio": 0.44,
            "parameters_entropy": 0.58,
        }

        vec_a = dataset._encode_features(
            features,
            endpoint="/api/v1/users/42",
            parameters="id=42&sort=asc",
            exploit_vector="UNION SELECT 1,2,3",
            impact="CVSS:8.1|Sensitive data exposure",
            source_tag="nvd",
            fingerprint="0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
        )
        vec_b = dataset._encode_features(
            features,
            endpoint="/api/v1/users/42",
            parameters="account=42&filter=active&expand=profile",
            exploit_vector="UNION SELECT 1,2,3",
            impact="CVSS:8.1|Sensitive data exposure",
            source_tag="nvd",
            fingerprint="0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
        )

        assert len(vec_a) == 256
        assert len(vec_b) == 256
        assert vec_a != vec_b
        assert vec_a[32:64] != vec_b[32:64]

    def test_ingestion_encoder_entropy_profile(self):
        """Encoded real-ingestion features should clear the native entropy floor."""
        from impl_v1.training.data.real_dataset_loader import IngestionPipelineDataset

        dataset = IngestionPipelineDataset.__new__(IngestionPipelineDataset)
        dataset.feature_dim = 256

        rows = []
        for i in range(256):
            signal = ((i * 7) % 100) / 100.0
            response = ((i * 11) % 100) / 100.0
            difficulty = 1.0 - min(signal * 0.7 + 0.1, 1.0)
            impact_severity = min(0.2 + ((i * 13) % 80) / 100.0, 1.0)
            fingerprint_density = 0.25 + ((i * 5) % 70) / 100.0
            parameters = f"id={i}&page={i % 9}&sort={(i * 3) % 7}&token={i:04x}"
            impact = f"CVSS:{3.0 + (i % 7):.1f}|impact-{i % 19}|scope-{i % 5}"
            row = dataset._encode_features(
                {
                    "signal_strength": signal,
                    "response_ratio": response,
                    "difficulty": difficulty,
                    "noise": 0.05,
                    "endpoint_entropy": 0.35 + ((i * 9) % 50) / 100.0,
                    "exploit_complexity": 0.30 + ((i * 4) % 60) / 100.0,
                    "impact_severity": impact_severity,
                    "fingerprint_density": fingerprint_density,
                    "parameter_ratio": min(len(parameters) / 96.0, 1.0),
                    "parameters_entropy": 0.25 + ((i * 6) % 60) / 100.0,
                },
                endpoint=f"/api/v{i % 4}/users/{i % 37}/items/{(i * 5) % 91}",
                parameters=parameters,
                exploit_vector=f"payload-{i % 17}-step-{(i * i) % 97}-probe",
                impact=impact,
                source_tag=f"source_{i % 23}",
                fingerprint=hashlib.sha256(f"sample-{i}".encode()).hexdigest(),
            )
            rows.append(row)

        features = np.asarray(rows, dtype=np.float64)

        def _entropy(col: np.ndarray, bins: int = 64) -> float:
            vmin = float(col.min())
            vmax = float(col.max())
            rng = vmax - vmin
            if rng < 1e-12:
                return 0.0
            hist = np.zeros(bins, dtype=np.int64)
            scaled = ((col - vmin) / rng * (bins - 1)).astype(np.int64)
            scaled = np.clip(scaled, 0, bins - 1)
            for bucket in scaled:
                hist[bucket] += 1
            probs = hist[hist > 0] / col.size
            return float(-(probs * np.log2(probs)).sum())

        entropies = np.asarray([_entropy(features[:, idx]) for idx in range(features.shape[1])])
        low_entropy_count = int((entropies < 1.5).sum())

        assert entropies.min() > 1.5
        assert low_entropy_count < (features.shape[1] // 4)

    def test_persisted_samples_forward_parameters(self, monkeypatch):
        """Persisted samples must carry parameters into the real encoder path."""
        from impl_v1.training.data.real_dataset_loader import IngestionPipelineDataset

        dataset = IngestionPipelineDataset.__new__(IngestionPipelineDataset)
        captured = []

        def _fake_process_one_sample(
            endpoint, parameters, exploit_vector, impact, source_tag,
            fingerprint, reliability_val, policy, scorer,
        ):
            captured.append(
                {
                    "endpoint": endpoint,
                    "parameters": parameters,
                    "source_tag": source_tag,
                    "reliability": reliability_val,
                }
            )
            return "accepted"

        monkeypatch.setattr(dataset, "_process_one_sample", _fake_process_one_sample)

        accepted, rejected_policy, rejected_quality = dataset._process_persisted_samples(
            [
                {
                    "endpoint": "CVE-2026-00007",
                    "parameters": "id=7&role=user",
                    "exploit_vector": "probe-vector",
                    "impact": "CVSS:7.3|impact",
                    "source_tag": "nvd",
                    "fingerprint": "abc123",
                    "reliability": 0.91,
                    "published_at": datetime.now(timezone.utc).isoformat(),
                }
            ],
            policy=object(),
            scorer=object(),
            min_samples=1,
        )

        assert accepted == 1
        assert rejected_policy == 0
        assert rejected_quality == 0
        assert captured[0]["parameters"] == "id=7&role=user"

    def test_ingestion_tensor_cache_round_trip(self, monkeypatch, tmp_path):
        """Encoded ingestion tensors should persist and reload from safetensors cache."""
        torch = pytest.importorskip("torch")
        pytest.importorskip("safetensors")
        import impl_v1.training.data.real_dataset_loader as rdl

        secure_data = tmp_path / "secure_data"
        monkeypatch.setattr(rdl, "_SECURE_DATA", secure_data)

        dataset = rdl.IngestionPipelineDataset.__new__(rdl.IngestionPipelineDataset)
        dataset.feature_dim = 4
        dataset.min_samples = 2
        dataset.seed = 42
        dataset._verified_count = 2
        dataset._manifest_hash = "manifest-cache-key"
        dataset._raw_samples = [{"reliability": 0.91}, {"reliability": 0.72}]
        dataset._features = []
        dataset._labels = [1, 0]
        dataset._features_tensor = torch.tensor(
            [[0.1, 0.2, 0.3, 0.4], [0.5, 0.6, 0.7, 0.8]],
            dtype=torch.float32,
        )
        dataset._labels_tensor = torch.tensor([1, 0], dtype=torch.long)

        metadata = dataset._build_tensor_cache_metadata(
            accepted=2,
            rejected_policy=0,
            rejected_quality=0,
            verified_count=2,
        )
        dataset._save_tensor_cache(metadata)

        reloaded = rdl.IngestionPipelineDataset.__new__(rdl.IngestionPipelineDataset)
        reloaded.feature_dim = 4
        reloaded.min_samples = 2
        reloaded.seed = 42
        reloaded._verified_count = 2
        reloaded._manifest_hash = "manifest-cache-key"
        reloaded._raw_samples = []
        reloaded._features = []
        reloaded._labels = []
        reloaded._tensor_cache_metadata = {}

        assert reloaded._load_tensor_cache(2) is True
        assert torch.equal(reloaded._features_tensor, dataset._features_tensor)
        assert torch.equal(reloaded._labels_tensor, dataset._labels_tensor)

        reloaded._ensure_manifest_from_cache()
        manifest = json.loads((secure_data / "dataset_manifest.json").read_text(encoding="utf-8"))
        assert manifest["tensor_hash"] == metadata["tensor_hash"]
        assert manifest["sample_count"] == 2

    def test_dataset_integrity_guard_accepts_parseable_finite_manifest(self, tmp_path):
        from impl_v1.training.data.real_dataset_loader import DatasetIntegrityGuard

        manifest_path = tmp_path / "dataset_manifest.json"
        manifest_path.write_text(
            json.dumps({"dataset_source": "INGESTION_PIPELINE", "sample_count": 10}),
            encoding="utf-8",
        )

        result = DatasetIntegrityGuard().verify(manifest_path)

        assert result.exists is True
        assert result.parseable is True
        assert result.finite is True
        assert result.size_bytes > 0
        assert result.issues == ()

    def test_dataset_integrity_guard_rejects_non_finite_json_values(self, tmp_path):
        from impl_v1.training.data.real_dataset_loader import (
            DatasetIntegrityError,
            DatasetIntegrityGuard,
        )

        manifest_path = tmp_path / "dataset_manifest.json"
        manifest_path.write_text('{"sample_count": NaN}', encoding="utf-8")

        with pytest.raises(DatasetIntegrityError, match="NaN"):
            DatasetIntegrityGuard().verify(manifest_path)

    def test_dataset_integrity_guard_retries_transient_io_errors(self, monkeypatch, tmp_path):
        import builtins
        import impl_v1.training.data.real_dataset_loader as rdl

        manifest_path = tmp_path / "dataset_manifest.json"
        manifest_path.write_text(json.dumps({"sample_count": 10}), encoding="utf-8")

        attempts = {"count": 0}
        sleeps = []
        real_open = builtins.open

        def _flaky_open(path, *args, **kwargs):
            if os.fspath(path) == os.fspath(manifest_path) and attempts["count"] < 2:
                attempts["count"] += 1
                err = BlockingIOError("temporary dataset lock")
                err.errno = errno.EAGAIN
                raise err
            return real_open(path, *args, **kwargs)

        monkeypatch.setattr(builtins, "open", _flaky_open)
        monkeypatch.setattr(rdl.time, "sleep", lambda seconds: sleeps.append(seconds))

        result = rdl.DatasetIntegrityGuard().verify(manifest_path)

        assert result.parseable is True
        assert attempts["count"] == 2
        assert sleeps == [0.5, 0.5]

    def test_dataset_integrity_validator_rejects_invalid_cve_format(self):
        from impl_v1.training.data.real_dataset_loader import DatasetIntegrityValidator

        validator = DatasetIntegrityValidator()

        assert validator.validate_sample(
            {
                "text": "Verified vulnerability description",
                "cve_id": "BAD-2026-00001",
                "severity": "HIGH",
                "published_at": "2026-01-01T00:00:00+00:00",
            }
        ) is False

    def test_dataset_integrity_validator_rejects_invalid_severity(self):
        from impl_v1.training.data.real_dataset_loader import DatasetIntegrityValidator

        validator = DatasetIntegrityValidator()

        assert validator.validate_sample(
            {
                "text": "Verified vulnerability description",
                "cve_id": "CVE-2026-00001",
                "severity": "SEVERE",
                "published_at": "2026-01-01T00:00:00+00:00",
            }
        ) is False

    def test_dataset_integrity_validator_rejects_unparseable_date(self):
        from impl_v1.training.data.real_dataset_loader import DatasetIntegrityValidator

        validator = DatasetIntegrityValidator()

        assert validator.validate_sample(
            {
                "text": "Verified vulnerability description",
                "cve_id": "CVE-2026-00001",
                "severity": "LOW",
                "published_at": "not-a-date",
            }
        ) is False

    def test_dataset_integrity_validator_accepts_valid_sample(self):
        from impl_v1.training.data.real_dataset_loader import DatasetIntegrityValidator

        validator = DatasetIntegrityValidator()

        assert validator.validate_sample(
            {
                "text": "Verified vulnerability description",
                "cve_id": "CVE-2026-00001",
                "severity": "INFORMATIONAL",
                "published_at": "2026-01-01T00:00:00+00:00",
            }
        ) is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
