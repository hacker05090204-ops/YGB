"""
YGB Authentication Module — JWT + bcrypt + Rate Limiting

Production auth with:
- JWT token generation and verification
- Password hashing via hashlib (bcrypt optional)
- Rate limiting for login attempts
- Session expiration enforcement
- CSRF token generation
- Device hash computation

ZERO mock users. ZERO bypass tokens. ZERO hardcoded credentials.
"""

import os
import sys
import time
import hashlib
import hmac
import secrets
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any, Tuple
from pathlib import Path
from collections import defaultdict

# Add project root
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# SECURITY: No .env loading — secrets MUST come from environment variables only.
# Removed dotenv loading to prevent accidental secret leaks from .env files.

# JWT config from env
JWT_SECRET = os.getenv("JWT_SECRET", "")
if not JWT_SECRET:
    import warnings
    warnings.warn(
        "[AUTH] JWT_SECRET not set. Token operations will fail. "
        "Set JWT_SECRET environment variable before starting the server.",
        RuntimeWarning,
        stacklevel=2,
    )
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
JWT_EXPIRATION_HOURS = int(os.getenv("JWT_EXPIRATION_HOURS", "24"))

# Rate limiting config
LOGIN_RATE_LIMIT_MAX = int(os.getenv("LOGIN_RATE_LIMIT_MAX", "5"))
LOGIN_RATE_LIMIT_WINDOW = int(os.getenv("LOGIN_RATE_LIMIT_WINDOW_SECONDS", "60"))


# =============================================================================
# PASSWORD HASHING (Argon2id primary, scrypt fallback, HMAC-SHA256 legacy)
# =============================================================================

_HASH_ITERATIONS = 100_000
_HASH_VERSION_V2 = "v2"  # v2 = iterative HMAC-SHA256 (legacy)

# Try Argon2id first, fall back to scrypt
try:
    from argon2 import PasswordHasher as _Argon2Hasher
    from argon2.exceptions import VerifyMismatchError as _Argon2Mismatch
    _argon2_hasher = _Argon2Hasher(
        time_cost=3, memory_cost=65536, parallelism=4, hash_len=32, salt_len=16
    )
    _HASH_VERSION = "v3"  # v3 = Argon2id
    _USE_ARGON2 = True
except ImportError:
    _HASH_VERSION = "v3s"  # v3s = scrypt (Argon2 not available)
    _USE_ARGON2 = False
    _argon2_hasher = None
    _Argon2Mismatch = None


def hash_password(password: str) -> str:
    """Hash a password with Argon2id (preferred) or scrypt fallback."""
    if _USE_ARGON2:
        # Argon2id — salt is embedded in the hash output
        hashed = _argon2_hasher.hash(password)
        return f"v3:{hashed}"
    else:
        # scrypt fallback
        salt = secrets.token_bytes(16)
        key = hashlib.scrypt(
            password.encode(), salt=salt, n=2**14, r=8, p=1, dklen=32
        )
        return f"v3s:{salt.hex()}:{key.hex()}"


def _iterative_hash(password: str, salt: str) -> str:
    """Iterative HMAC-SHA256 key derivation (v2 legacy)."""
    key = f"{salt}:{password}".encode()
    digest = hashlib.sha256(key).digest()
    for _ in range(_HASH_ITERATIONS):
        digest = hmac.new(key, digest, hashlib.sha256).digest()
    return digest.hex()


def verify_password(password: str, stored_hash: str) -> bool:
    """Verify password — supports v3 (Argon2id), v3s (scrypt), v2 (HMAC-SHA256), v1 (SHA-256)."""
    if not stored_hash or not password:
        return False

    # v3 format: v3:<argon2id hash>
    if stored_hash.startswith("v3:") and not stored_hash.startswith("v3s:"):
        if not _USE_ARGON2:
            return False  # Cannot verify Argon2 without argon2-cffi
        argon2_hash = stored_hash[3:]
        try:
            return _argon2_hasher.verify(argon2_hash, password)
        except _Argon2Mismatch:
            return False
        except Exception:
            return False

    # v3s format: v3s:salt_hex:key_hex (scrypt)
    if stored_hash.startswith("v3s:"):
        parts = stored_hash.split(":", 2)
        if len(parts) != 3:
            return False
        _, salt_hex, expected_hex = parts
        try:
            salt = bytes.fromhex(salt_hex)
            key = hashlib.scrypt(
                password.encode(), salt=salt, n=2**14, r=8, p=1, dklen=32
            )
            return hmac.compare_digest(key.hex(), expected_hex)
        except Exception:
            return False

    # v2 format: v2:salt:hash (iterative HMAC-SHA256)
    if stored_hash.startswith("v2:"):
        parts = stored_hash.split(":", 2)
        if len(parts) != 3:
            return False
        _, salt, expected = parts
        actual = _iterative_hash(password, salt)
        return hmac.compare_digest(actual, expected)

    # Legacy v1 format: salt:hash (SHA-256)
    if ":" not in stored_hash:
        return False
    salt, expected_hash = stored_hash.split(":", 1)
    actual_hash = hashlib.sha256(f"{salt}:{password}".encode()).hexdigest()
    return hmac.compare_digest(actual_hash, expected_hash)


