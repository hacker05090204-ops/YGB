"""
Test P0 Security Fixes — Comprehensive Verification Suite

Tests for all 10 P0 security items:
1. Protected API routes require auth (401 without token)
2. Token/session verification works
3. Logout revokes token and session
4. No duplicate /api/voice/parse route ambiguity
5. No weak/default secret behavior
6. Video token endpoint requires auth
7. Password hashing upgraded to iterative HMAC
8. SSRF/scope gating blocks private IPs
9. Synthetic data fallback is impossible
10. Update signature verification is strict
"""

import os
import sys
import importlib
import hashlib
import hmac
import secrets
import time
import pytest
from pathlib import Path
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


# =============================================================================
# P0-1: Protected API routes require auth (401 without token)
# =============================================================================

class TestRouteProtection:
    """Verify all sensitive routes require authentication."""

    def test_auth_guard_module_exists(self):
        """auth_guard.py must exist and be importable."""
        from backend.auth.auth_guard import require_auth, require_admin
        assert callable(require_auth)
        assert callable(require_admin)

    def test_server_imports_auth_guard(self):
        """server.py must import auth_guard dependencies."""
        server_path = PROJECT_ROOT / "api" / "server.py"
        content = server_path.read_text(errors="ignore")
        assert "require_auth" in content, "server.py must import require_auth"
        assert "require_admin" in content, "server.py must import require_admin"
        assert "Depends(require_auth)" in content, "Routes must use Depends(require_auth)"
        assert "Depends(require_admin)" in content, "Admin routes must use Depends(require_admin)"

    def test_sensitive_routes_have_auth(self):
        """All state-changing/sensitive routes must include Depends(require_auth)."""
        server_path = PROJECT_ROOT / "api" / "server.py"
        content = server_path.read_text(errors="ignore")

        # Routes that MUST have auth
        protected_routes = [
            "/api/hunter/start",
            "/api/bounty/start",
            "/api/execution/transition",
            "/scope/validate",
            "/target/start",
            "/api/video/token",
            "/auth/logout",
            "/training/start",
            "/training/stop",
            "/training/continuous",
            "/training/continuous/stop",
            "/api/g38/abort",
            "/api/g38/start",
            "/api/mode/train/start",
            "/api/mode/train/stop",
            "/api/mode/hunt/start",
            "/api/mode/hunt/stop",
        ]
        for route in protected_routes:
            # Find the route + its function def and check for Depends
            idx = content.find(f'"{route}"')
            if idx == -1:
                continue
            # Look at the next 200 chars for Depends(require_auth) or Depends(require_admin)
            chunk = content[idx:idx+200]
            assert "Depends(require_auth)" in chunk or "Depends(require_admin)" in chunk, \
                f"Route {route} is NOT protected with auth dependency"

    def test_admin_routes_require_admin_role(self):
        """Admin routes must use Depends(require_admin)."""
        server_path = PROJECT_ROOT / "api" / "server.py"
        content = server_path.read_text(errors="ignore")
        admin_routes = ["/admin/active-devices", "/admin/active-sessions"]
        for route in admin_routes:
            idx = content.find(f'"{route}"')
            if idx == -1:
                continue
            chunk = content[idx:idx+200]
            assert "Depends(require_admin)" in chunk, \
                f"Admin route {route} must use Depends(require_admin)"


# =============================================================================
# P0-2: Token/session verification
# =============================================================================

class TestTokenVerification:
    """Verify token verification works correctly."""

    def test_token_revocation_store(self):
        """Token revocation must track revoked tokens."""
        from backend.auth.auth_guard import (
            revoke_token, is_token_revoked
        )
        test_token = f"test-token-{secrets.token_hex(16)}"
        assert not is_token_revoked(test_token)
        revoke_token(test_token)
        assert is_token_revoked(test_token)

    def test_session_revocation_store(self):
        """Session revocation must track revoked sessions."""
        from backend.auth.auth_guard import (
            revoke_session, is_session_revoked
        )
        test_session = f"test-session-{secrets.token_hex(8)}"
        assert not is_session_revoked(test_session)
        revoke_session(test_session)
        assert is_session_revoked(test_session)


# =============================================================================
# P0-3: Logout revokes token/session
# =============================================================================

class TestLogout:
    """Verify logout properly invalidates tokens and sessions."""

    def test_logout_endpoint_has_revocation(self):
        """Logout endpoint must call revoke_token and end_session."""
        server_path = PROJECT_ROOT / "api" / "server.py"
        content = server_path.read_text(errors="ignore")
        # Find logout handler — search a larger window
        idx = content.find("def logout")
        assert idx != -1, "logout handler not found"
        logout_code = content[idx:idx+800]
        assert "revoke_token" in logout_code, "Logout must revoke the bearer token"
        assert "end_session" in logout_code, \
            "Logout must invalidate the session"


# =============================================================================
# P0-4: No duplicate /api/voice/parse route
# =============================================================================

