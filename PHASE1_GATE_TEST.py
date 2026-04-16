"""
PHASE 1 GATE TEST — MoE Architecture Verification
Orchestrator requirement: 23 experts × 130M params = ~3B total
"""

import sys
import torch

print("="*70)
print("PHASE 1 GATE TEST — MoE Architecture")
print("="*70)

# Test 1: SimpleMoEClassifier parameter count
print("\n[TEST 1] SimpleMoEClassifier Parameter Count")
try:
    from impl_v1.phase49.moe import SimpleMoEClassifier, count_params
    
    model = SimpleMoEClassifier(
        n_experts=23,
        input_dim=267,
        hidden_dim=2048,
        n_layers=6,
        n_heads=16,
        n_classes=5,
        top_k=2
    )
    
    total = count_params(model)
    per_expert = count_params(model.experts[0])
    router = count_params(model.router)
    
    print(f"  Total params: {total:,} ({total/1e6:.2f}M)")
    print(f"  Per expert: {per_expert:,} ({per_expert/1e6:.2f}M)")
    print(f"  Router params: {router:,} ({router/1e6:.2f}M)")
    print(f"  Target: 130M per expert")
    
    if per_expert >= 130_000_000:
        print("  ✓ PASS: Exceeds 130M per expert requirement")
        test1_pass = True
    else:
        print(f"  ✗ FAIL: Only {per_expert/1e6:.2f}M per expert")
        test1_pass = False
except Exception as e:
    print(f"  ✗ FAIL: {e}")
    test1_pass = False

# Test 2: Verify exports
print("\n[TEST 2] MoE Module Exports")
try:
    from impl_v1.phase49.moe import (
        SimpleMoEClassifier,
        SimpleExpert130M,
        SimpleRouter,
        count_params,
        MoEClassifier,
        EXPERT_FIELDS
    )
    print("  ✓ PASS: All required exports available")
    print(f"  Expert fields: {len(EXPERT_FIELDS)} registered")
    test2_pass = True
except ImportError as e:
    print(f"  ✗ FAIL: Missing export - {e}")
    test2_pass = False

# Test 3: Verify train_single_expert function
print("\n[TEST 3] train_single_expert() Function")
try:
    from training_controller import train_single_expert
    import inspect
    sig = inspect.signature(train_single_expert)
    params = list(sig.parameters.keys())
    print(f"  Function signature: {params}")
    if 'expert_id' in params and 'field_name' in params:
        print("  ✓ PASS: train_single_expert() properly defined")
        test3_pass = True
    else:
        print("  ✗ FAIL: Missing required parameters")
        test3_pass = False
except Exception as e:
    print(f"  ✗ FAIL: {e}")
    test3_pass = False

# Test 4: Forward pass smoke test
print("\n[TEST 4] Forward Pass Smoke Test")
try:
    from impl_v1.phase49.moe import SimpleMoEClassifier
    
    model = SimpleMoEClassifier(
        n_experts=23,
        input_dim=267,
        hidden_dim=512,  # smaller for speed
        n_layers=2,
        n_heads=8,
        n_classes=5,
        top_k=2
    )
    
    # Test forward pass
    x = torch.randn(4, 267)
    with torch.no_grad():
        output = model(x)
    
    if output.shape == (4, 5):
        print(f"  Input shape: {x.shape}")
        print(f"  Output shape: {output.shape}")
        print("  ✓ PASS: Forward pass successful")
        test4_pass = True
    else:
        print(f"  ✗ FAIL: Wrong output shape {output.shape}")
        test4_pass = False
except Exception as e:
    print(f"  ✗ FAIL: {e}")
    test4_pass = False

# Test 5: Verify 100M gate (existing requirement)
print("\n[TEST 5] 100M Parameter Gate (Existing)")
try:
    from impl_v1.phase49.moe import MoEClassifier, MoEConfig
    
    config = MoEConfig(
        d_model=256,
        n_experts=23,
        top_k=2,
        expert_hidden_mult=2,
        dropout=0.3,
        gate_noise=1.0,
        aux_loss_coeff=0.01,
    )
    
    model = MoEClassifier(config, input_dim=267, output_dim=5)
    total = sum(p.numel() for p in model.parameters())
    
    print(f"  Existing MoEClassifier: {total:,} ({total/1e6:.2f}M)")
    
    if total > 100_000_000:
        print("  ✓ PASS: Exceeds 100M gate")
        test5_pass = True
    else:
        print(f"  ✗ FAIL: Only {total/1e6:.2f}M")
        test5_pass = False
except Exception as e:
    print(f"  ✗ FAIL: {e}")
    test5_pass = False

# Final verdict
print("\n" + "="*70)
print("PHASE 1 GATE TEST RESULTS")
print("="*70)

all_tests = [test1_pass, test2_pass, test3_pass, test4_pass, test5_pass]
passed = sum(all_tests)
total_tests = len(all_tests)

print(f"Tests passed: {passed}/{total_tests}")

if all(all_tests):
    print("\n🟢 PHASE 1 GATE: GREEN — All tests passed")
    print("✓ SimpleMoEClassifier meets 130M per expert requirement")
    print("✓ All exports available")
    print("✓ train_single_expert() function ready")
    print("✓ Forward pass working")
    print("✓ Existing MoEClassifier passes 100M gate")
    print("\nREADY TO PROCEED TO PHASE 2")
    sys.exit(0)
else:
    print("\n🔴 PHASE 1 GATE: RED — Some tests failed")
    print("FIX ISSUES BEFORE PROCEEDING")
    sys.exit(1)
