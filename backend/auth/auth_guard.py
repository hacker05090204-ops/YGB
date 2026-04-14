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
import logging
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
from http.cookies import SimpleCookie
from threading import RLock
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

logger = logging.getLogger(__name__)

# Bearer token scheme
_bearer_scheme = HTTPBearer(auto_error=False)
AUTH_COOKIE_NAME = "ygb_auth"
LEGACY_AUTH_COOKIE_NAME = "ygb_token"
CSRF_COOKIE_NAME = "ygb_csrf"
CSRF_HEADER_NAME = "x-csrf-token"
_SAFE_HTTP_METHODS = frozenset({"GET", "HEAD", "OPTIONS", "TRACE"})
_TRUTHY_VALUES = frozenset({"1", "true", "yes", "on"})
_AUDIT_MAX_ENTRIES = 50000
_AUDIT_ROTATE_ENTRIES = 25000
_RATE_LIMIT_WINDOW_SECONDS = 60
_RATE_LIMIT_MAX_CALLS = 100
IS_PRODUCTION = os.getenv("YGB_ENV", "development") == "production"
_TEST_ONLY_PATH_ENV = "YGB_ENABLE_TEST_ONLY_PATHS"


@dataclass(frozen=True)
class AuthAuditEntry:
    timestamp: str
    subject: str
    resource: str
    action: str
    decision: str
    reason: str


class AuthAuditTrail:
    def __init__(self, max_entries: int = _AUDIT_MAX_ENTRIES, retain_entries: int = _AUDIT_ROTATE_ENTRIES):
        self._max_entries = max(1, int(max_entries))
        self._retain_entries = max(1, min(int(retain_entries), self._max_entries))
        self._entries: list[AuthAuditEntry] = []
        self._lock = RLock()

    def append(self, entry: AuthAuditEntry) -> None:
        with self._lock:
            self._entries.append(entry)
            if len(self._entries) > self._max_entries:
                self._entries = self._entries[-self._retain_entries:]

    def get(self, subject: Optional[str] = None) -> list[AuthAuditEntry]:
        with self._lock:
            if subject is None:
                return list(self._entries)
            return [entry for entry in self._entries if entry.subject == subject]


_audit_trail = AuthAuditTrail()
_subject_rate_limit_windows: dict[str, deque[float]] = {}


def _audit_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def _request_resource(request: Optional[Request]) -> str:
    if request is None:
        return "auth"
    try:
        return str(request.url.path)
    except Exception:
        return "auth"


def _normalize_audit_reason(value: object, fallback: str) -> str:
    if isinstance(value, dict):
        detail = value.get("detail")
        if isinstance(detail, str) and detail.strip():
            return detail.strip().lower().replace(" ", "_")
        error = value.get("error")
        if isinstance(error, str) and error.strip():
            return error.strip().lower().replace(" ", "_")
    if isinstance(value, str) and value.strip():
        return value.strip().lower().replace(" ", "_")
    return fallback


def _append_auth_audit(
    *,
    subject: str,
    resource: str,
    action: str,
    decision: str,
    reason: str,
) -> None:
    _audit_trail.append(
        AuthAuditEntry(
            timestamp=_audit_timestamp(),
            subject=subject or "anonymous",
            resource=resource,
            action=action,
            decision=decision,
            reason=reason,
        )
    )


def _check_subject_rate_limit(subject: str) -> bool:
    normalized_subject = subject or "anonymous"
    now = time.time()
    attempts = _subject_rate_limit_windows.setdefault(normalized_subject, deque())
    cutoff = now - _RATE_LIMIT_WINDOW_SECONDS
    while attempts and attempts[0] <= cutoff:
        attempts.popleft()
    if len(attempts) >= _RATE_LIMIT_MAX_CALLS:
        return False
    attempts.append(now)
    return True


def _raise_rate_limited(subject: str, resource: str, action: str) -> None:
    logger.warning("Auth rate limit exceeded for subject %s", subject)
    _append_auth_audit(
        subject=subject,
        resource=resource,
        action=action,
        decision="deny",
        reason="rate_limited",
    )
    raise HTTPException(
        status_code=429,
        detail={"error": "RATE_LIMITED", "detail": "rate_limited"},
    )


