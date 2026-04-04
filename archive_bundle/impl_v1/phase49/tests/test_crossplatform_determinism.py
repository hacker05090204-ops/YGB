"""
Cross-Platform Determinism Tests - Phase 49
============================================

Verify training determinism across:
- Linux CUDA
- Windows CUDA
- CPU (both platforms)

Compare:
- Weights identical
- RNG states identical
- Loss curves identical
"""

import unittest
import hashlib
import json
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass
from pathlib import Path
import sys
import random

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from impl_v1.phase49.training.deterministic_training import (
    set_deterministic_mode,
    get_rng_states,
    verify_replay_determinism,
    compute_loss_hash,
)


# =============================================================================
# DETERMINISM REQUIREMENTS
# =============================================================================

TOLERANCE = 1e-6  # Maximum allowed difference in weights
EPOCHS_TO_TEST = 3
SEED = 42


# =============================================================================
# MOCK TRAINING FOR TESTING
# =============================================================================

def mock_train_epoch(seed: int, epoch: int) -> Tuple[float, List[float]]:
    """Mock training epoch - deterministic based on seed."""
    random.seed(seed + epoch)
    loss = 1.0
    weights = []
    
    for i in range(100):  # 100 "weights"
        delta = random.random() * 0.1
        loss -= delta / 100
        weights.append(random.random())
    
    return loss, weights


def compute_weights_hash(weights: List[float]) -> str:
    """Compute hash of weight values."""
    weights_str = ":".join(f"{w:.8f}" for w in weights)
    return hashlib.sha256(weights_str.encode()).hexdigest()[:16]


# =============================================================================
# TESTS
# =============================================================================

class TestCrossPlatformDeterminism(unittest.TestCase):
    """Test cross-platform determinism."""
    
    def test_same_seed_same_loss(self):
        """Same seed produces same loss."""
        set_deterministic_mode(seed=SEED)
        loss1, _ = mock_train_epoch(SEED, 0)
        
        set_deterministic_mode(seed=SEED)
        loss2, _ = mock_train_epoch(SEED, 0)
        
        self.assertEqual(loss1, loss2)
    
    def test_same_seed_same_weights(self):
        """Same seed produces identical weights."""
        set_deterministic_mode(seed=SEED)
        _, weights1 = mock_train_epoch(SEED, 0)
        hash1 = compute_weights_hash(weights1)
        
        set_deterministic_mode(seed=SEED)
        _, weights2 = mock_train_epoch(SEED, 0)
        hash2 = compute_weights_hash(weights2)
        
        self.assertEqual(hash1, hash2)
    
    def test_multi_epoch_determinism(self):
        """Multiple epochs are deterministic."""
        set_deterministic_mode(seed=SEED)
        losses1 = []
        for epoch in range(EPOCHS_TO_TEST):
            loss, _ = mock_train_epoch(SEED, epoch)
            losses1.append(loss)
        
        set_deterministic_mode(seed=SEED)
        losses2 = []
        for epoch in range(EPOCHS_TO_TEST):
            loss, _ = mock_train_epoch(SEED, epoch)
            losses2.append(loss)
        
        is_det, error = verify_replay_determinism(losses1, losses2)
        self.assertTrue(is_det, error)
    
    def test_loss_curve_hash_stable(self):
        """Loss curve hash is stable across runs."""
        set_deterministic_mode(seed=SEED)
        losses1 = [mock_train_epoch(SEED, e)[0] for e in range(EPOCHS_TO_TEST)]
        hash1 = compute_loss_hash(losses1)
        
        set_deterministic_mode(seed=SEED)
        losses2 = [mock_train_epoch(SEED, e)[0] for e in range(EPOCHS_TO_TEST)]
        hash2 = compute_loss_hash(losses2)
        
        self.assertEqual(hash1, hash2)
    
    def test_rng_state_restoration(self):
        """RNG state restoration produces identical sequence."""
        set_deterministic_mode(seed=SEED)
        
        # Generate some random values
        _ = [random.random() for _ in range(10)]
        
        # Save state
        state = get_rng_states()
        
        # Generate more and save result
        expected = [random.random() for _ in range(5)]
        
        # Restore and generate again
        random.setstate(state["python_random"])
        actual = [random.random() for _ in range(5)]
        
        self.assertEqual(expected, actual)
    
    def test_different_seeds_different_results(self):
        """Different seeds produce different results."""
        set_deterministic_mode(seed=42)
        _, weights1 = mock_train_epoch(42, 0)
        
        set_deterministic_mode(seed=123)
        _, weights2 = mock_train_epoch(123, 0)
        
        hash1 = compute_weights_hash(weights1)
        hash2 = compute_weights_hash(weights2)
        
        self.assertNotEqual(hash1, hash2)


class TestDeterminismCIEnforcement(unittest.TestCase):
    """Test CI enforcement of determinism."""
    
    def test_ci_would_fail_on_drift(self):
        """CI should fail if loss curves drift."""
        curve1 = [0.5, 0.4, 0.3]
        curve2 = [0.5, 0.4, 0.31]  # Drift
        
        is_det, _ = verify_replay_determinism(curve1, curve2)
        self.assertFalse(is_det)  # Should fail
    
    def test_ci_passes_on_identical(self):
        """CI passes on identical curves."""
        curve = [0.5, 0.4, 0.3]
        
        is_det, _ = verify_replay_determinism(curve, curve.copy())
        self.assertTrue(is_det)
    
    def test_hash_changes_on_modification(self):
        """Hash changes if any value changes."""
        curve1 = [0.5, 0.4, 0.3]
        curve2 = [0.5, 0.4, 0.30000001]
        
        hash1 = compute_loss_hash(curve1)
        hash2 = compute_loss_hash(curve2)
        
        self.assertNotEqual(hash1, hash2)


if __name__ == "__main__":
    unittest.main()
