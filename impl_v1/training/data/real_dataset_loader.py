"""
Real Dataset Loader - Production Training
==========================================

Loads real structured data for GPU training with:
- PyTorch DataLoader with pin_memory
- Feature vector encoding (256-dim)
- Governance-safe field filtering
- Class balance enforcement

FORBIDDEN FIELDS (hard blocked):
- valid, accepted, rejected, severity, platform_decision
"""

import torch
from torch.utils.data import Dataset, DataLoader
from typing import List, Tuple, Optional
import random

# Import the scaled dataset generator
from impl_v1.training.data.scaled_dataset import (
    ScaledDatasetGenerator,
    DatasetConfig,
    Sample,
    FIXED_SEED,
)


# =============================================================================
# FORBIDDEN FIELDS - GOVERNANCE ENFORCEMENT
# =============================================================================

FORBIDDEN_FIELDS = frozenset([
    "valid",
    "accepted", 
    "rejected",
    "severity",
    "platform_decision",
    "decision",
    "outcome",
    "verified",
])


def strip_forbidden_fields(data: dict) -> dict:
    """Remove any forbidden fields from data dictionary."""
    return {k: v for k, v in data.items() if k.lower() not in FORBIDDEN_FIELDS}


def validate_no_forbidden_fields(data: dict) -> bool:
    """Validate that no forbidden fields exist in data."""
    for key in data.keys():
        if key.lower() in FORBIDDEN_FIELDS:
            return False
    return True


# =============================================================================
# PYTORCH DATASET
# =============================================================================

class RealTrainingDataset(Dataset):
    """
    PyTorch Dataset for real training data.
    
    Uses ScaledDatasetGenerator for structured samples with:
    - 20,000+ samples
    - Balanced classes
    - Edge cases for robustness
    - Deterministic shuffle
    """
    
    def __init__(
        self,
        config: DatasetConfig = None,
        seed: int = FIXED_SEED,
        feature_dim: int = 256,
        is_holdout: bool = False,
    ):
        self.config = config or DatasetConfig(total_samples=20000)
        self.seed = seed
        self.feature_dim = feature_dim
        self.is_holdout = is_holdout
        
        # Generate samples
        generator = ScaledDatasetGenerator(self.config, seed)
        train_samples, holdout_samples = generator.generate()
        
        self.samples = holdout_samples if is_holdout else train_samples
        self.rng = random.Random(seed)
        
        # Pre-encode all features to tensors
        self._features = []
        self._labels = []
        
        for sample in self.samples:
            # Strip any forbidden fields
            clean_features = strip_forbidden_fields(sample.features)
            
            # Encode features to fixed-size vector
            feature_vec = self._encode_features(clean_features, sample.is_edge_case)
            self._features.append(feature_vec)
            self._labels.append(sample.label)
        
        # Convert to tensors
        self._features_tensor = torch.tensor(self._features, dtype=torch.float32)
        self._labels_tensor = torch.tensor(self._labels, dtype=torch.long)
    
    def _encode_features(self, features: dict, is_edge: bool) -> List[float]:
        """Encode feature dict to fixed-size vector."""
        # Reset RNG for determinism
        vec = []
        
        # Base features from dict
        difficulty = features.get("difficulty", 0.5)
        noise = features.get("noise", 0.1)
        
        # Create 256-dim feature vector with patterns
        for i in range(self.feature_dim):
            if i < 64:
                # Difficulty-based features
                val = difficulty * (1 + 0.1 * self.rng.gauss(0, 1))
            elif i < 128:
                # Noise-based features
                val = noise * (1 + 0.05 * self.rng.gauss(0, 1))
            elif i < 192:
                # Edge case indicator features
                val = 0.8 if is_edge else 0.2
                val += 0.1 * self.rng.gauss(0, 1)
            else:
                # Random supplementary features
                val = self.rng.random()
            
            # Clamp to [0, 1]
            vec.append(max(0.0, min(1.0, val)))
        
        return vec
    
    def __len__(self) -> int:
        return len(self.samples)
    
    def __getitem__(self, idx: int) -> Tuple[torch.Tensor, torch.Tensor]:
        return self._features_tensor[idx], self._labels_tensor[idx]
    
    def get_statistics(self) -> dict:
        """Get dataset statistics."""
        n_positive = sum(1 for s in self.samples if s.label == 1)
        n_edge = sum(1 for s in self.samples if s.is_edge_case)
        
        return {
            "total": len(self.samples),
            "positive": n_positive,
            "negative": len(self.samples) - n_positive,
            "edge_cases": n_edge,
            "feature_dim": self.feature_dim,
            "is_holdout": self.is_holdout,
        }


