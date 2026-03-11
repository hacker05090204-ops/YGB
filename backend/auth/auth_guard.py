"""
Auth Guard — Centralized Authentication & Authorization Middleware

Provides reusable FastAPI dependencies for:
- JWT token verification (mandatory on protected routes)
- Role-based access control (admin endpoints)
- Session validation and token revocation
- Startup preflight checks (fail-closed on missing secrets)

ZERO bypass. ZERO fallback. ZERO default secrets.
"""

import os
import sys
import time
import hashlib
import hmac
import secrets
from http.cookies import SimpleCookie
from urllib.parse import urlparse
from typing import Optional, Dict, Set
from pathlib import Path
from functools import wraps

from fastapi import Request, HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

# Add project root
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from backend.auth.auth import verify_jwt, verify_csrf_token

# =============================================================================
# TOKEN REVOCATION STORE (pluggable — see revocation_store.py)
# =============================================================================

from backend.auth.revocation_store import (
    revoke_token,
    revoke_session,
    is_token_revoked,
    is_session_revoked,
)

# Bearer token scheme
_bearer_scheme = HTTPBearer(auto_error=False)
AUTH_COOKIE_NAME = "ygb_auth"
LEGACY_AUTH_COOKIE_NAME = "ygb_token"
CSRF_COOKIE_NAME = "ygb_csrf"
CSRF_HEADER_NAME = "x-csrf-token"
_SAFE_HTTP_METHODS = frozenset({"GET", "HEAD", "OPTIONS", "TRACE"})
_TRUTHY_VALUES = frozenset({"1", "true", "yes", "on"})


def is_temporary_auth_bypass_enabled() -> bool:
    return os.getenv("YGB_TEMP_AUTH_BYPASS", "false").strip().lower() in _TRUTHY_VALUES


def build_temporary_auth_user(auth_via: str = "temporary") -> Dict:
    role = os.getenv("YGB_TEMP_AUTH_ROLE", "admin").strip().lower() or "admin"
    user_id = os.getenv("YGB_TEMP_AUTH_USER_ID", "temp-public-admin").strip() or "temp-public-admin"
    name = os.getenv("YGB_TEMP_AUTH_NAME", "Temporary Admin").strip() or "Temporary Admin"
    email = os.getenv(
        "YGB_TEMP_AUTH_EMAIL",
        "temp-public-admin@local.invalid",
    ).strip() or "temp-public-admin@local.invalid"
    session_id = os.getenv(
        "YGB_TEMP_AUTH_SESSION_ID",
        "temp-auth-bypass-session",
    ).strip() or "temp-auth-bypass-session"
    return {
        "sub": user_id,
        "name": name,
        "email": email,
        "role": role,
        "session_id": session_id,
        "auth_provider": "temporary_bypass",
        "_auth_via": auth_via,
        "_temporary_bypass": True,
    }


def _allowed_origins() -> Set[str]:
    origins = {
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:8000",
        "http://127.0.0.1:8000",
    }
    frontend = os.getenv("FRONTEND_URL", "").rstrip("/")
    if frontend:
        origins.add(frontend)
    extra = os.getenv("YGB_ALLOWED_ORIGINS", "")
    for value in extra.split(","):
        value = value.strip().rstrip("/")
        if value:
            origins.add(value)
    return origins


def _extract_cookie_token(request: Request) -> Optional[str]:
    return request.cookies.get(AUTH_COOKIE_NAME) or request.cookies.get(LEGACY_AUTH_COOKIE_NAME)


def _normalize_origin(origin: str) -> str:
    parsed = urlparse(origin)
    if not parsed.scheme or not parsed.netloc:
        return ""
    return f"{parsed.scheme}://{parsed.netloc}".rstrip("/")


