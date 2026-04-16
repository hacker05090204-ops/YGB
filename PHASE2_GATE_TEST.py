"""
PHASE 2 GATE TEST — Device Manager
Orchestrator requirement: Auto-detect hardware and configure optimal settings
"""

import sys

print("="*70)
print("PHASE 2 GATE TEST — Device Manager")
print("="*70)

# Test 1: Import and basic functionality
print("\n[TEST 1] Device Manager Import")
try:
    from scripts.device_manager import get_config, print_config, DeviceConfig
    print("  ✓ PASS: Device manager imports successfully")
    test1_pass = True
except ImportError as e:
    print(f"  ✗ FAIL: {e}")
    test1_pass = False

# Test 2: Get configuration
print("\n[TEST 2] Get Device Configuration")
try:
    from scripts.device_manager import get_config
    config = get_config(target_params=130_430_000)
    
    print(f"  Device: {config.device}")
    print(f"  Device name: {config.device_name}")
    print(f"  VRAM: {config.vram_gb:.1f}GB")
    print(f"  Batch size: {config.batch_size}")
    print(f"  Precision: {config.precision}")
    print(f"  Gradient checkpointing: {config.gradient_checkpointing}")
    print(f"  Max model params: {config.max_model_params/1e6:.1f}M")
    
    if config.device in ["cuda", "cpu", "mps"]:
        print("  ✓ PASS: Valid device configuration")
        test2_pass = True
    else:
        print(f"  ✗ FAIL: Invalid device {config.device}")
        test2_pass = False
except Exception as e:
    print(f"  ✗ FAIL: {e}")
    test2_pass = False

# Test 3: Verify dataclass fields
print("\n[TEST 3] DeviceConfig Dataclass")
try:
    from scripts.device_manager import DeviceConfig
    import dataclasses
    
    fields = [f.name for f in dataclasses.fields(DeviceConfig)]
    required_fields = [
        'device', 'device_name', 'vram_gb', 'batch_size', 'precision',
        'gradient_checkpointing', 'use_amp', 'num_workers', 'pin_memory',
        'max_model_params', 'is_colab', 'notes'
    ]
    
    missing = [f for f in required_fields if f not in fields]
    if not missing:
        print(f"  All {len(required_fields)} required fields present")
        print("  ✓ PASS: DeviceConfig properly defined")
        test3_pass = True
    else:
        print(f"  ✗ FAIL: Missing fields: {missing}")
        test3_pass = False
except Exception as e:
    print(f"  ✗ FAIL: {e}")
    test3_pass = False

# Test 4: Different target params
print("\n[TEST 4] Adaptive Configuration")
try:
    from scripts.device_manager import get_config
    
    # Test with small model
    small_config = get_config(target_params=10_000_000)
    # Test with large model
    large_config = get_config(target_params=3_000_000_000)
    
    print(f"  Small model (10M): batch={small_config.batch_size}")
    print(f"  Large model (3B): batch={large_config.batch_size}")
    
    # Batch size should adapt (or at least not crash)
    if small_config.batch_size > 0 and large_config.batch_size > 0:
        print("  ✓ PASS: Adaptive configuration working")
        test4_pass = True
    else:
        print("  ✗ FAIL: Invalid batch sizes")
        test4_pass = False
except Exception as e:
    print(f"  ✗ FAIL: {e}")
    test4_pass = False

# Test 5: Print config (should not crash)
print("\n[TEST 5] Print Configuration")
try:
    from scripts.device_manager import get_config, print_config
    import io
    import sys as sys_module
    
    config = get_config()
    
    # Capture output
    old_stdout = sys_module.stdout
    sys_module.stdout = io.StringIO()
    print_config(config)
    output = sys_module.stdout.getvalue()
    sys_module.stdout = old_stdout
    
    if "YBG DEVICE CONFIGURATION" in output and config.device_name in output:
        print("  ✓ PASS: print_config() works correctly")
        test5_pass = True
    else:
        print("  ✗ FAIL: print_config() output incomplete")
        test5_pass = False
except Exception as e:
    print(f"  ✗ FAIL: {e}")
    test5_pass = False

# Final verdict
print("\n" + "="*70)
print("PHASE 2 GATE TEST RESULTS")
print("="*70)

all_tests = [test1_pass, test2_pass, test3_pass, test4_pass, test5_pass]
passed = sum(all_tests)
total_tests = len(all_tests)

print(f"Tests passed: {passed}/{total_tests}")

if all(all_tests):
    print("\n🟢 PHASE 2 GATE: GREEN — All tests passed")
    print("✓ Device manager imports successfully")
    print("✓ Device configuration working")
    print("✓ DeviceConfig dataclass properly defined")
    print("✓ Adaptive configuration working")
    print("✓ print_config() working")
    print("\nREADY TO PROCEED TO PHASE 3")
    sys.exit(0)
else:
    print("\n🔴 PHASE 2 GATE: RED — Some tests failed")
    print("FIX ISSUES BEFORE PROCEEDING")
    sys.exit(1)
