"""
Test No Synthetic Fallback
===========================

Validates:
- No synthetic data in training pipeline
- No random.random() for training data
- No fallback to mock data
- Real dataset connected
"""

import pytest
import inspect
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))))


class TestNoSyntheticFallback:
    """Ensure no synthetic data survives in the training pipeline."""
    
    def test_no_random_data_in_init_gpu(self):
        """_init_gpu_resources must NOT use random.random() for training data."""
        from impl_v1.phase49.runtime.auto_trainer import AutoTrainer
        
        source = inspect.getsource(AutoTrainer._init_gpu_resources)
        
        # Must NOT contain random data generation
        assert "random.random()" not in source, \
            "_init_gpu_resources still uses random.random() for synthetic data"
        assert "random.randint(0, 1)" not in source, \
            "_init_gpu_resources still uses random.randint for synthetic labels"
    
    def test_no_512_samples_hardcoded(self):
        """Must NOT have hardcoded 512 synthetic samples."""
        from impl_v1.phase49.runtime.auto_trainer import AutoTrainer
        
        source = inspect.getsource(AutoTrainer._init_gpu_resources)
        
        assert "range(512)" not in source, \
            "_init_gpu_resources still has hardcoded 512 sample loop"
    
    def test_uses_real_dataset_loader(self):
        """_init_gpu_resources must import real_dataset_loader."""
        from impl_v1.phase49.runtime.auto_trainer import AutoTrainer
        
        source = inspect.getsource(AutoTrainer._init_gpu_resources)
        
        assert "real_dataset_loader" in source, \
            "_init_gpu_resources must use real_dataset_loader"
        assert "create_training_dataloader" in source, \
            "_init_gpu_resources must use create_training_dataloader"
    
    def test_uses_validate_dataset_integrity(self):
        """_init_gpu_resources must validate dataset before use."""
        from impl_v1.phase49.runtime.auto_trainer import AutoTrainer
        
        source = inspect.getsource(AutoTrainer._init_gpu_resources)
        
        assert "validate_dataset_integrity" in source, \
            "_init_gpu_resources must validate dataset integrity"
    
    def test_real_dataset_has_minimum_samples(self):
        """Real dataset must have at least 18000 samples."""
        from impl_v1.training.data.real_dataset_loader import (
            validate_dataset_integrity,
        )
        
        valid, msg = validate_dataset_integrity()
        assert valid, f"Dataset validation failed: {msg}"
    
    def test_no_mock_keyword_in_init(self):
        """No 'mock' or 'synthetic' in _init_gpu_resources."""
        from impl_v1.phase49.runtime.auto_trainer import AutoTrainer
        
        source = inspect.getsource(AutoTrainer._init_gpu_resources).lower()
        
        assert "mock" not in source, \
            "Found 'mock' keyword in _init_gpu_resources"
        # Allow 'synthetic' only in 'NO SYNTHETIC' documentation
        lines_with_synthetic = [
            line for line in source.split('\n')
            if 'synthetic' in line and 'no synthetic' not in line
        ]
        assert len(lines_with_synthetic) == 0, \
            f"Found synthetic data references: {lines_with_synthetic}"
    
    def test_batch_size_is_1024(self):
        """Batch size must be 1024 for optimal GPU utilization."""
        from impl_v1.phase49.runtime.auto_trainer import AutoTrainer
        
        source = inspect.getsource(AutoTrainer._init_gpu_resources)
        
        assert "batch_size=1024" in source, \
            f"Batch size should be 1024, not found in _init_gpu_resources"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