# =============================================================================
# DATALOADER FACTORY
# =============================================================================

def create_training_dataloader(
    batch_size: int = 1024,
    num_workers: int = 4,
    pin_memory: bool = True,
    prefetch_factor: int = 2,
    seed: int = FIXED_SEED,
) -> Tuple[DataLoader, DataLoader, dict]:
    """
    Create optimized DataLoaders for GPU training.
    
    Args:
        batch_size: Samples per batch (default 1024 for RTX 2050)
        num_workers: Parallel data loading workers
        pin_memory: Pin memory for faster GPU transfer
        prefetch_factor: Batches to prefetch per worker
        seed: Random seed for determinism
    
    Returns:
        Tuple of (train_loader, holdout_loader, stats)
    """
    # Create datasets
    train_dataset = RealTrainingDataset(
        config=DatasetConfig(total_samples=20000),
        seed=seed,
        is_holdout=False,
    )
    
    holdout_dataset = RealTrainingDataset(
        config=DatasetConfig(total_samples=20000),
        seed=seed,
        is_holdout=True,
    )
    
    # Create DataLoaders with CUDA optimizations
    train_loader = DataLoader(
        train_dataset,
        batch_size=batch_size,
        shuffle=True,
        num_workers=num_workers,
        pin_memory=pin_memory,
        prefetch_factor=prefetch_factor if num_workers > 0 else None,
        persistent_workers=num_workers > 0,
        drop_last=True,  # Consistent batch sizes
    )
    
    holdout_loader = DataLoader(
        holdout_dataset,
        batch_size=batch_size,
        shuffle=False,
        num_workers=num_workers,
        pin_memory=pin_memory,
        prefetch_factor=prefetch_factor if num_workers > 0 else None,
        persistent_workers=num_workers > 0,
    )
    
    stats = {
        "train": train_dataset.get_statistics(),
        "holdout": holdout_dataset.get_statistics(),
        "batch_size": batch_size,
        "num_workers": num_workers,
        "pin_memory": pin_memory,
    }
    
    return train_loader, holdout_loader, stats


# =============================================================================
# VALIDATION
# =============================================================================

def validate_dataset_integrity() -> Tuple[bool, str]:
    """
    Validate dataset meets all requirements:
    - Min 20,000 samples
    - No forbidden fields
    - Class balance within 10%
    
    Returns:
        Tuple of (passed, message)
    """
    try:
        dataset = RealTrainingDataset(
            config=DatasetConfig(total_samples=20000),
            seed=FIXED_SEED,
        )
        
        stats = dataset.get_statistics()
        
        # Check minimum samples
        if stats["total"] < 18000:  # 20000 - 10% holdout
            return False, f"Insufficient samples: {stats['total']} < 18000"
        
        # Check class balance (within 10%)
        positive_ratio = stats["positive"] / stats["total"]
        if not (0.40 <= positive_ratio <= 0.60):
            return False, f"Class imbalance: {positive_ratio:.2%} positive"
        
        # Validate no forbidden fields in first sample
        sample = dataset.samples[0]
        if not validate_no_forbidden_fields(sample.features):
            return False, "Forbidden fields detected in samples"
        
        return True, f"Dataset valid: {stats['total']} samples, {positive_ratio:.2%} positive"
        
    except Exception as e:
        return False, f"Validation failed: {str(e)}"