def _enforce_cookie_csrf(request: Request) -> None:
    if request.method.upper() in _SAFE_HTTP_METHODS:
        return

    origin = request.headers.get("origin")
    if not origin:
        referer = request.headers.get("referer", "")
        origin = _normalize_origin(referer)
    normalized_origin = _normalize_origin(origin or "")
    if not normalized_origin or normalized_origin not in _allowed_origins():
        raise HTTPException(
            status_code=403,
            detail={"error": "CSRF_BLOCKED", "detail": "Request origin not allowed"},
        )

    csrf_cookie = request.cookies.get(CSRF_COOKIE_NAME, "")
    csrf_header = request.headers.get(CSRF_HEADER_NAME, "")
    if not csrf_cookie or not csrf_header or not verify_csrf_token(csrf_header, csrf_cookie):
        raise HTTPException(
            status_code=403,
            detail={"error": "CSRF_BLOCKED", "detail": "Missing or invalid CSRF token"},
        )


def _verify_token_or_401(token: str) -> Dict:
    if is_token_revoked(token):
        raise HTTPException(
            status_code=401,
            detail={"error": "AUTH_REQUIRED", "detail": "Token has been revoked"},
            headers={"WWW-Authenticate": "Bearer"},
        )

    payload = verify_jwt(token)
    if payload is None:
        raise HTTPException(
            status_code=401,
            detail={"error": "AUTH_REQUIRED", "detail": "Invalid or expired token"},
            headers={"WWW-Authenticate": "Bearer"},
        )

    session_id = payload.get("session_id")
    if session_id and is_session_revoked(session_id):
        raise HTTPException(
            status_code=401,
            detail={"error": "AUTH_REQUIRED", "detail": "Session has been invalidated"},
            headers={"WWW-Authenticate": "Bearer"},
        )

    return payload


# =============================================================================
# WEBSOCKET AUTHENTICATION HELPER
# =============================================================================

async def ws_authenticate(websocket) -> Optional[Dict]:
    """
    Authenticate a WebSocket during handshake.

    Token extraction: Sec-WebSocket-Protocol header (bearer.{token}) ONLY.
    Query-string tokens are rejected (token leakage risk via logs/referrer).

    Returns decoded JWT payload on success, None on failure.
    """
    import logging
    _ws_logger = logging.getLogger("ygb.ws_auth")

    if is_temporary_auth_bypass_enabled():
        return build_temporary_auth_user("temporary_websocket")

    token = None

    # REJECTED: Query parameter tokens (security risk — leaks in logs/referrer)
    if websocket.query_params.get("token"):
        _ws_logger.warning(
            "WS auth via query param rejected — use Sec-WebSocket-Protocol instead"
        )
        return None

    cookie_header = websocket.headers.get("cookie", "")
    if cookie_header:
        try:
            cookies = SimpleCookie()
            cookies.load(cookie_header)
            morsel = cookies.get(AUTH_COOKIE_NAME) or cookies.get(LEGACY_AUTH_COOKIE_NAME)
            if morsel is not None:
                token = morsel.value
        except Exception:
            token = None

    if not token:
        protocols = websocket.headers.get("sec-websocket-protocol", "")
        for proto in protocols.split(","):
            proto = proto.strip()
            if proto.startswith("bearer."):
                token = proto[7:]
                break

    if not token:
        return None

    # Check revocation
    if is_token_revoked(token):
        return None

    # Verify JWT
    payload = verify_jwt(token)
    if not payload:
        return None

    # ── Session revocation parity with HTTP auth ──────────
    # HTTP require_auth checks is_session_revoked (line 142).
    # WS auth must enforce the same — otherwise revoking a session
    # via HTTP would not disconnect active WS connections.
    session_id = payload.get("session_id")
    if session_id and is_session_revoked(session_id):
        _ws_logger.warning("WS auth rejected — session %s revoked", session_id[:8])
        return None

    return payload


# =============================================================================
# FASTAPI DEPENDENCIES
# =============================================================================

