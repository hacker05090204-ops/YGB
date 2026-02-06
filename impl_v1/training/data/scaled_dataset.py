"""
Scaled Dataset Generator - Safe Training
==========================================

Generate 20,000+ samples with:
- Balanced classes
- 10% holdout
- 10% stress edge cases
- Deterministic shuffle (fixed seed)
"""

from dataclasses import dataclass
from typing import List, Tuple
from datetime import datetime
import random


# =============================================================================
# CONFIGURATION
# =============================================================================

FIXED_SEED = 42  # Deterministic shuffle


@dataclass
class DatasetConfig:
    """Dataset configuration."""
    total_samples: int = 20000
    holdout_fraction: float = 0.10
    edge_case_fraction: float = 0.10
    positive_ratio: float = 0.50  # Balanced


@dataclass
class Sample:
    """A training sample."""
    id: str
    features: dict
    label: int
    is_edge_case: bool


# =============================================================================
# DATASET GENERATOR
# =============================================================================

class ScaledDatasetGenerator:
    """Generate scaled dataset with deterministic shuffle."""
    
    def __init__(self, config: DatasetConfig = None, seed: int = FIXED_SEED):
        self.config = config or DatasetConfig()
        self.seed = seed
        self.rng = random.Random(seed)
    
    def generate(self) -> Tuple[List[Sample], List[Sample]]:
        """
        Generate train and holdout splits.
        
        Returns:
            Tuple of (train_samples, holdout_samples)
        """
        samples = []
        
        # Calculate counts
        n_positive = int(self.config.total_samples * self.config.positive_ratio)
        n_negative = self.config.total_samples - n_positive
        n_edge = int(self.config.total_samples * self.config.edge_case_fraction)
        
        # Generate positive samples
        for i in range(n_positive):
            is_edge = i < n_edge // 2
            samples.append(self._create_sample(i, 1, is_edge))
        
        # Generate negative samples
        for i in range(n_negative):
            is_edge = i < n_edge // 2
            samples.append(self._create_sample(n_positive + i, 0, is_edge))
        
        # Deterministic shuffle
        self.rng.shuffle(samples)
        
        # Split holdout
        n_holdout = int(len(samples) * self.config.holdout_fraction)
        holdout = samples[:n_holdout]
        train = samples[n_holdout:]
        
        return train, holdout
    
    def _create_sample(self, idx: int, label: int, is_edge: bool) -> Sample:
        """Create a sample."""
        if is_edge:
            # Edge case: harder features
            features = {
                "type": "edge_case",
                "difficulty": self.rng.uniform(0.8, 1.0),
                "noise": self.rng.uniform(0.3, 0.5),
            }
        else:
            features = {
                "type": "standard",
                "difficulty": self.rng.uniform(0.1, 0.7),
                "noise": self.rng.uniform(0.0, 0.2),
            }
        
        return Sample(
            id=f"S{idx:06d}",
            features=features,
            label=label,
            is_edge_case=is_edge,
        )
    
    def get_statistics(self, samples: List[Sample]) -> dict:
        """Get dataset statistics."""
        n_positive = sum(1 for s in samples if s.label == 1)
        n_edge = sum(1 for s in samples if s.is_edge_case)
        
        return {
            "total": len(samples),
            "positive": n_positive,
            "negative": len(samples) - n_positive,
            "edge_cases": n_edge,
            "positive_ratio": round(n_positive / len(samples), 4) if samples else 0,
            "edge_ratio": round(n_edge / len(samples), 4) if samples else 0,
        }


# =============================================================================
# VERIFICATION
# =============================================================================

def verify_determinism(seed: int = FIXED_SEED) -> bool:
    """Verify dataset generation is deterministic."""
    gen1 = ScaledDatasetGenerator(seed=seed)
    gen2 = ScaledDatasetGenerator(seed=seed)
    
    train1, _ = gen1.generate()
    train2, _ = gen2.generate()
    
    # Check exact match
    for s1, s2 in zip(train1, train2):
        if s1.id != s2.id or s1.label != s2.label:
            return False
    
    return True