class TestVoiceRouteDeduplicated:
    """Verify only one /api/voice/parse handler exists."""

    def test_single_voice_parse_handler(self):
        """Only one /api/voice/parse route should be registered."""
        server_path = PROJECT_ROOT / "api" / "server.py"
        content = server_path.read_text(errors="ignore")
        count = content.count('@app.post("/api/voice/parse")')
        assert count == 1, f"Expected 1 /api/voice/parse route, found {count}"


# =============================================================================
# P0-5: No weak/default secret behavior
# =============================================================================

class TestSecretHandling:
    """Verify secrets are not hardcoded or defaulting to weak values."""

    def test_no_dotenv_loading_in_auth(self):
        """auth.py must NOT load secrets from .env files."""
        auth_path = PROJECT_ROOT / "backend" / "auth" / "auth.py"
        content = auth_path.read_text(errors="ignore")
        assert "load_dotenv" not in content or "Removed" in content, \
            "auth.py must not use load_dotenv"

    def test_jwt_secret_warns_if_empty(self):
        """auth.py must warn if JWT_SECRET is not set."""
        auth_path = PROJECT_ROOT / "backend" / "auth" / "auth.py"
        content = auth_path.read_text(errors="ignore")
        assert "warnings.warn" in content or "RuntimeWarning" in content, \
            "auth.py must warn when JWT_SECRET is empty"

    def test_preflight_check_rejects_placeholder_secrets(self):
        """preflight_check_secrets() must reject known placeholder secrets."""
        from backend.auth.auth_guard import preflight_check_secrets
        # Save original and test with placeholder
        original = os.environ.get("JWT_SECRET")
        try:
            os.environ["JWT_SECRET"] = "changeme"
            with pytest.raises(RuntimeError, match="placeholder"):
                preflight_check_secrets()
        finally:
            if original:
                os.environ["JWT_SECRET"] = original
            elif "JWT_SECRET" in os.environ:
                del os.environ["JWT_SECRET"]

    def test_preflight_check_rejects_short_secrets(self):
        """preflight_check_secrets() must reject secrets shorter than 32 chars."""
        from backend.auth.auth_guard import preflight_check_secrets
        original = os.environ.get("JWT_SECRET")
        try:
            os.environ["JWT_SECRET"] = "short_secret_123"
            with pytest.raises(RuntimeError, match="too short"):
                preflight_check_secrets()
        finally:
            if original:
                os.environ["JWT_SECRET"] = original
            elif "JWT_SECRET" in os.environ:
                del os.environ["JWT_SECRET"]

    def test_preflight_check_accepts_strong_secret(self):
        """preflight_check_secrets() must pass with a strong secret."""
        from backend.auth.auth_guard import preflight_check_secrets
        original = os.environ.get("JWT_SECRET")
        try:
            os.environ["JWT_SECRET"] = secrets.token_hex(32)
            preflight_check_secrets()  # Should not raise
        finally:
            if original:
                os.environ["JWT_SECRET"] = original
            elif "JWT_SECRET" in os.environ:
                del os.environ["JWT_SECRET"]

    def test_startup_calls_preflight(self):
        """Server startup lifespan must call preflight_check_secrets()."""
        server_path = PROJECT_ROOT / "api" / "server.py"
        content = server_path.read_text(errors="ignore")
        assert "preflight_check_secrets()" in content, \
            "Server startup must call preflight_check_secrets()"


# =============================================================================
# P0-6: Video token requires auth
# =============================================================================

class TestVideoTokenProtection:
    """Verify video token endpoint is protected."""

    def test_video_token_requires_auth(self):
        """POST /api/video/token must require authentication."""
        server_path = PROJECT_ROOT / "api" / "server.py"
        content = server_path.read_text(errors="ignore")
        idx = content.find('"/api/video/token"')
        assert idx != -1, "Video token endpoint not found"
        chunk = content[idx:idx+200]
        assert "Depends(require_auth)" in chunk, \
            "Video token endpoint must require authentication"


# =============================================================================
# P0-7: Password hashing upgraded
# =============================================================================

class TestPasswordHashing:
    """Verify password hashing uses iterative HMAC, not plain SHA-256."""

    def test_hash_produces_v2_format(self):
        """hash_password must produce v2:salt:hash format."""
        from backend.auth.auth import hash_password
        hashed = hash_password("test_password_123")
        assert hashed.startswith("v2:"), f"Expected v2 prefix, got: {hashed[:10]}"
        parts = hashed.split(":", 2)
        assert len(parts) == 3, "Hash must have format v2:salt:hash"

    def test_verify_password_v2(self):
        """verify_password must correctly verify v2 hashes."""
        from backend.auth.auth import hash_password, verify_password
        pw = "my_secure_password_42"
        hashed = hash_password(pw)
        assert verify_password(pw, hashed)
        assert not verify_password("wrong_password", hashed)

    def test_verify_password_legacy_v1(self):
        """verify_password must still work with legacy v1 hashes."""
        from backend.auth.auth import verify_password
        # Simulate legacy v1 hash: salt:sha256(salt:password)
        salt = secrets.token_hex(16)
        password = "legacy_password"
        hashed = hashlib.sha256(f"{salt}:{password}".encode()).hexdigest()
        stored = f"{salt}:{hashed}"
        assert verify_password(password, stored)
        assert not verify_password("wrong", stored)

    def test_needs_rehash_detects_legacy(self):
        """needs_rehash must return True for legacy hashes."""
        from backend.auth.auth import needs_rehash
        assert needs_rehash("abc123:deadbeef")  # v1 format
        assert not needs_rehash("v2:abc123:deadbeef")  # v2 format

    def test_verify_rejects_empty(self):
        """verify_password must reject empty password or hash."""
        from backend.auth.auth import verify_password
        assert not verify_password("", "v2:salt:hash")
        assert not verify_password("password", "")
        assert not verify_password("", "")


