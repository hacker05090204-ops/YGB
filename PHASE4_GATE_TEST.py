"""
PHASE 4 GATE TEST — Deep RL Agent
Tests GRPO rewards, sklearn augmentation, episode recording
"""

import sys
import tempfile
from pathlib import Path
import numpy as np

print("="*70)
print("PHASE 4 GATE TEST — Deep RL Agent")
print("="*70)

# Test 1: Import
print("\n[TEST 1] Deep RL Agent Import")
try:
    from backend.training.deep_rl_agent import (
        DeepRLAgent,
        GRPORewardNormalizer,
        SklearnFeatureAugmenter,
        RLEpisode,
    )
    print("  PASS: All components imported")
    test1_pass = True
except ImportError as e:
    print(f"  FAIL: {e}")
    test1_pass = False

# Test 2: GRPO Reward Normalization
print("\n[TEST 2] GRPO Reward Normalization")
try:
    from backend.training.deep_rl_agent import GRPORewardNormalizer
    
    normalizer = GRPORewardNormalizer(group_size=4)
    
    # Add rewards
    rewards = [1.0, 0.5, -0.2, 0.8, 1.2, -0.5, 0.3, 0.9]
    advantages = [normalizer.add(r) for r in rewards]
    
    stats = normalizer.get_stats()
    
    print(f"  Rewards: {rewards[:4]}")
    print(f"  Advantages: {[f'{a:.2f}' for a in advantages[:4]]}")
    print(f"  Mean: {stats['mean']:.2f}, Std: {stats['std']:.2f}")
    
    if len(advantages) == len(rewards) and stats['count'] > 0:
        print("  PASS: GRPO normalization working")
        test2_pass = True
    else:
        print("  FAIL: Unexpected output")
        test2_pass = False
except Exception as e:
    print(f"  FAIL: {e}")
    test2_pass = False

# Test 3: Sklearn Feature Augmentation
print("\n[TEST 3] Sklearn Feature Augmentation")
try:
    from backend.training.deep_rl_agent import SklearnFeatureAugmenter
    
    augmenter = SklearnFeatureAugmenter()
    
    # Create synthetic training data
    X_train = np.random.randn(100, 50).astype(np.float32)
    
    # Fit
    augmenter.fit(X_train)
    
    if not augmenter.is_fitted:
        print("  FAIL: Augmenter not fitted")
        test3_pass = False
    else:
        # Augment
        X_test = np.random.randn(10, 50).astype(np.float32)
        X_aug = augmenter.augment(X_test)
        
        added_features = augmenter.get_feature_count()
        
        print(f"  Original features: {X_test.shape[1]}")
        print(f"  Augmented features: {X_aug.shape[1]}")
        print(f"  Added features: {added_features}")
        
        if X_aug.shape[1] > X_test.shape[1]:
            print("  PASS: Feature augmentation working")
            test3_pass = True
        else:
            print("  FAIL: No features added")
            test3_pass = False
            
except ImportError:
    print("  SKIP: scikit-learn not installed")
    test3_pass = True  # Don't fail if optional dep missing
except Exception as e:
    print(f"  FAIL: {e}")
    test3_pass = False

# Test 4: Episode Recording
print("\n[TEST 4] Episode Recording")
try:
    from backend.training.deep_rl_agent import DeepRLAgent
    
    with tempfile.TemporaryDirectory() as tmpdir:
        agent = DeepRLAgent(checkpoint_dir=Path(tmpdir))
        
        # Record outcomes
        ep1 = agent.record_outcome("CVE-2024-0001", "CRITICAL", "CRITICAL", "cisa_kev")
        ep2 = agent.record_outcome("CVE-2024-0002", "HIGH", "MEDIUM", "nvd_update")
        ep3 = agent.record_outcome("CVE-2024-0003", "LOW", "CRITICAL", "label")
        
        print(f"  Episode 1: reward={ep1.reward:.2f}, advantage={ep1.advantage:.2f}")
        print(f"  Episode 2: reward={ep2.reward:.2f}, advantage={ep2.advantage:.2f}")
        print(f"  Episode 3: reward={ep3.reward:.2f}, advantage={ep3.advantage:.2f}")
        
        stats = agent.get_episode_stats()
        print(f"  Total episodes: {stats['total']}")
        print(f"  Mean reward: {stats['mean_reward']:.2f}")
        
        if stats['total'] == 3 and ep1.reward > 0 and ep3.reward < 0:
            print("  PASS: Episode recording working")
            test4_pass = True
        else:
            print("  FAIL: Unexpected episode stats")
            test4_pass = False
            
