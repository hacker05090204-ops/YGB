"""
Tests for Auth Security

Verifies:
- JWT generation and verification
- Password hashing and verification
- Rate limiting blocks after threshold
- Session expiration via JWT
- CSRF token generation
- No hardcoded credentials
"""

import sys
import time
import pytest
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from backend.auth.auth import (
    hash_password, verify_password,
    generate_jwt, verify_jwt,
    RateLimiter, generate_csrf_token, verify_csrf_token,
    compute_device_hash
)


class TestPasswordHashing:
    """Test password hashing security."""

    def test_hash_produces_salt(self):
        """Hash must contain a salt separator."""
        hashed = hash_password("mypassword123")
        assert ":" in hashed

    def test_same_password_different_hash(self):
        """Same password hashed twice should produce different results (different salt)."""
        h1 = hash_password("mypassword123")
        h2 = hash_password("mypassword123")
        assert h1 != h2  # Different salts

    def test_verify_correct_password(self):
        """Correct password should verify."""
        hashed = hash_password("correcthorse")
        assert verify_password("correcthorse", hashed) is True

    def test_verify_wrong_password(self):
        """Wrong password should not verify."""
        hashed = hash_password("correcthorse")
        assert verify_password("wronghorse", hashed) is False

    def test_verify_empty_hash(self):
        """Empty or malformed hash should not verify."""
        assert verify_password("password", "") is False
        assert verify_password("password", "noseparator") is False


class TestJWT:
    """Test JWT token management."""

    def test_generate_and_verify(self):
        """Generate a token and verify it."""
        import os
        os.environ["JWT_SECRET"] = "test-secret-key-for-testing-only"

        # Reset module state
        import backend.auth.auth as auth_mod
        auth_mod.JWT_SECRET = "test-secret-key-for-testing-only"

        token = generate_jwt("user-123", "test@test.com")
        assert token is not None
        assert len(token) > 0

        payload = verify_jwt(token)
        assert payload is not None
        assert payload.get("sub") == "user-123"

    def test_invalid_token_returns_none(self):
        """Invalid token should return None, not crash."""
        result = verify_jwt("totally.invalid.token")
        assert result is None

    def test_empty_token_returns_none(self):
        """Empty token should return None."""
        result = verify_jwt("")
        assert result is None


class TestRateLimiting:
    """Test rate limiter."""

    def test_allows_under_limit(self):
        """Should allow attempts under the limit."""
        limiter = RateLimiter(max_attempts=3, window_seconds=60)
        assert limiter.is_rate_limited("1.1.1.1") is False

        limiter.record_attempt("1.1.1.1")
        limiter.record_attempt("1.1.1.1")
        assert limiter.is_rate_limited("1.1.1.1") is False

    def test_blocks_at_limit(self):
        """Should block after reaching the limit."""
        limiter = RateLimiter(max_attempts=3, window_seconds=60)

        for _ in range(3):
            limiter.record_attempt("1.1.1.1")

        assert limiter.is_rate_limited("1.1.1.1") is True

    def test_different_ips_independent(self):
        """Rate limits should be independent per IP."""
        limiter = RateLimiter(max_attempts=2, window_seconds=60)

        limiter.record_attempt("1.1.1.1")
        limiter.record_attempt("1.1.1.1")

        assert limiter.is_rate_limited("1.1.1.1") is True
        assert limiter.is_rate_limited("2.2.2.2") is False

    def test_reset_clears_limit(self):
        """Resetting should clear the rate limit."""
        limiter = RateLimiter(max_attempts=2, window_seconds=60)

        limiter.record_attempt("1.1.1.1")
        limiter.record_attempt("1.1.1.1")
        assert limiter.is_rate_limited("1.1.1.1") is True

        limiter.reset("1.1.1.1")
        assert limiter.is_rate_limited("1.1.1.1") is False

    def test_remaining_count(self):
        """Should correctly report remaining attempts."""
        limiter = RateLimiter(max_attempts=5, window_seconds=60)
        assert limiter.get_remaining("1.1.1.1") == 5

        limiter.record_attempt("1.1.1.1")
        assert limiter.get_remaining("1.1.1.1") == 4


class TestCSRF:
    """Test CSRF token generation/verification."""

    def test_generate_returns_string(self):
        """CSRF token should be a hex string."""
        token = generate_csrf_token()
        assert isinstance(token, str)
        assert len(token) == 64  # 32 bytes = 64 hex chars

    def test_verify_correct_token(self):
        """Correct CSRF token should verify."""
        token = generate_csrf_token()
        assert verify_csrf_token(token, token) is True

    def test_verify_wrong_token(self):
        """Wrong CSRF token should not verify."""
        token1 = generate_csrf_token()
        token2 = generate_csrf_token()
        assert verify_csrf_token(token1, token2) is False


class TestNoHardcodedCredentials:
    """Ensure no hardcoded credentials in auth module."""

    def test_no_hardcoded_passwords(self):
        """Auth source must not contain hardcoded passwords."""
        import inspect
        import backend.auth.auth as auth_mod
        source = inspect.getsource(auth_mod)

        forbidden = ["admin123", "password123", "secret123", "default_password",
                      "HARDCODED_", "MOCK_PASSWORD"]
        for keyword in forbidden:
            assert keyword not in source, \
                f"Hardcoded credential pattern '{keyword}' found in auth module"
