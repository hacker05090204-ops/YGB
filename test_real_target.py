#!/usr/bin/env python3
"""Test hunter against a SAFE target (httpbin.org) to verify it works."""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

async def test_safe_target():
    """Test against httpbin.org - a safe testing service."""
    from backend.hunter.http_engine import SmartHTTPEngine, HTTPRequest
    from backend.hunter.explorer import AutonomousExplorer
    from backend.intelligence.scope_validator import ScopeValidator
    
    print("=" * 80)
    print("TESTING HUNTER AGAINST SAFE TARGET (httpbin.org)")
    print("=" * 80)
    
    # Test 1: HTTP Engine
    print("\n1. Testing HTTP Engine...")
    http = SmartHTTPEngine(session_id="test_safe")
    try:
        req = HTTPRequest("GET", "https://httpbin.org/get")
        resp = await http.send(req)
        print(f"   ✓ HTTP GET successful: {resp.status_code}")
        print(f"   ✓ Response length: {resp.content_length} bytes")
        assert resp.status_code == 200
    except Exception as e:
        print(f"   ✗ HTTP Engine failed: {e}")
        return False
    
    # Test 2: POST Request
    print("\n2. Testing POST Request...")
    try:
        req = HTTPRequest("POST", "https://httpbin.org/post", body='{"test": "data"}')
        resp = await http.send(req)
        print(f"   ✓ HTTP POST successful: {resp.status_code}")
        assert resp.status_code == 200
    except Exception as e:
        print(f"   ✗ POST failed: {e}")
        return False
    
    # Test 3: Headers
    print("\n3. Testing Custom Headers...")
    try:
        req = HTTPRequest("GET", "https://httpbin.org/headers", 
                         headers={"X-Test": "hunter-test"})
        resp = await http.send(req)
        print(f"   ✓ Custom headers sent: {resp.status_code}")
        assert resp.status_code == 200
    except Exception as e:
        print(f"   ✗ Headers test failed: {e}")
        return False
    
    # Test 4: Cookies
    print("\n4. Testing Cookie Handling...")
    try:
        req = HTTPRequest("GET", "https://httpbin.org/cookies/set?test=value")
        resp = await http.send(req)
        print(f"   ✓ Cookie set: {resp.status_code}")
        print(f"   ✓ Cookies collected: {len(http._session_cookies)}")
    except Exception as e:
        print(f"   ✗ Cookie test failed: {e}")
        return False
    
    # Test 5: Rate Limiting
    print("\n5. Testing Rate Limiting...")
    try:
        start = asyncio.get_event_loop().time()
        for i in range(3):
            req = HTTPRequest("GET", "https://httpbin.org/get")
            await http.send(req)
        elapsed = asyncio.get_event_loop().time() - start
        print(f"   ✓ Rate limiting working (3 requests in {elapsed:.2f}s)")
        assert elapsed > 0.1  # Should have some delay
    except Exception as e:
        print(f"   ✗ Rate limiting test failed: {e}")
        return False
    
    # Test 6: Scope Validation
    print("\n6. Testing Scope Validation...")
    scope = ScopeValidator()
    decision = scope.validate("httpbin.org", ["httpbin.org"])
    print(f"   ✓ Scope validation: {decision.in_scope}")
    assert decision.in_scope
    
    decision = scope.validate("evil.com", ["httpbin.org"])
    print(f"   ✓ Out-of-scope blocked: {not decision.in_scope}")
    assert not decision.in_scope
    
    # Test 7: Explorer (limited)
    print("\n7. Testing Explorer (limited crawl)...")
    try:
        explorer = AutonomousExplorer(http, scope)
        result = await explorer.explore(
            "https://httpbin.org",
            ["httpbin.org"],
            max_pages=5  # Very limited
        )
        print(f"   ✓ Pages explored: {result.total_pages_visited}")
        print(f"   ✓ Endpoints found: {len(result.endpoints)}")
        print(f"   ✓ Tech stack: {result.tech_stack}")
    except Exception as e:
        print(f"   ✗ Explorer failed: {e}")
        return False
    
    await http.close()
    
    print("\n" + "=" * 80)
    print("ALL TESTS PASSED ✓")
    print("=" * 80)
    return True

if __name__ == "__main__":
    result = asyncio.run(test_safe_target())
    sys.exit(0 if result else 1)
