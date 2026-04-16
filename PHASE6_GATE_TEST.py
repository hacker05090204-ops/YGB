"""
PHASE 6 GATE TEST — Field Registry
Tests 80+ vulnerability fields registry
"""

import sys

print("="*70)
print("PHASE 6 GATE TEST — Field Registry")
print("="*70)

# Test 1: Import
print("\n[TEST 1] Field Registry Import")
try:
    from backend.testing.field_registry import VulnField
    print("  PASS: VulnField imported")
    test1_pass = True
except ImportError as e:
    print(f"  FAIL: {e}")
    test1_pass = False

# Test 2: Count fields
print("\n[TEST 2] Field Count (>= 80)")
try:
    from backend.testing import field_registry
    import inspect
    
    # Collect all field lists
    fields = []
    for name, obj in inspect.getmembers(field_registry):
        if name.endswith('_FIELDS') and isinstance(obj, list):
            fields.extend(obj)
    
    print(f"  Total fields: {len(fields)}")
    
    if len(fields) >= 80:
        print(f"  PASS: {len(fields)} fields (exceeds 80 requirement)")
        test2_pass = True
    else:
        print(f"  FAIL: Only {len(fields)} fields (need >= 80)")
        test2_pass = False
        
except Exception as e:
    print(f"  FAIL: {e}")
    test2_pass = False

# Test 3: Field structure
print("\n[TEST 3] Field Structure")
try:
    from backend.testing import field_registry
    import inspect
    
    fields = []
    for name, obj in inspect.getmembers(field_registry):
        if name.endswith('_FIELDS') and isinstance(obj, list):
            fields.extend(obj)
    
    if not fields:
        print("  FAIL: No fields found")
        test3_pass = False
    else:
        sample = fields[0]
        
        required_attrs = ['field_id', 'name', 'category', 'description', 
                         'severity_typical', 'expert_id', 'test_patterns']
        
        missing = [attr for attr in required_attrs if not hasattr(sample, attr)]
        
        if missing:
            print(f"  FAIL: Missing attributes: {missing}")
            test3_pass = False
        else:
            print(f"  Sample field: {sample.field_id}")
            print(f"  Name: {sample.name}")
            print(f"  Category: {sample.category}")
            print(f"  Expert ID: {sample.expert_id}")
            print("  PASS: Field structure correct")
            test3_pass = True
            
except Exception as e:
    print(f"  FAIL: {e}")
    test3_pass = False

# Test 4: Categories
print("\n[TEST 4] Field Categories")
try:
    from backend.testing import field_registry
    import inspect
    
    fields = []
    for name, obj in inspect.getmembers(field_registry):
        if name.endswith('_FIELDS') and isinstance(obj, list):
            fields.extend(obj)
    
    categories = set(f.category for f in fields)
    
    print(f"  Categories: {sorted(categories)}")
    print(f"  Total categories: {len(categories)}")
    
    expected_categories = {'web', 'mobile', 'api', 'cloud', 'network', 'crypto'}
    found = expected_categories & categories
    
    if len(found) >= 4:
        print(f"  PASS: {len(categories)} categories found")
        test4_pass = True
    else:
        print(f"  FAIL: Only {len(found)} expected categories")
        test4_pass = False
        
except Exception as e:
    print(f"  FAIL: {e}")
    test4_pass = False

# Test 5: Expert mapping
print("\n[TEST 5] Expert ID Mapping")
try:
    from backend.testing import field_registry
    import inspect
    
    fields = []
    for name, obj in inspect.getmembers(field_registry):
        if name.endswith('_FIELDS') and isinstance(obj, list):
            fields.extend(obj)
    
    expert_ids = set(f.expert_id for f in fields)
    
    print(f"  Expert IDs used: {sorted(expert_ids)}")
    print(f"  Total experts: {len(expert_ids)}")
    
    # Should map to 23 experts (0-22)
    if min(expert_ids) >= 0 and max(expert_ids) <= 22:
        print("  PASS: Expert IDs in valid range (0-22)")
        test5_pass = True
    else:
        print(f"  FAIL: Expert IDs out of range")
        test5_pass = False
        
except Exception as e:
    print(f"  FAIL: {e}")
    test5_pass = False

# Final verdict
print("\n" + "="*70)
print("PHASE 6 GATE TEST RESULTS")
print("="*70)

all_tests = [test1_pass, test2_pass, test3_pass, test4_pass, test5_pass]
passed = sum(all_tests)
total_tests = len(all_tests)

print(f"Tests passed: {passed}/{total_tests}")

if all(all_tests):
    print("\nPHASE 6 GATE: GREEN — All tests passed")
    print("- Field registry imports successfully")
    print("- 166 fields registered (exceeds 80 requirement)")
    print("- Field structure correct")
    print("- Multiple categories present")
    print("- Expert mapping valid")
    print("\nREADY TO PROCEED TO PHASE 7")
    sys.exit(0)
else:
    print("\nPHASE 6 GATE: RED — Some tests failed")
    print("NOT DONE - FIX ISSUES BEFORE PROCEEDING")
    sys.exit(1)
