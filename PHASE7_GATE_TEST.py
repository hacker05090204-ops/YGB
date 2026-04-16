"""
PHASE 7 GATE TEST — Security Hardening
Tests auth bypass gating, secret enforcement, integrity checks
"""

import sys
import os

print("="*70)
print("PHASE 7 GATE TEST — Security Hardening")
print("="*70)

# Test 1: Auth guard file exists
print("\n[TEST 1] Auth Guard Exists")
try:
    from pathlib import Path
    auth_guard_path = Path("backend/auth/auth_guard.py")
    
    if auth_guard_path.exists():
        content = auth_guard_path.read_text()
        
        # Check for key security features
        has_bypass_gate = "YGB_ENV" in content and "production" in content
        has_jwt_check = "JWT_SECRET" in content
        has_csrf = "csrf" in content.lower()
        
        print(f"  Auth guard file: EXISTS")
        print(f"  Production bypass gate: {'YES' if has_bypass_gate else 'NO'}")
        print(f"  JWT secret check: {'YES' if has_jwt_check else 'NO'}")
        print(f"  CSRF protection: {'YES' if has_csrf else 'NO'}")
        
        if has_bypass_gate and has_jwt_check and has_csrf:
            print("  PASS: Auth guard has security features")
            test1_pass = True
        else:
            print("  FAIL: Missing security features")
            test1_pass = False
    else:
        print("  FAIL: Auth guard file not found")
        test1_pass = False
        
except Exception as e:
    print(f"  FAIL: {e}")
    test1_pass = False

# Test 2: JWT secret enforcement
print("\n[TEST 2] JWT Secret Enforcement")
try:
    # Set empty secret to test enforcement
    os.environ['JWT_SECRET'] = ''
    
    try:
        # This should fail with empty secret
        from backend.auth import auth
        print("  FAIL: Empty JWT secret was accepted")
        test2_pass = False
    except RuntimeError as e:
        if "JWT_SECRET" in str(e) and "placeholder" in str(e):
            print(f"  Secret enforcement triggered: {str(e)[:80]}...")
            print("  PASS: JWT secret enforcement working")
            test2_pass = True
        else:
            print(f"  FAIL: Wrong error: {e}")
            test2_pass = False
            
except Exception as e:
    print(f"  FAIL: {e}")
    test2_pass = False
finally:
    # Clean up
    if 'JWT_SECRET' in os.environ:
        del os.environ['JWT_SECRET']

# Test 3: Production bypass gate
print("\n[TEST 3] Production Bypass Gate")
try:
    from pathlib import Path
    auth_guard_path = Path("backend/auth/auth_guard.py")
    content = auth_guard_path.read_text()
    
    # Check for production gating logic
    has_env_check = 'os.getenv("YGB_ENV")' in content or 'os.environ.get("YGB_ENV")' in content
    has_prod_check = '"production"' in content or "'production'" in content
    
    print(f"  Environment check: {'YES' if has_env_check else 'NO'}")
    print(f"  Production check: {'YES' if has_prod_check else 'NO'}")
    
    if has_env_check and has_prod_check:
        print("  PASS: Production bypass gate implemented")
        test3_pass = True
    else:
        print("  FAIL: Production gate missing")
        test3_pass = False
        
except Exception as e:
    print(f"  FAIL: {e}")
    test3_pass = False

# Test 4: Checkpoint integrity
print("\n[TEST 4] Checkpoint Integrity Verification")
try:
    from pathlib import Path
    
    # Check for SHA256 verification in codebase
    files_to_check = [
        "backend/training/safetensors_store.py",
        "training_controller.py",
    ]
    
    has_sha256 = False
    for file_path in files_to_check:
        p = Path(file_path)
        if p.exists():
            content = p.read_text()
            if "sha256" in content.lower() or "hashlib" in content:
                has_sha256 = True
                print(f"  Found SHA256 in: {file_path}")
                break
    
    if has_sha256:
        print("  PASS: Checkpoint integrity verification present")
        test4_pass = True
    else:
        print("  FAIL: No SHA256 verification found")
        test4_pass = False
        
except Exception as e:
    print(f"  FAIL: {e}")
    test4_pass = False

# Test 5: Path traversal protection
print("\n[TEST 5] Path Traversal Protection")
try:
    from pathlib import Path
    from backend.storage import storage_bridge

    component_blocked = False
    helper_blocked = False
    store_blocked = False
    token_blocked = False

    try:
        storage_bridge.sanitize_storage_path_component(
            "../escape",
            field_name="user_id",
        )
    except ValueError as exc:
        component_blocked = "user_id" in str(exc) or "unsafe" in str(exc).lower()

    try:
        storage_bridge._sanitize_path(
            Path("phase7_safe_root"),
            "../../../etc/passwd",
        )
    except ValueError:
        helper_blocked = True

    store_result = storage_bridge.store_video(
        "../escape",
        "session_01",
        b"video-bytes",
    )
    store_blocked = (
        store_result.get("success") is False
        and "user_id" in str(store_result.get("reason", ""))
    )

    token_result = storage_bridge.get_video_stream_token(
        "user_01",
        "session_01",
        "../secret.webm",
    )
    token_blocked = (
        "error" in token_result
        and "filename" in str(token_result.get("error", ""))
    )

    print(f"  Component sanitization: {'PASS' if component_blocked else 'FAIL'}")
    print(f"  Helper traversal guard: {'PASS' if helper_blocked else 'FAIL'}")
    print(f"  store_video blocks traversal: {'PASS' if store_blocked else 'FAIL'}")
    print(f"  get_video_stream_token blocks traversal: {'PASS' if token_blocked else 'FAIL'}")

    if component_blocked and helper_blocked and store_blocked and token_blocked:
        print("  PASS: Path traversal protection present and enforced")
        test5_pass = True
    else:
        print("  FAIL: Path traversal protection not enforced at all required points")
        test5_pass = False
        
except Exception as e:
    print(f"  FAIL: {e}")
    test5_pass = False

# Final verdict
print("\n" + "="*70)
print("PHASE 7 GATE TEST RESULTS")
print("="*70)

all_tests = [test1_pass, test2_pass, test3_pass, test4_pass, test5_pass]
passed = sum(all_tests)
total_tests = len(all_tests)

print(f"Tests passed: {passed}/{total_tests}")

if all(all_tests):
    print("\nPHASE 7 GATE: GREEN — All tests passed")
    print("- Auth guard with security features")
    print("- JWT secret enforcement working")
    print("- Production bypass gate implemented")
    print("- Checkpoint integrity verification present")
    print("- Path traversal protection present")
    print("\nREADY TO PROCEED TO PHASE 8")
    sys.exit(0)
else:
    print("\nPHASE 7 GATE: RED — Some tests failed")
    print("NOT DONE - FIX ISSUES BEFORE PROCEEDING")
    sys.exit(1)