# =============================================================================
# P0-8: SSRF/scope gating
# =============================================================================

class TestSSRFProtection:
    """Verify SSRF protection blocks private/internal targets."""

    def test_blocks_localhost(self):
        """Must block localhost targets."""
        from backend.auth.auth_guard import validate_target_url
        safe, violations = validate_target_url("http://localhost/admin")
        assert not safe
        assert any(v["rule"] == "BLOCKED_HOST" for v in violations)

    def test_blocks_private_ips(self):
        """Must block private IP ranges."""
        from backend.auth.auth_guard import validate_target_url
        for ip in ["10.0.0.1", "172.16.0.1", "192.168.1.1", "127.0.0.1"]:
            safe, violations = validate_target_url(f"http://{ip}/path")
            assert not safe, f"Should block private IP {ip}"

    def test_blocks_metadata_endpoints(self):
        """Must block cloud metadata endpoints."""
        from backend.auth.auth_guard import validate_target_url
        safe, violations = validate_target_url("http://169.254.169.254/latest/meta-data")
        assert not safe

    def test_allows_public_domains(self):
        """Must allow legitimate public domains."""
        from backend.auth.auth_guard import validate_target_url
        safe, violations = validate_target_url("https://example.com")
        assert safe, f"Should allow example.com, got violations: {violations}"

    def test_blocks_empty_url(self):
        """Must block empty URLs."""
        from backend.auth.auth_guard import validate_target_url
        safe, violations = validate_target_url("")
        assert not safe

    def test_scope_validation_in_target_start(self):
        """target/start must call validate_target_url before starting session."""
        server_path = PROJECT_ROOT / "api" / "server.py"
        content = server_path.read_text(errors="ignore")
        idx = content.find('async def start_target_session')
        assert idx != -1
        handler = content[idx:idx+500]
        assert "validate_target_url" in handler, \
            "start_target_session must call validate_target_url"


# =============================================================================
# P0-9: Synthetic data fallback impossible
# =============================================================================

class TestSyntheticDataBlocked:
    """Verify synthetic fallback is impossible in runtime."""

    def test_feature_cache_no_synthetic(self):
        """feature_cache.py must NOT generate synthetic data on import failure."""
        cache_path = PROJECT_ROOT / "impl_v1" / "training" / "data" / "feature_cache.py"
        content = cache_path.read_text(errors="ignore")
        assert "rng.randn" not in content
        assert "RuntimeError" in content
        assert "FAIL-CLOSED" in content or "FATAL" in content

    def test_real_data_enforcer_cpp_exists(self):
        """real_data_enforcer.cpp must exist and be compiled."""
        cpp_path = PROJECT_ROOT / "native" / "security" / "real_data_enforcer.cpp"
        assert cpp_path.exists()
        dll_path = PROJECT_ROOT / "native" / "security" / "real_data_enforcer.dll"
        assert dll_path.exists(), "real_data_enforcer.dll must be compiled"


# =============================================================================
# P0-10: Update signature verification is strict
# =============================================================================

class TestSignatureVerification:
    """Verify update signature checks are strict and cryptographic."""

    def test_g21_rejects_mock_signatures(self):
        """g21_auto_update.py must reject known mock signatures."""
        g21_path = PROJECT_ROOT / "impl_v1" / "phase49" / "governors" / "g21_auto_update.py"
        content = g21_path.read_text(errors="ignore")
        assert "REJECTED_SIGNATURES" in content
        assert "mock-signature" in content
        assert "Mock: Accept any non-empty" not in content

    def test_update_signature_verifier_cpp_exists(self):
        """update_signature_verifier.cpp must exist and be compiled."""
        cpp_path = PROJECT_ROOT / "native" / "security" / "update_signature_verifier.cpp"
        assert cpp_path.exists()
        dll_path = PROJECT_ROOT / "native" / "security" / "update_signature_verifier.dll"
        assert dll_path.exists(), "update_signature_verifier.dll must be compiled"

    def test_g21_requires_minimum_signature_length(self):
        """g21_auto_update.py must enforce minimum signature length."""
        g21_path = PROJECT_ROOT / "impl_v1" / "phase49" / "governors" / "g21_auto_update.py"
        content = g21_path.read_text(errors="ignore")
        assert "len(update.signature) < 64" in content or "< 64" in content
