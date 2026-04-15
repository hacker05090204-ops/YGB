"""
Tests for Deep RL Agent with sklearn integration.
Verifies reward computation, GRPO normalization, and feature augmentation.
"""

import sys
import tempfile
import pytest
from pathlib import Path
import numpy as np

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


def test_deep_rl_imports():
    """Test that deep RL agent can be imported."""
    from backend.training.deep_rl_agent import (
        DeepRLAgent,
        GRPORewardNormalizer,
        SklearnFeatureAugmenter,
        RLEpisode,
    )
    assert DeepRLAgent is not None
    assert GRPORewardNormalizer is not None
    assert SklearnFeatureAugmenter is not None
    assert RLEpisode is not None


def test_grpo_reward_normalizer():
    """Test GRPO reward normalization."""
    from backend.training.deep_rl_agent import GRPORewardNormalizer

    normalizer = GRPORewardNormalizer(group_size=4)

    # Add rewards
    rewards = [1.0, 0.5, -0.5, -1.0, 0.8, 0.3, -0.3, -0.8]
    advantages = []

    for reward in rewards:
        advantage = normalizer.add(reward)
        advantages.append(advantage)

    # First 3 rewards should return raw values (not enough for group)
    assert advantages[0] == 1.0
    assert advantages[1] == 0.5
    assert advantages[2] == -0.5

    # After group_size, should return normalized advantages
    assert isinstance(advantages[4], float)

    # Check stats
    stats = normalizer.get_stats()
    assert stats["count"] == len(rewards)
    assert "mean" in stats
    assert "std" in stats

    print(f"   + GRPO normalization working")
    print(f"   + Stats: mean={stats['mean']:.2f}, std={stats['std']:.2f}")


def test_sklearn_feature_augmenter():
    """Test sklearn feature augmentation."""
    try:
        from sklearn.preprocessing import StandardScaler
    except ImportError:
        pytest.skip("scikit-learn not installed")

    from backend.training.deep_rl_agent import SklearnFeatureAugmenter

    augmenter = SklearnFeatureAugmenter()

    # Create training data
    X_train = np.random.rand(100, 50).astype(np.float32)

    # Fit augmenter
    augmenter.fit(X_train)
    assert augmenter.is_fitted

    # Augment features
    X_test = np.random.rand(10, 50).astype(np.float32)
    X_augmented = augmenter.augment(X_test)

    # Should have additional features
    assert X_augmented.shape[0] == X_test.shape[0]
    assert X_augmented.shape[1] > X_test.shape[1]

    additional_features = augmenter.get_feature_count()
    assert additional_features > 0

    print(f"   + Feature augmentation working")
    print(f"   + Original features: {X_test.shape[1]}")
    print(f"   + Augmented features: {X_augmented.shape[1]}")
    print(f"   + Additional features: {additional_features}")


def test_sklearn_augmenter_save_load():
    """Test saving and loading sklearn augmenter."""
    try:
        from sklearn.preprocessing import StandardScaler
    except ImportError:
        pytest.skip("scikit-learn not installed")

    from backend.training.deep_rl_agent import SklearnFeatureAugmenter

    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)

        # Create and fit augmenter
        augmenter1 = SklearnFeatureAugmenter()
        X_train = np.random.rand(100, 50).astype(np.float32)
        augmenter1.fit(X_train)

        # Save
        save_path = tmpdir / "augmenter.pkl"
        augmenter1.save(save_path)
        assert save_path.exists()

        # Load into new augmenter
        augmenter2 = SklearnFeatureAugmenter()
        augmenter2.load(save_path)
        assert augmenter2.is_fitted

        # Test that both produce same output
        X_test = np.random.rand(10, 50).astype(np.float32)
        X_aug1 = augmenter1.augment(X_test)
        X_aug2 = augmenter2.augment(X_test)

        assert X_aug1.shape == X_aug2.shape
        np.testing.assert_array_almost_equal(X_aug1, X_aug2, decimal=5)

        print(f"   + Save/load working correctly")


def test_reward_computation():
    """Test reward computation for different scenarios."""
    from backend.training.deep_rl_agent import DeepRLAgent

    with tempfile.TemporaryDirectory() as tmpdir:
        agent = DeepRLAgent(checkpoint_dir=Path(tmpdir))

        # Test exact match
        ep1 = agent.record_outcome("CVE-2024-0001", "CRITICAL", "CRITICAL", "cisa_kev")
        assert ep1.reward == 1.0  # Exact match with max trust

        # Test off by one level
        ep2 = agent.record_outcome("CVE-2024-0002", "HIGH", "CRITICAL", "cisa_kev")
        assert ep2.reward < 0  # Penalty for missing critical

        # Test false critical
        ep3 = agent.record_outcome("CVE-2024-0003", "CRITICAL", "LOW", "cisa_kev")
        assert ep3.reward < -0.5  # Large penalty for false critical

        # Test with lower trust source
        ep4 = agent.record_outcome("CVE-2024-0004", "MEDIUM", "MEDIUM", "label")
        assert 0 < ep4.reward < 1.0  # Exact match but lower trust

        print(f"   + Reward computation working")
        print(f"   + Exact match: {ep1.reward:.2f}")
        print(f"   + Miss critical: {ep2.reward:.2f}")
        print(f"   + False critical: {ep3.reward:.2f}")
        print(f"   + Lower trust: {ep4.reward:.2f}")


