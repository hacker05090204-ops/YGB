"""
Comprehensive test for Phases 0, 1, and 2.
Run this to verify all components are working correctly.
"""

import os
import sys
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

print("="*70)
print("YBG PHASES 0-2 COMPREHENSIVE TEST")
print("="*70)

# Test results tracker
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
        print(f"✅ PASS: {phase_name}")
        tests_passed += 1
        test_results.append((phase_name, "PASS", None))
        return True
    except Exception as e:
        print(f"❌ FAIL: {phase_name}")
        print(f"   Error: {e}")
        tests_failed += 1
        test_results.append((phase_name, "FAIL", str(e)))
        return False


# ============================================================================
# PHASE 0 TESTS — BARE EXCEPT VIOLATIONS
# ============================================================================

def test_phase0_no_bare_excepts():
    """Verify no bare except: statements exist."""
    import re
    
    violations = []
    
    # Search in key directories
    for directory in ['backend', 'impl_v1', 'scripts']:
        dir_path = Path(directory)
        if not dir_path.exists():
            continue
        
        for py_file in dir_path.rglob('*.py'):
            # Skip test files themselves
            if 'test_' in py_file.name:
                continue
                
            try:
                content = py_file.read_text(encoding='utf-8', errors='ignore')
                lines = content.split('\n')
                
                for line_num, line in enumerate(lines, 1):
                    stripped = line.strip()
                    
                    # Skip comments and docstrings
                    if stripped.startswith('#') or stripped.startswith('"""') or stripped.startswith("'''"):
                        continue
                    
                    # Check for bare except: (actual code, not in strings)
                    if 'except:' in line and not '#' in line.split('except:')[0]:
                        # Make sure it's actual code
                        if stripped.endswith('except:') or re.search(r'except:\s*$', line):
                            violations.append(f"{py_file}:{line_num}: {line.strip()}")
                    
                    # Check for except Exception: pass (but not in comments)
                    if re.search(r'except\s+Exception:\s*pass\s*$', line) and not stripped.startswith('#'):
                        violations.append(f"{py_file}:{line_num}: {line.strip()}")
                        
            except Exception as e:
                # Skip files that can't be read
                continue
    
    if violations:
        print(f"   Found {len(violations)} bare except violations:")
        for v in violations[:5]:  # Show first 5
            print(f"   - {v}")
        raise AssertionError(f"Found {len(violations)} bare except violations")
    
    print("   ✓ No bare except violations found in backend/, impl_v1/, scripts/")


# ============================================================================
# PHASE 1 TESTS — MOE WIRING
# ============================================================================

def test_phase1_moe_imports():
    """Verify MoE can be imported."""
    from impl_v1.phase49.moe import MoEClassifier, MoEConfig
    print("   ✓ MoE imports successfully")


def test_phase1_moe_model_build():
    """Verify MoE model can be built."""
    os.environ['YGB_USE_MOE'] = 'true'
    
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
    params = sum(p.numel() for p in model.parameters())
    
    print(f"   ✓ Model built: {type(model).__name__}")
    print(f"   ✓ Total parameters: {params:,} ({params/1e6:.2f}M)")
    
    if params < 100_000_000:
        raise AssertionError(f"Model has only {params:,} parameters (need > 100M)")
    
    print(f"   ✓ Model exceeds 100M parameter requirement")


def test_phase1_moe_forward_pass():
    """Verify MoE model can perform forward pass."""
    import torch
    os.environ['YGB_USE_MOE'] = 'true'
    
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
    model.eval()
    
    # Test forward pass
    x = torch.randn(4, 267)  # batch of 4 samples
    with torch.no_grad():
        output = model(x)
    
    if output.shape != (4, 5):
        raise AssertionError(f"Expected output shape (4, 5), got {output.shape}")
    
    print(f"   ✓ Forward pass successful: input {x.shape} → output {output.shape}")