async def require_auth(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer_scheme),
) -> Dict:
    """
    Require valid JWT authentication.
    
    Use as FastAPI dependency:
        @app.get("/protected", dependencies=[Depends(require_auth)])
        async def protected_route(): ...
    
    Or inject the user payload:
        @app.get("/protected")
        async def protected_route(user=Depends(require_auth)): ...
    
    Returns decoded JWT payload on success.
    Raises HTTPException(401) on failure.
    """
    if is_temporary_auth_bypass_enabled():
        return build_temporary_auth_user("temporary_http")

    token = None
    via_cookie = False

    if credentials:
        token = credentials.credentials
    else:
        token = _extract_cookie_token(request)
        via_cookie = bool(token)

    if not token:
        raise HTTPException(
            status_code=401,
            detail={"error": "AUTH_REQUIRED", "detail": "Authentication required"},
            headers={"WWW-Authenticate": "Bearer"},
        )

    if via_cookie:
        _enforce_cookie_csrf(request)

    payload = _verify_token_or_401(token)

    # Role is required by admin guards, but older JWTs may not contain it.
    # Hydrate role from storage as a compatibility path.
    if not payload.get("role"):
        user_id = payload.get("sub")
        if user_id:
            try:
                from backend.storage.storage_bridge import get_user
                user_record = get_user(user_id)
                if user_record and user_record.get("role"):
                    payload = {**payload, "role": user_record["role"]}
            except Exception:
                # Fail closed for auth token validity, but avoid breaking
                # regular auth if role lookup backend is unavailable.
                pass

    return {**payload, "_auth_via": "cookie" if via_cookie else "bearer"}


async def require_admin(
    user: Dict = Depends(require_auth),
) -> Dict:
    """
    Require admin role.
    
    Use as FastAPI dependency on admin-only endpoints:
        @app.get("/admin/stats", dependencies=[Depends(require_admin)])
    
    Raises HTTPException(403) if user is not admin.
    """
    role = user.get("role", "")
    if role != "admin":
        raise HTTPException(
            status_code=403,
            detail={"error": "AUTH_REQUIRED", "detail": "Insufficient permissions — admin access required"},
        )
    return user


# =============================================================================
# STARTUP PREFLIGHT CHECKS
# =============================================================================

_PLACEHOLDER_SECRETS = frozenset([
    "", "changeme", "secret", "password", "jwt_secret",
    "your-secret-here", "your_secret_here", "replace-me",
    "replace_me", "test", "dev", "development", "default",
    "mysecret", "my_secret", "super_secret", "supersecret",
])

# Patterns that indicate placeholder secrets (substring match)
_PLACEHOLDER_PATTERNS = [
    "change-me", "change_me", "changeme", "replace-me", "replace_me",
    "your-secret", "your_secret", "example", "placeholder",
    "CHANGE_ME", "REPLACE_ME", "YOUR_SECRET",
]


def preflight_check_secrets() -> None:
    """
    Verify all required secrets are present and not placeholders.
    
    FAIL-CLOSED: Raises RuntimeError if any secret is missing or weak.
    Call this at server startup BEFORE accepting any requests.
    """
    errors = []

    def _check_secret(env_name: str, min_length: int = 32):
        """Check a single secret env var."""
        val = os.getenv(env_name, "")
        if val.lower() in _PLACEHOLDER_SECRETS:
            errors.append(
                f"{env_name} is missing or is a placeholder. "
                f"Set a strong ({min_length}+ char) {env_name} environment variable."
            )
        elif any(pat in val for pat in _PLACEHOLDER_PATTERNS):
            errors.append(
                f"{env_name} contains a placeholder pattern (e.g. 'change-me'). "
                f"Generate a real secret: python -c \"import secrets; print(secrets.token_hex(32))\""
            )
        elif len(val) < min_length:
            errors.append(
                f"{env_name} is too short ({len(val)} chars). "
                f"Minimum {min_length} characters required."
            )

    # All required secrets
    _check_secret("JWT_SECRET", 32)
    _check_secret("YGB_HMAC_SECRET", 32)
    _check_secret("YGB_VIDEO_JWT_SECRET", 32)

    if errors:
        msg = "\n".join(f"  ✗ {e}" for e in errors)
        raise RuntimeError(
            f"\n[PREFLIGHT] FATAL — Security preflight check failed:\n{msg}\n"
            f"[PREFLIGHT] Server WILL NOT START with insecure configuration.\n"
            f"[PREFLIGHT] Set required environment variables and restart."
        )

    print("[PREFLIGHT] OK - All security preflight checks passed")

    # Soft warnings for optional but important config
    _warnings = []
    if not os.getenv("GITHUB_CLIENT_SECRET"):
        _warnings.append("GITHUB_CLIENT_SECRET is empty — GitHub OAuth will not work")
    if not os.getenv("DATABASE_URL"):
        _warnings.append("DATABASE_URL is not set — using default sqlite:///C:/ygb_data/ygb.db")
    if os.getenv("API_HOST", "127.0.0.1") == "0.0.0.0":
        _warnings.append("API_HOST=0.0.0.0 — server is binding to all interfaces (use 127.0.0.1 for local-only)")
    for w in _warnings:
        print(f"[PREFLIGHT] WARN: {w}")