def test_episode_recording():
    """Test episode recording and persistence."""
    from backend.training.deep_rl_agent import DeepRLAgent

    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)

        # Create agent and record episodes
        agent1 = DeepRLAgent(checkpoint_dir=tmpdir)
        
        for i in range(5):
            agent1.record_outcome(
                f"CVE-2024-{i:04d}",
                "CRITICAL",
                "HIGH",
                "nvd_update",
            )

        # Check stats
        stats = agent1.get_episode_stats()
        assert stats["total"] == 5
        assert stats["by_source"]["nvd_update"] == 5

        # Create new agent and verify episodes loaded
        agent2 = DeepRLAgent(checkpoint_dir=tmpdir)
        stats2 = agent2.get_episode_stats()
        assert stats2["total"] == 5

        print(f"   + Episode recording working")
        print(f"   + Episodes persisted: {stats2['total']}")


def test_sample_weights():
    """Test sample weight computation based on RL history."""
    from backend.training.deep_rl_agent import DeepRLAgent

    with tempfile.TemporaryDirectory() as tmpdir:
        agent = DeepRLAgent(checkpoint_dir=Path(tmpdir))

        # Record some episodes
        agent.record_outcome("CVE-2024-0001", "CRITICAL", "CRITICAL", "cisa_kev")  # Good
        agent.record_outcome("CVE-2024-0002", "LOW", "CRITICAL", "cisa_kev")       # Bad

        # Get weights
        cve_ids = ["CVE-2024-0001", "CVE-2024-0002", "CVE-2024-0003"]
        weights = agent.get_sample_weights(cve_ids)

        assert len(weights) == 3
        assert weights[0] > weights[1]  # Good prediction gets higher weight
        assert weights[2] == 1.0  # Unknown CVE gets default weight

        print(f"   + Sample weights working")
        print(f"   + Good prediction weight: {weights[0]:.2f}")
        print(f"   + Bad prediction weight: {weights[1]:.2f}")
        print(f"   + Unknown CVE weight: {weights[2]:.2f}")


def test_sklearn_integration():
    """Test full sklearn integration with RL agent."""
    try:
        from sklearn.preprocessing import StandardScaler
    except ImportError:
        pytest.skip("scikit-learn not installed")

    from backend.training.deep_rl_agent import DeepRLAgent

    with tempfile.TemporaryDirectory() as tmpdir:
        agent = DeepRLAgent(checkpoint_dir=Path(tmpdir))

        # Fit sklearn augmenter
        X_train = np.random.rand(100, 267).astype(np.float32)
        agent.fit_sklearn(X_train)

        # Augment features
        X_test = np.random.rand(10, 267).astype(np.float32)
        X_augmented = agent.augment_features(X_test)

        assert X_augmented.shape[0] == X_test.shape[0]
        assert X_augmented.shape[1] > X_test.shape[1]

        # Test save/load
        agent2 = DeepRLAgent(checkpoint_dir=Path(tmpdir))
        agent2.load_sklearn_augmenter()
        X_augmented2 = agent2.augment_features(X_test)

        np.testing.assert_array_almost_equal(X_augmented, X_augmented2, decimal=5)

        print(f"   + sklearn integration working")
        print(f"   + Features: {X_test.shape[1]} → {X_augmented.shape[1]}")


def test_episode_stats():
    """Test episode statistics computation."""
    from backend.training.deep_rl_agent import DeepRLAgent

    with tempfile.TemporaryDirectory() as tmpdir:
        agent = DeepRLAgent(checkpoint_dir=Path(tmpdir))

        # Record diverse episodes
        agent.record_outcome("CVE-2024-0001", "CRITICAL", "CRITICAL", "cisa_kev")
        agent.record_outcome("CVE-2024-0002", "HIGH", "HIGH", "nvd_update")
        agent.record_outcome("CVE-2024-0003", "LOW", "CRITICAL", "vendor_confirm")
        agent.record_outcome("CVE-2024-0004", "MEDIUM", "MEDIUM", "label")

        stats = agent.get_episode_stats()

        assert stats["total"] == 4
        assert stats["positive"] >= 2  # At least 2 exact matches
        assert "by_source" in stats
        assert "by_severity" in stats
        assert "normalizer_stats" in stats

        print(f"   + Episode stats working")
        print(f"   + Total episodes: {stats['total']}")
        print(f"   + Mean reward: {stats['mean_reward']:.2f}")
        print(f"   + Positive: {stats['positive']}, Negative: {stats['negative']}")


if __name__ == "__main__":
    print("Running Deep RL Agent tests...")
    print("=" * 70)

    tests = [
        ("Imports", test_deep_rl_imports),
        ("GRPO reward normalizer", test_grpo_reward_normalizer),
        ("sklearn feature augmenter", test_sklearn_feature_augmenter),
        ("sklearn save/load", test_sklearn_augmenter_save_load),
        ("Reward computation", test_reward_computation),
        ("Episode recording", test_episode_recording),
        ("Sample weights", test_sample_weights),
        ("sklearn integration", test_sklearn_integration),
        ("Episode stats", test_episode_stats),
    ]

    passed = 0
    failed = 0

    for name, test_func in tests:
        print(f"\nTesting: {name}")
        print("-" * 70)
        try:
            test_func()
            print(f"PASS: {name}")
            passed += 1
        except Exception as e:
            print(f"FAIL: {name}")
            print(f"   Error: {e}")
            failed += 1

    print("\n" + "=" * 70)
    print(f"Results: {passed} passed, {failed} failed")

    if failed == 0:
        print("All Deep RL Agent tests passed!")
    else:
        print(f"{failed} test(s) failed")

