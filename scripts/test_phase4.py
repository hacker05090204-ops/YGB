"""
Phase 4 Test: Deep RL + sklearn Integration
Verifies reinforcement learning feedback loops and feature augmentation.
"""

import sys
import tempfile
from pathlib import Path
import numpy as np

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

print("="*70)
print("PHASE 4: DEEP RL + SKLEARN INTEGRATION TEST")
print("="*70)

tests_passed = 0
tests_failed = 0
test_results = []


def test_phase(phase_name, test_func):
    """Run a test and track results."""
    global tests_passed, tests_failed
    print(f"\n{'='*70}")
    print(f"Testing: {phase_name}")
    print(f"{'='*70}")
    try:
        test_func()
        print(f"PASS: {phase_name}")
        tests_passed += 1
        test_results.append((phase_name, "PASS", None))
        return True
    except Exception as e:
        print(f"FAIL: {phase_name}")
        print(f"   Error: {e}")
        tests_failed += 1
        test_results.append((phase_name, "FAIL", str(e)))
        return False


# ============================================================================
# PHASE 4 TESTS
# ============================================================================

def test_deep_rl_imports():
    """Verify Deep RL agent can be imported."""
    from backend.training.deep_rl_agent import (
        DeepRLAgent,
        GRPORewardNormalizer,
        SklearnFeatureAugmenter,
        RLEpisode,
    )
    print("   + DeepRLAgent imported")
    print("   + GRPORewardNormalizer imported")
    print("   + SklearnFeatureAugmenter imported")
    print("   + RLEpisode imported")


def test_grpo_normalization():
    """Test GRPO reward normalization."""
    from backend.training.deep_rl_agent import GRPORewardNormalizer

    normalizer = GRPORewardNormalizer(group_size=8)

    # Add rewards
    rewards = [1.0, 0.8, 0.5, -0.5, -0.8, -1.0, 0.3, -0.3]
    advantages = []

    for reward in rewards:
        advantage = normalizer.add(reward)
        advantages.append(advantage)

    # Check that normalization is working
    stats = normalizer.get_stats()
    
    print(f"   + Processed {len(rewards)} rewards")
    print(f"   + Mean reward: {stats['mean']:.2f}")
    print(f"   + Std reward: {stats['std']:.2f}")
    print(f"   + Advantages computed: {len(advantages)}")

    if stats['count'] != len(rewards):
        raise AssertionError(f"Expected {len(rewards)} rewards, got {stats['count']}")


def test_reward_computation():
    """Test reward computation for different scenarios."""
    from backend.training.deep_rl_agent import DeepRLAgent

    with tempfile.TemporaryDirectory() as tmpdir:
        agent = DeepRLAgent(checkpoint_dir=Path(tmpdir))

        # Test exact match
        ep1 = agent.record_outcome("CVE-2024-0001", "CRITICAL", "CRITICAL", "cisa_kev")
        
        # Test miss
        ep2 = agent.record_outcome("CVE-2024-0002", "LOW", "CRITICAL", "cisa_kev")
        
        # Test false alarm
        ep3 = agent.record_outcome("CVE-2024-0003", "CRITICAL", "LOW", "cisa_kev")

        print(f"   + Exact match reward: {ep1.reward:.2f}")
        print(f"   + Miss critical reward: {ep2.reward:.2f}")
        print(f"   + False critical reward: {ep3.reward:.2f}")

        # Verify reward logic
        if ep1.reward <= 0:
            raise AssertionError("Exact match should have positive reward")
        if ep2.reward >= 0:
            raise AssertionError("Missing critical should have negative reward")
        if ep3.reward >= 0:
            raise AssertionError("False critical should have negative reward")


def test_sklearn_feature_augmentation():
    """Test sklearn feature augmentation."""
    try:
        from sklearn.preprocessing import StandardScaler
    except ImportError:
        print("   ! Skipping: scikit-learn not installed")
        return

    from backend.training.deep_rl_agent import SklearnFeatureAugmenter

    augmenter = SklearnFeatureAugmenter()

    # Create training data
    X_train = np.random.rand(100, 267).astype(np.float32)
    
    # Fit
    augmenter.fit(X_train)
    
    if not augmenter.is_fitted:
        raise AssertionError("Augmenter should be fitted")

    # Augment
    X_test = np.random.rand(10, 267).astype(np.float32)
    X_augmented = augmenter.augment(X_test)

    additional_features = augmenter.get_feature_count()

    print(f"   + Original features: {X_test.shape[1]}")
    print(f"   + Augmented features: {X_augmented.shape[1]}")
    print(f"   + Additional features: {additional_features}")

    if X_augmented.shape[1] <= X_test.shape[1]:
        raise AssertionError("Augmentation should add features")