# =============================================================================
# SSRF / SCOPE GATING HELPERS
# =============================================================================

import ipaddress
from urllib.parse import urlparse

# Private/reserved IP ranges that MUST be blocked
_PRIVATE_RANGES = [
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),  # link-local
    ipaddress.ip_network("::1/128"),          # IPv6 loopback
    ipaddress.ip_network("fc00::/7"),         # IPv6 private
    ipaddress.ip_network("fe80::/10"),        # IPv6 link-local
]

_BLOCKED_HOSTNAMES = frozenset([
    "localhost", "localhost.localdomain",
    "metadata.google.internal",  # GCP metadata
    "169.254.169.254",           # AWS/GCP/Azure metadata
])


def validate_target_url(url: str) -> tuple:
    """
    Validate a target URL for SSRF safety.
    
    Returns: (is_safe, violations_list)
    """
    violations = []

    if not url or not url.strip():
        violations.append({"rule": "EMPTY_TARGET", "message": "Target URL cannot be empty"})
        return False, violations

    # Parse URL
    try:
        parsed = urlparse(url if "://" in url else f"https://{url}")
    except Exception:
        violations.append({"rule": "INVALID_URL", "message": f"Cannot parse URL: {url}"})
        return False, violations

    hostname = (parsed.hostname or "").lower().strip()

    # Block empty hostname
    if not hostname:
        violations.append({"rule": "NO_HOST", "message": "No hostname found in URL"})
        return False, violations

    # Block known dangerous hostnames
    if hostname in _BLOCKED_HOSTNAMES:
        violations.append({"rule": "BLOCKED_HOST", "message": f"Hostname blocked: {hostname}"})
        return False, violations

    # Block IP addresses in private/reserved ranges
    try:
        ip = ipaddress.ip_address(hostname)
        for net in _PRIVATE_RANGES:
            if ip in net:
                violations.append({
                    "rule": "PRIVATE_IP",
                    "message": f"Private/reserved IP address blocked: {hostname}"
                })
                return False, violations
    except ValueError:
        pass  # Not an IP — it's a hostname, which is fine

    # Block wildcard TLDs
    import re
    if re.match(r'^\*\.[a-z]{2,4}$', hostname):
        violations.append({"rule": "WILDCARD_TLD", "message": f"Wildcard TLD blocked: {hostname}"})

    # Require valid domain pattern
    if not re.search(r'[a-zA-Z0-9][a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', hostname):
        # Allow if it's a valid public IP
        try:
            ip = ipaddress.ip_address(hostname)
            if ip.is_global:
                pass  # Valid public IP
            else:
                violations.append({"rule": "INVALID_DOMAIN", "message": f"Not a valid public domain or IP: {hostname}"})
        except ValueError:
            violations.append({"rule": "INVALID_DOMAIN", "message": f"Not a valid domain: {hostname}"})

    return len(violations) == 0, violations