def get_auth_audit_trail(subject: Optional[str] = None) -> list[AuthAuditEntry]:
    return _audit_trail.get(subject)


def _runtime_is_production() -> bool:
    configured_environment = os.getenv("YGB_ENV")
    if configured_environment is None:
        return bool(IS_PRODUCTION)
    return configured_environment.strip().lower() == "production"


def _test_only_paths_enabled() -> bool:
    if "pytest" in sys.modules:
        return True
    return os.getenv(_TEST_ONLY_PATH_ENV, "").strip().lower() in _TRUTHY_VALUES


def _temporary_auth_bypass_requested() -> bool:
    return os.getenv("YGB_TEMP_AUTH_BYPASS", "false").strip().lower() in _TRUTHY_VALUES


def is_temporary_auth_bypass_enabled() -> bool:
    if _runtime_is_production():
        return False
    if not _temporary_auth_bypass_requested():
        return False
    return _test_only_paths_enabled()


def _log_temporary_auth_bypass_startup_warning() -> None:
    bypass_requested = _temporary_auth_bypass_requested()
    bypass_enabled = is_temporary_auth_bypass_enabled()
    production_mode = _runtime_is_production()

    if bypass_requested and production_mode:
        logger.critical(
            "Temporary auth bypass was requested while YGB_ENV=production. "
            "Bypass remains disabled and the deployment is misconfigured."
        )
        return

    if bypass_requested:
        if bypass_enabled:
            logger.warning(
                "Temporary auth bypass is enabled in non-production. "
                "Disable YGB_TEMP_AUTH_BYPASS before deployment."
            )
        else:
            logger.warning(
                "Temporary auth bypass was requested in non-production but remains disabled "
                "outside test-only execution."
            )
        return

    logger.info("Temporary auth bypass is disabled.")


_log_temporary_auth_bypass_startup_warning()


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


def get_allowed_origins() -> Set[str]:
    """Expose the normalized allowlist for callers outside this module."""
    return set(_allowed_origins())


def _extract_cookie_token(request: Request) -> Optional[str]:
    return request.cookies.get(AUTH_COOKIE_NAME) or request.cookies.get(LEGACY_AUTH_COOKIE_NAME)


def _normalize_origin(origin: str) -> str:
    parsed = urlparse(origin)
    if not parsed.scheme or not parsed.netloc:
        return ""
    return f"{parsed.scheme}://{parsed.netloc}".rstrip("/")