except Exception as e:
    print(f"  FAIL: {e}")
    test4_pass = False

# Test 5: Sample Weighting
print("\n[TEST 5] Sample Weighting")
try:
    from backend.training.deep_rl_agent import DeepRLAgent
    
    with tempfile.TemporaryDirectory() as tmpdir:
        agent = DeepRLAgent(checkpoint_dir=Path(tmpdir))
        
        # Record some outcomes
        agent.record_outcome("CVE-2024-0001", "CRITICAL", "CRITICAL", "cisa_kev")  # Good
        agent.record_outcome("CVE-2024-0002", "LOW", "CRITICAL", "cisa_kev")      # Bad
        agent.record_outcome("CVE-2024-0003", "HIGH", "HIGH", "nvd_update")       # Good
        
        # Get weights
        cve_ids = ["CVE-2024-0001", "CVE-2024-0002", "CVE-2024-0003", "CVE-2024-9999"]
        weights = agent.get_sample_weights(cve_ids)
        
        print(f"  Weights: {[f'{w:.2f}' for w in weights]}")
        print(f"  Good prediction weight: {weights[0]:.2f}")
        print(f"  Bad prediction weight: {weights[1]:.2f}")
        print(f"  Unknown CVE weight: {weights[3]:.2f}")
        
        # Good predictions should have higher weight than bad
        if weights[0] > weights[1] and weights[3] == 1.0:
            print("  PASS: Sample weighting working")
            test5_pass = True
        else:
            print("  FAIL: Unexpected weights")
            test5_pass = False
            
except Exception as e:
    print(f"  FAIL: {e}")
    test5_pass = False

# Test 6: Persistence
print("\n[TEST 6] Episode Persistence")
try:
    from backend.training.deep_rl_agent import DeepRLAgent
    
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)
        
        # Create agent and record episodes
        agent1 = DeepRLAgent(checkpoint_dir=tmpdir)
        agent1.record_outcome("CVE-2024-0001", "CRITICAL", "CRITICAL", "cisa_kev")
        agent1.record_outcome("CVE-2024-0002", "HIGH", "MEDIUM", "nvd_update")
        
        stats1 = agent1.get_episode_stats()
        
        # Create new agent with same checkpoint dir
        agent2 = DeepRLAgent(checkpoint_dir=tmpdir)
        stats2 = agent2.get_episode_stats()
        
        print(f"  Agent 1 episodes: {stats1['total']}")
        print(f"  Agent 2 episodes: {stats2['total']}")
        
        if stats1['total'] == stats2['total'] == 2:
            print("  PASS: Episode persistence working")
            test6_pass = True
        else:
            print("  FAIL: Episodes not persisted")
            test6_pass = False
            
except Exception as e:
    print(f"  FAIL: {e}")
    test6_pass = False

# Final verdict
print("\n" + "="*70)
print("PHASE 4 GATE TEST RESULTS")
print("="*70)

all_tests = [test1_pass, test2_pass, test3_pass, test4_pass, test5_pass, test6_pass]
passed = sum(all_tests)
total_tests = len(all_tests)

print(f"Tests passed: {passed}/{total_tests}")

if all(all_tests):
    print("\nPHASE 4 GATE: GREEN — All tests passed")
    print("- Deep RL agent imports successfully")
    print("- GRPO reward normalization working")
    print("- Sklearn feature augmentation working")
    print("- Episode recording working")
    print("- Sample weighting working")
    print("- Episode persistence working")
    print("\nREADY TO PROCEED TO PHASE 5")
    sys.exit(0)
else:
    print("\nPHASE 4 GATE: RED — Some tests failed")
    print("NOT DONE - FIX ISSUES BEFORE PROCEEDING")
    sys.exit(1)