def test_episode_persistence():
    """Test episode recording and persistence."""
    from backend.training.deep_rl_agent import DeepRLAgent

    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)

        # Create agent and record episodes
        agent1 = DeepRLAgent(checkpoint_dir=tmpdir)
        
        for i in range(10):
            agent1.record_outcome(
                f"CVE-2024-{i:04d}",
                "HIGH" if i % 2 == 0 else "MEDIUM",
                "HIGH",
                "nvd_update",
            )

        stats1 = agent1.get_episode_stats()

        # Create new agent and verify episodes loaded
        agent2 = DeepRLAgent(checkpoint_dir=tmpdir)
        stats2 = agent2.get_episode_stats()

        print(f"   + Episodes recorded: {stats1['total']}")
        print(f"   + Episodes loaded: {stats2['total']}")
        print(f"   + Mean reward: {stats2['mean_reward']:.2f}")

        if stats1['total'] != stats2['total']:
            raise AssertionError("Episodes not persisted correctly")


def test_sample_weighting():
    """Test sample weight computation based on RL history."""
    from backend.training.deep_rl_agent import DeepRLAgent

    with tempfile.TemporaryDirectory() as tmpdir:
        agent = DeepRLAgent(checkpoint_dir=Path(tmpdir))

        # Record good and bad predictions
        agent.record_outcome("CVE-2024-0001", "CRITICAL", "CRITICAL", "cisa_kev")  # Good
        agent.record_outcome("CVE-2024-0002", "LOW", "CRITICAL", "cisa_kev")       # Bad
        agent.record_outcome("CVE-2024-0003", "HIGH", "HIGH", "nvd_update")        # Good

        # Get weights
        cve_ids = ["CVE-2024-0001", "CVE-2024-0002", "CVE-2024-0003", "CVE-2024-9999"]
        weights = agent.get_sample_weights(cve_ids)

        print(f"   + Sample weights computed: {len(weights)}")
        print(f"   + Good prediction weight: {weights[0]:.2f}")
        print(f"   + Bad prediction weight: {weights[1]:.2f}")
        print(f"   + Unknown CVE weight: {weights[3]:.2f}")

        # Verify weight logic
        if weights[0] <= weights[1]:
            raise AssertionError("Good predictions should have higher weight")
        if weights[3] != 1.0:
            raise AssertionError("Unknown CVEs should have default weight")


def test_full_integration():
    """Test full Deep RL + sklearn integration."""
    try:
        from sklearn.preprocessing import StandardScaler
    except ImportError:
        print("   ! Skipping: scikit-learn not installed")
        return

    from backend.training.deep_rl_agent import DeepRLAgent

    with tempfile.TemporaryDirectory() as tmpdir:
        agent = DeepRLAgent(checkpoint_dir=Path(tmpdir))

        # Fit sklearn augmenter
        X_train = np.random.rand(100, 267).astype(np.float32)
        agent.fit_sklearn(X_train)

        # Record some episodes
        for i in range(5):
            agent.record_outcome(
                f"CVE-2024-{i:04d}",
                "CRITICAL" if i < 3 else "HIGH",
                "CRITICAL",
                "cisa_kev",
            )

        # Get stats
        stats = agent.get_episode_stats()

        # Augment features
        X_test = np.random.rand(10, 267).astype(np.float32)
        X_augmented = agent.augment_features(X_test)

        # Get sample weights
        cve_ids = [f"CVE-2024-{i:04d}" for i in range(5)]
        weights = agent.get_sample_weights(cve_ids)

        print(f"   + Episodes recorded: {stats['total']}")
        print(f"   + Features augmented: {X_test.shape[1]} -> {X_augmented.shape[1]}")
        print(f"   + Sample weights: min={weights.min():.2f}, max={weights.max():.2f}")

        if stats['total'] != 5:
            raise AssertionError("Expected 5 episodes")
        if X_augmented.shape[1] <= X_test.shape[1]:
            raise AssertionError("Features should be augmented")


# ============================================================================
# RUN ALL TESTS
# ============================================================================

if __name__ == "__main__":
    print("\nStarting Phase 4 test suite...\n")

    # Run tests
    test_phase("Deep RL imports", test_deep_rl_imports)
    test_phase("GRPO normalization", test_grpo_normalization)
    test_phase("Reward computation", test_reward_computation)
    test_phase("sklearn feature augmentation", test_sklearn_feature_augmentation)
    test_phase("Episode persistence", test_episode_persistence)
    test_phase("Sample weighting", test_sample_weighting)
    test_phase("Full integration", test_full_integration)

    # Summary
    print("\n" + "="*70)
    print("TEST SUMMARY")
    print("="*70)

    for test_name, status, error in test_results:
        symbol = "PASS" if status == "PASS" else "FAIL"
        print(f"{symbol}: {test_name}")
        if error:
            print(f"   Error: {error[:100]}")

    print(f"\nTotal: {tests_passed + tests_failed} tests")
    print(f"Passed: {tests_passed}")
    print(f"Failed: {tests_failed}")

    if tests_failed == 0:
        print("\nPHASE 4 COMPLETE! Deep RL + sklearn integration is operational.")
        print("\nKey Achievements:")
        print("  * GRPO reward normalization working")
        print("  * Reward computation verified")
        print("  * sklearn feature augmentation functional")
        print("  * Episode persistence confirmed")
        print("  * Sample weighting operational")
        print("  * Full integration tested")
        sys.exit(0)
    else:
        print(f"\n{tests_failed} test(s) failed. Please review errors above.")
        sys.exit(1)
