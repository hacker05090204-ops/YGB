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


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