def test_phase1_training_controller_integration():
    """Verify training_controller.py has MoE integration."""
    tc_path = Path('training_controller.py')
    
    if not tc_path.exists():
        raise FileNotFoundError("training_controller.py not found")
    
    content = tc_path.read_text(encoding='utf-8', errors='ignore')
    
    required_refs = ['MoEClassifier', 'YGB_USE_MOE', 'N_EXPERTS']
    missing = [ref for ref in required_refs if ref not in content]
    
    if missing:
        raise AssertionError(f"Missing MoE references in training_controller.py: {missing}")
    
    print(f"   ✓ training_controller.py has MoE integration")


# ============================================================================
# PHASE 2 TESTS — DEVICE MANAGER
# ============================================================================

def test_phase2_device_manager_import():
    """Verify device_manager can be imported."""
    from scripts.device_manager import get_config, print_config, DeviceConfig
    print("   ✓ device_manager imports successfully")


def test_phase2_device_detection():
    """Verify device manager detects hardware."""
    from scripts.device_manager import get_config
    
    config = get_config()
    
    print(f"   ✓ Detected device: {config.device_name}")
    print(f"   ✓ Device type: {config.device}")
    print(f"   ✓ VRAM: {config.vram_gb:.1f}GB")
    print(f"   ✓ Batch size: {config.batch_size}")
    print(f"   ✓ Precision: {config.precision}")
    print(f"   ✓ Cloud platform: {config.is_colab}")
    
    # Verify config is valid
    assert config.device in ['cuda', 'cpu', 'mps'], f"Invalid device: {config.device}"
    assert config.batch_size > 0, "Batch size must be positive"
    assert config.precision in ['bf16', 'fp16', 'fp32'], f"Invalid precision: {config.precision}"


def test_phase2_colab_setup_exists():
    """Verify Colab setup script exists."""
    colab_path = Path('scripts/colab_setup.py')
    
    if not colab_path.exists():
        raise FileNotFoundError("scripts/colab_setup.py not found")
    
    content = colab_path.read_text()
    
    required_elements = ['COLAB_SETUP_CODE', 'YGB_USE_MOE', 'get_config']
    missing = [elem for elem in required_elements if elem not in content]
    
    if missing:
        raise AssertionError(f"Missing elements in colab_setup.py: {missing}")
    
    print(f"   ✓ Colab setup script exists and is valid")


# ============================================================================
# RUN ALL TESTS
# ============================================================================

if __name__ == "__main__":
    print("\nStarting comprehensive test suite...\n")
    
    # Phase 0 tests
    test_phase("Phase 0: No bare except violations", test_phase0_no_bare_excepts)
    
    # Phase 1 tests
    test_phase("Phase 1: MoE imports", test_phase1_moe_imports)
    test_phase("Phase 1: MoE model build", test_phase1_moe_model_build)
    test_phase("Phase 1: MoE forward pass", test_phase1_moe_forward_pass)
    test_phase("Phase 1: Training controller integration", test_phase1_training_controller_integration)
    
    # Phase 2 tests
    test_phase("Phase 2: Device manager import", test_phase2_device_manager_import)
    test_phase("Phase 2: Device detection", test_phase2_device_detection)
    test_phase("Phase 2: Colab setup exists", test_phase2_colab_setup_exists)
    
    # Summary
    print("\n" + "="*70)
    print("TEST SUMMARY")
    print("="*70)
    
    for test_name, status, error in test_results:
        symbol = "✅" if status == "PASS" else "❌"
        print(f"{symbol} {test_name}: {status}")
        if error:
            print(f"   Error: {error[:100]}")
    
    print(f"\nTotal: {tests_passed + tests_failed} tests")
    print(f"Passed: {tests_passed}")
    print(f"Failed: {tests_failed}")
    
    if tests_failed == 0:
        print("\n🎉 ALL TESTS PASSED! Phases 0-2 are fully operational.")
        sys.exit(0)
    else:
        print(f"\n⚠️  {tests_failed} test(s) failed. Please review errors above.")
        sys.exit(1)