def needs_rehash(stored_hash: str) -> bool:
    """Check if a stored hash needs upgrade to current version (v3/v3s)."""
    return not stored_hash.startswith(f"{_HASH_VERSION}:")


# =============================================================================
# JWT TOKEN MANAGEMENT
# =============================================================================

def generate_jwt(user_id: str, email: str = None) -> str:
    """Generate a JWT token for a user."""
    try:  # pragma: no cover
        import jwt  # pragma: no cover
    except ImportError:  # pragma: no cover
        # Fallback: simple HMAC-based token
        return _generate_simple_token(user_id)  # pragma: no cover

    now = datetime.now(timezone.utc)
    payload = {
        "sub": user_id,
        "email": email,
        "iat": now,
        "exp": now + timedelta(hours=JWT_EXPIRATION_HOURS),
        "jti": secrets.token_hex(16),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def verify_jwt(token: str) -> Optional[Dict[str, Any]]:
    """Verify and decode a JWT token. Returns None if invalid."""
    try:  # pragma: no cover
        import jwt  # pragma: no cover
    except ImportError:  # pragma: no cover
        return _verify_simple_token(token)  # pragma: no cover

    try:  # pragma: no cover
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])  # pragma: no cover
        return payload  # pragma: no cover
    except jwt.ExpiredSignatureError:  # pragma: no cover
        return None  # pragma: no cover
    except jwt.InvalidTokenError:  # pragma: no cover
        return None  # pragma: no cover


def _generate_simple_token(user_id: str) -> str:
    """Fallback HMAC token when PyJWT not installed."""
    expires = int(time.time()) + (JWT_EXPIRATION_HOURS * 3600)
    data = f"{user_id}:{expires}"
    sig = hmac.new(JWT_SECRET.encode(), data.encode(), hashlib.sha256).hexdigest()
    return f"{data}:{sig}"


def _verify_simple_token(token: str) -> Optional[Dict[str, Any]]:
    """Verify fallback HMAC token."""
    parts = token.split(":")
    if len(parts) != 3:
        return None

    user_id, expires_str, sig = parts
    try:
        expires = int(expires_str)
    except ValueError:
        return None

    if time.time() > expires:
        return None

    data = f"{user_id}:{expires_str}"
    expected_sig = hmac.new(JWT_SECRET.encode(), data.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(sig, expected_sig):
        return None

    return {"sub": user_id, "exp": expires}


# =============================================================================
# RATE LIMITING
# =============================================================================

class RateLimiter:
    """In-memory rate limiter for login attempts."""

    def __init__(self, max_attempts: int = LOGIN_RATE_LIMIT_MAX,
                 window_seconds: int = LOGIN_RATE_LIMIT_WINDOW):
        self.max_attempts = max_attempts
        self.window_seconds = window_seconds
        self._attempts: Dict[str, list] = defaultdict(list)

    def is_rate_limited(self, key: str) -> bool:
        """Check if a key (IP address) is rate limited."""
        now = time.time()
        # Clean old entries
        self._attempts[key] = [
            t for t in self._attempts[key]
            if now - t < self.window_seconds
        ]
        return len(self._attempts[key]) >= self.max_attempts

    def record_attempt(self, key: str):
        """Record a login attempt."""
        self._attempts[key].append(time.time())

    def get_remaining(self, key: str) -> int:
        """Get remaining attempts before rate limit."""
        now = time.time()
        recent = [t for t in self._attempts[key] if now - t < self.window_seconds]
        return max(0, self.max_attempts - len(recent))

    def reset(self, key: str):
        """Reset rate limit for a key (after successful login)."""
        self._attempts.pop(key, None)


# =============================================================================
# DEVICE HASH
# =============================================================================

def compute_device_hash(user_agent: str, ip_address: str = None) -> str:
    """Compute a stable hash representing a device."""
    # Use user-agent as primary signal (IP can change)
    data = user_agent or "unknown"
    return hashlib.sha256(data.encode()).hexdigest()[:16]


# =============================================================================
# CSRF PROTECTION
# =============================================================================

def generate_csrf_token() -> str:
    """Generate a CSRF token."""
    return secrets.token_hex(32)


def verify_csrf_token(token: str, stored_token: str) -> bool:
    """Verify a CSRF token."""
    return hmac.compare_digest(token, stored_token)


# =============================================================================
# SINGLETON
# =============================================================================

_rate_limiter: Optional[RateLimiter] = None


def get_rate_limiter() -> RateLimiter:
    """Get or create the singleton RateLimiter."""
    global _rate_limiter
    if _rate_limiter is None:
        _rate_limiter = RateLimiter()
    return _rate_limiter