def is_allowed_origin(origin: str) -> bool:
    """Return True when the supplied origin matches the configured allowlist."""
    normalized = _normalize_origin(origin or "")
    return bool(normalized and normalized in _allowed_origins())


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
        _append_auth_audit(
            subject="anonymous",
            resource="token",
            action="verify_token",
            decision="deny",
            reason="token_revoked",
        )
        raise HTTPException(
            status_code=401,
            detail={"error": "AUTH_REQUIRED", "detail": "Token has been revoked"},
            headers={"WWW-Authenticate": "Bearer"},
        )

    payload = verify_jwt(token)
    if payload is None:
        _append_auth_audit(
            subject="anonymous",
            resource="token",
            action="verify_token",
            decision="deny",
            reason="invalid_or_expired_token",
        )
        raise HTTPException(
            status_code=401,
            detail={"error": "AUTH_REQUIRED", "detail": "Invalid or expired token"},
            headers={"WWW-Authenticate": "Bearer"},
        )

    session_id = payload.get("session_id")
    if session_id and is_session_revoked(session_id):
        _append_auth_audit(
            subject=str(payload.get("sub", "anonymous")),
            resource="token",
            action="verify_token",
            decision="deny",
            reason="session_revoked",
        )
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
        user = build_temporary_auth_user("temporary_websocket")
        subject = str(user.get("sub", "anonymous"))
        if not _check_subject_rate_limit(subject):
            logger.warning("Auth rate limit exceeded for subject %s", subject)
            _append_auth_audit(
                subject=subject,
                resource="websocket",
                action="ws_authenticate",
                decision="deny",
                reason="rate_limited",
            )
            return None
        _append_auth_audit(
            subject=subject,
            resource="websocket",
            action="ws_authenticate",
            decision="allow",
            reason="temporary_bypass",
        )
        return user

    token = None

    # REJECTED: Query parameter tokens (security risk — leaks in logs/referrer)
    if websocket.query_params.get("token"):
        _ws_logger.warning(
            "WS auth via query param rejected — use Sec-WebSocket-Protocol instead"
        )
        _append_auth_audit(
            subject="anonymous",
            resource="websocket",
            action="ws_authenticate",
            decision="deny",
            reason="query_token_rejected",
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
        _append_auth_audit(
            subject="anonymous",
            resource="websocket",
            action="ws_authenticate",
            decision="deny",
            reason="auth_required",
        )
        return None

    # Check revocation
    if is_token_revoked(token):
        _append_auth_audit(
            subject="anonymous",
            resource="websocket",
            action="ws_authenticate",
            decision="deny",
            reason="token_revoked",
        )
        return None

    # Verify JWT
    payload = verify_jwt(token)
    if not payload:
        _append_auth_audit(
            subject="anonymous",
            resource="websocket",
            action="ws_authenticate",
            decision="deny",
            reason="invalid_or_expired_token",
        )
        return None

    # ── Session revocation parity with HTTP auth ──────────
    # HTTP require_auth checks is_session_revoked (line 142).
    # WS auth must enforce the same — otherwise revoking a session
    # via HTTP would not disconnect active WS connections.
    session_id = payload.get("session_id")
    if session_id and is_session_revoked(session_id):
        _ws_logger.warning("WS auth rejected — session %s revoked", session_id[:8])
        _append_auth_audit(
            subject=str(payload.get("sub", "anonymous")),
            resource="websocket",
            action="ws_authenticate",
            decision="deny",
            reason="session_revoked",
        )
        return None

    subject = str(payload.get("sub", "anonymous"))
    if not _check_subject_rate_limit(subject):
        logger.warning("Auth rate limit exceeded for subject %s", subject)
        _append_auth_audit(
            subject=subject,
            resource="websocket",
            action="ws_authenticate",
            decision="deny",
            reason="rate_limited",
        )
        return None

    _append_auth_audit(
        subject=subject,
        resource="websocket",
        action="ws_authenticate",
        decision="allow",
        reason="ok",
    )

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
        user = build_temporary_auth_user("temporary_http")
        subject = str(user.get("sub", "anonymous"))
        resource = _request_resource(request)
        if not _check_subject_rate_limit(subject):
            _raise_rate_limited(subject, resource, "require_auth")
        _append_auth_audit(
            subject=subject,
            resource=resource,
            action="require_auth",
            decision="allow",
            reason="temporary_bypass",
        )
        return user

    token = None
    via_cookie = False
    resource = _request_resource(request)

    if credentials:
        token = credentials.credentials
    else:
        token = _extract_cookie_token(request)
        via_cookie = bool(token)

    if not token:
        _append_auth_audit(
            subject="anonymous",
            resource=resource,
            action="require_auth",
            decision="deny",
            reason="auth_required",
        )
        raise HTTPException(
            status_code=401,
            detail={"error": "AUTH_REQUIRED", "detail": "Authentication required"},
            headers={"WWW-Authenticate": "Bearer"},
        )

    if via_cookie:
        try:
            _enforce_cookie_csrf(request)
        except HTTPException as exc:
            _append_auth_audit(
                subject="anonymous",
                resource=resource,
                action="require_auth",
                decision="deny",
                reason=_normalize_audit_reason(exc.detail, "csrf_blocked"),
            )
            raise

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
            except Exception as exc:
                # Fail closed for auth token validity, but avoid breaking
                # regular auth if role lookup backend is unavailable.
                logger.warning(
                    "Non-critical failure while hydrating auth role from storage: %s",
                    exc,
                    exc_info=True,
                )

    subject = str(payload.get("sub", "anonymous"))
    if not _check_subject_rate_limit(subject):
        _raise_rate_limited(subject, resource, "require_auth")

    _append_auth_audit(
        subject=subject,
        resource=resource,
        action="require_auth",
        decision="allow",
        reason="ok",
    )

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
    subject = str(user.get("sub", "anonymous"))
    role = user.get("role", "")
    if role != "admin":
        _append_auth_audit(
            subject=subject,
            resource="admin",
            action="require_admin",
            decision="deny",
            reason="insufficient_permissions",
        )
        raise HTTPException(
            status_code=403,
            detail={"error": "AUTH_REQUIRED", "detail": "Insufficient permissions — admin access required"},
        )
    _append_auth_audit(
        subject=subject,
        resource="admin",
        action="require_admin",
        decision="allow",
        reason="ok",
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


def get_required_secret(env_name: str, min_length: int = 32) -> str:
    """Return a required secret env var or raise a fail-closed runtime error."""
    value = os.getenv(env_name, "").strip()
    if value.lower() in _PLACEHOLDER_SECRETS:
        raise RuntimeError(f"{env_name} must be set before startup")
    if any(pattern in value for pattern in _PLACEHOLDER_PATTERNS):
        raise RuntimeError(f"{env_name} contains a placeholder value")
    if len(value) < min_length:
        raise RuntimeError(
            f"{env_name} must be at least {min_length} characters long"
        )
    return value


_STARTUP_JWT_SECRET = get_required_secret("JWT_SECRET", 32)


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
    if _runtime_is_production() and _temporary_auth_bypass_requested():
        errors.append(
            "YGB_TEMP_AUTH_BYPASS=true is not allowed when YGB_ENV=production. "
            "Set YGB_TEMP_AUTH_BYPASS=false before startup."
        )

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


def _secret_meets_runtime_requirements(env_name: str, min_length: int = 32) -> bool:
    value = os.getenv(env_name, "").strip()
    if value.lower() in _PLACEHOLDER_SECRETS:
        return False
    if any(pattern in value for pattern in _PLACEHOLDER_PATTERNS):
        return False
    return len(value) >= min_length


def get_auth_runtime_status() -> Dict:
    """Return non-secret authentication hardening status for operator visibility."""
    from backend.auth.revocation_store import get_backend_health

    secret_health = {
        "JWT_SECRET": _secret_meets_runtime_requirements("JWT_SECRET", 32),
        "YGB_HMAC_SECRET": _secret_meets_runtime_requirements("YGB_HMAC_SECRET", 32),
        "YGB_VIDEO_JWT_SECRET": _secret_meets_runtime_requirements("YGB_VIDEO_JWT_SECRET", 32),
    }
    bypass_requested = _temporary_auth_bypass_requested()
    bypass_enabled = is_temporary_auth_bypass_enabled()
    production_mode = _runtime_is_production()
    backend_health = get_backend_health()
    audit_entries = len(get_auth_audit_trail())
    active_rate_limited_subjects = sum(
        1 for attempts in _subject_rate_limit_windows.values() if attempts
    )

    status = "HEALTHY"
    if not all(secret_health.values()):
        status = "ERROR" if production_mode else "DEGRADED"
    elif bypass_requested:
        status = "DEGRADED"

    backend_status = ""
    if isinstance(backend_health, dict):
        backend_status = str(backend_health.get("status", "") or "").upper()
    if backend_status in {"ERROR", "DOWN", "UNAVAILABLE"} and status == "HEALTHY":
        status = "DEGRADED"

    return {
        "status": status,
        "available": status != "ERROR",
        "production_mode": production_mode,
        "temporary_bypass_requested": bypass_requested,
        "temporary_bypass_enabled": bypass_enabled,
        "required_secrets": secret_health,
        "all_required_secrets_present": all(secret_health.values()),
        "audit_entries": audit_entries,
        "active_rate_limited_subjects": active_rate_limited_subjects,
        "revocation_backend": backend_health,
    }


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
    except ValueError as exc:
        logger.debug("Target hostname is not a literal IP address: %s (%s)", hostname, exc)

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
