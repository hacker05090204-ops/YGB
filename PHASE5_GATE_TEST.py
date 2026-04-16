"""
PHASE 5 GATE TEST — Self-Reflection Engine
Tests method invention, failure tracking, persistence
"""

import sys
import tempfile
from pathlib import Path

print("="*70)
print("PHASE 5 GATE TEST — Self-Reflection Engine")
print("="*70)

# Test 1: Import
print("\n[TEST 1] Self-Reflection Import")
try:
    from backend.agent.self_reflection import (
        SelfReflectionEngine,
        MethodLibrary,
        FailureObservation,
        VulnMethod,
        ReflectionEvent,
    )
    print("  PASS: All components imported")
    test1_pass = True
except ImportError as e:
    print(f"  FAIL: {e}")
    test1_pass = False

# Test 2: Method Library
print("\n[TEST 2] Method Library")
try:
    from backend.agent.self_reflection import MethodLibrary
    
    with tempfile.TemporaryDirectory() as tmpdir:
        lib_path = Path(tmpdir) / "methods.json"
        lib = MethodLibrary(lib_path)
        
        methods = lib.get_all_methods()
        print(f"  Seed methods: {len(methods)}")
        
        # Record outcomes
        lib.record_outcome("xss_basic", success=True)
        lib.record_outcome("xss_basic", success=False)
        
        all_methods = lib.get_all_methods()
        xss_method = [m for m in all_methods if m.method_id == "xss_basic"][0]
        
        print(f"  XSS method: success={xss_method.success_count}, fail={xss_method.failure_count}")
        
        if xss_method.success_count == 1 and xss_method.failure_count == 1:
            print("  PASS: Method library working")
            test2_pass = True
        else:
            print("  FAIL: Unexpected counts")
            test2_pass = False
            
except Exception as e:
    print(f"  FAIL: {e}")
    test2_pass = False

# Test 3: Method Invention
print("\n[TEST 3] Method Invention")
try:
    from backend.agent.self_reflection import MethodLibrary, SelfReflectionEngine
    
    with tempfile.TemporaryDirectory() as tmpdir:
        lib_path = Path(tmpdir) / "methods.json"
        log_path = Path(tmpdir) / "reflection.jsonl"
        
        lib = MethodLibrary(lib_path)
        engine = SelfReflectionEngine(lib, log_path)
        
        # Simulate repeated failures
        for i in range(4):
            engine.observe_failure("xss_basic", "xss", "basic payload filtered by WAF")
        
        # Check if new method was invented
        invented = [m for m in lib.get_all_methods() if m.invented_by == "self_reflection"]
        
        print(f"  Failures recorded: 4")
        print(f"  Invented methods: {len(invented)}")
        
        if len(invented) > 0:
            print(f"  New method: {invented[0].name}")
            print("  PASS: Method invention working")
            test3_pass = True
        else:
            print("  FAIL: No methods invented")
            test3_pass = False
            
except Exception as e:
    print(f"  FAIL: {e}")
    test3_pass = False

# Test 4: Persistence
print("\n[TEST 4] Persistence")
try:
    from backend.agent.self_reflection import MethodLibrary
    
    with tempfile.TemporaryDirectory() as tmpdir:
        lib_path = Path(tmpdir) / "methods.json"
        
        # Create library and add method
        lib1 = MethodLibrary(lib_path)
        initial_count = len(lib1.get_all_methods())
        lib1.record_outcome("xss_basic", success=True)
        xss1 = [m for m in lib1.get_all_methods() if m.method_id == "xss_basic"][0]
        
        # Load library again
        lib2 = MethodLibrary(lib_path)
        xss2 = [m for m in lib2.get_all_methods() if m.method_id == "xss_basic"][0]
        
        print(f"  First library: success_count={xss1.success_count}")
        print(f"  Reloaded library: success_count={xss2.success_count}")
        print(f"  Methods persisted: {len(lib2.get_all_methods())}")
        
        if xss1.success_count == xss2.success_count and len(lib2.get_all_methods()) == initial_count:
            print("  PASS: Persistence working")
            test4_pass = True
        else:
            print("  FAIL: Data not persisted correctly")
            test4_pass = False
            
except Exception as e:
    print(f"  FAIL: {e}")
    test4_pass = False

# Test 5: Stats
print("\n[TEST 5] Statistics")
try:
    from backend.agent.self_reflection import MethodLibrary, SelfReflectionEngine
    
    with tempfile.TemporaryDirectory() as tmpdir:
        lib_path = Path(tmpdir) / "methods.json"
        log_path = Path(tmpdir) / "reflection.jsonl"
        
        lib = MethodLibrary(lib_path)
        engine = SelfReflectionEngine(lib, log_path)
        
        # Get initial stats
        initial_stats = engine.get_stats()
        
        # Record some outcomes
        engine.observe_success("xss_basic", "xss")
        engine.observe_failure("sqli_error", "sqli", "error suppressed")
        
        stats = engine.get_stats()
        
        print(f"  Total methods: {stats['total_methods']}")
        print(f"  Successes added: {stats['total_successes'] - initial_stats['total_successes']}")
        print(f"  Failures added: {stats['total_failures'] - initial_stats['total_failures']}")
        
        success_delta = stats['total_successes'] - initial_stats['total_successes']
        failure_delta = stats['total_failures'] - initial_stats['total_failures']
        
        if success_delta == 1 and failure_delta == 1:
            print("  PASS: Statistics working")
            test5_pass = True
        else:
            print("  FAIL: Unexpected stats")
            test5_pass = False
            
except Exception as e:
    print(f"  FAIL: {e}")
    test5_pass = False

# Final verdict
print("\n" + "="*70)
print("PHASE 5 GATE TEST RESULTS")
print("="*70)

all_tests = [test1_pass, test2_pass, test3_pass, test4_pass, test5_pass]
passed = sum(all_tests)
total_tests = len(all_tests)

print(f"Tests passed: {passed}/{total_tests}")

if all(all_tests):
    print("\nPHASE 5 GATE: GREEN — All tests passed")
    print("- Self-reflection engine imports successfully")
    print("- Method library working")
    print("- Method invention working")
    print("- Persistence working")
    print("- Statistics working")
    print("\nREADY TO PROCEED TO PHASE 6")
    sys.exit(0)
else:
    print("\nPHASE 5 GATE: RED — Some tests failed")
    print("NOT DONE - FIX ISSUES BEFORE PROCEEDING")
    sys.exit(1)
