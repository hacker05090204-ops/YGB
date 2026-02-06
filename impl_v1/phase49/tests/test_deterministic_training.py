"""
Deterministic Training Tests - Phase 49
========================================

Tests for deterministic AI training:
1. Seed synchronization
2. RNG checkpointing
3. Replay determinism
"""

import unittest
import random
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

# Add to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from impl_v1.phase49.training.deterministic_training import (
    set_deterministic_mode,
    get_rng_states,
    restore_rng_states,
    verify_replay_determinism,
    compute_loss_hash,
    DEFAULT_SEED,
)


class TestSeedSynchronization(unittest.TestCase):
    """Test: All seeds are synchronized."""
    
    def test_python_random_seeded(self):
        """Python random is seeded."""
        set_deterministic_mode(seed=42)
        val1 = random.random()
        
        set_deterministic_mode(seed=42)
        val2 = random.random()
        
        self.assertEqual(val1, val2)
    
    def test_different_seeds_different_values(self):
        """Different seeds produce different values."""
        set_deterministic_mode(seed=42)
        val1 = random.random()
        
        set_deterministic_mode(seed=123)
        val2 = random.random()
        
        self.assertNotEqual(val1, val2)
    
    def test_seed_stored_in_states(self):
        """Seed is stored in returned states."""
        states = set_deterministic_mode(seed=12345)
        self.assertEqual(states["seed"], 12345)


class TestRNGCheckpointing(unittest.TestCase):
    """Test: RNG states are saved and restored."""
    
    def test_get_states_includes_python_random(self):
        """Python random state is captured."""
        states = get_rng_states()
        self.assertIn("python_random", states)
    
    def test_restore_produces_same_sequence(self):
        """Restoring states produces same random sequence."""
        set_deterministic_mode(seed=42)
        
        # Get some random values
        _ = [random.random() for _ in range(10)]
        
        # Save state
        states = get_rng_states()
        
        # Generate more values
        expected = [random.random() for _ in range(5)]
        
        # Restore and generate again
        restore_rng_states(states)
        actual = [random.random() for _ in range(5)]
        
        self.assertEqual(expected, actual)


class TestReplayDeterminism(unittest.TestCase):
    """Test: Replay verification works correctly."""
    
    def test_identical_curves_pass(self):
        """Identical loss curves pass verification."""
        curve = [0.5, 0.4, 0.3, 0.2, 0.1]
        is_det, error = verify_replay_determinism(curve, curve.copy())
        self.assertTrue(is_det)
        self.assertIsNone(error)
    
    def test_different_curves_fail(self):
        """Different loss curves fail verification."""
        curve1 = [0.5, 0.4, 0.3, 0.2, 0.1]
        curve2 = [0.5, 0.4, 0.31, 0.2, 0.1]  # Drift at epoch 2
        is_det, error = verify_replay_determinism(curve1, curve2)
        self.assertFalse(is_det)
        self.assertIn("Drift", error)
    
    def test_length_mismatch_fails(self):
        """Different length curves fail verification."""
        curve1 = [0.5, 0.4, 0.3]
        curve2 = [0.5, 0.4]
        is_det, error = verify_replay_determinism(curve1, curve2)
        self.assertFalse(is_det)
        self.assertIn("Length mismatch", error)
    
    def test_tolerance_respected(self):
        """Small differences within tolerance pass."""
        curve1 = [0.5, 0.4, 0.3]
        curve2 = [0.5, 0.4 + 1e-9, 0.3]  # Very small difference
        is_det, error = verify_replay_determinism(curve1, curve2, tolerance=1e-6)
        self.assertTrue(is_det)


class TestLossHash(unittest.TestCase):
    """Test: Loss curve hashing."""
    
    def test_same_curve_same_hash(self):
        """Same curve produces same hash."""
        curve = [0.5, 0.4, 0.3, 0.2, 0.1]
        hash1 = compute_loss_hash(curve)
        hash2 = compute_loss_hash(curve)
        self.assertEqual(hash1, hash2)
    
    def test_different_curve_different_hash(self):
        """Different curves produce different hashes."""
        curve1 = [0.5, 0.4, 0.3]
        curve2 = [0.5, 0.4, 0.31]
        hash1 = compute_loss_hash(curve1)
        hash2 = compute_loss_hash(curve2)
        self.assertNotEqual(hash1, hash2)
    
    def test_hash_is_16_chars(self):
        """Hash is 16 characters."""
        curve = [0.5, 0.4, 0.3]
        hash_val = compute_loss_hash(curve)
        self.assertEqual(len(hash_val), 16)


if __name__ == "__main__":
    unittest.main()
