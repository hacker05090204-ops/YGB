"""
Revocation Store — Redis-backed token/session revocation with TTL.

Backend: controlled by REVOCATION_BACKEND env var.
    "redis"     -> Redis-backed (fail-closed if unavailable)
    "memory"    -> In-memory (default, lost on restart)

Redis keys:
    revoked:token:{sha256_hash}    TTL = REVOCATION_TTL_SECONDS
    revoked:session:{session_id}   TTL = REVOCATION_TTL_SECONDS

Fail-closed: if Redis is required and unreachable, revocation checks
return True (i.e. treat as revoked -> deny access).
"""

import hashlib
import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)

_DEFAULT_TTL = 86400  # 24 hours


# ---------------------------------------------------------------------------
# Abstract store interface
# ---------------------------------------------------------------------------

class _MemoryStore:
    """In-memory revocation store (default)."""

    def __init__(self) -> None:
        self._tokens: set = set()
        self._sessions: set = set()

    def revoke_token(self, token_hash: str, ttl: int = _DEFAULT_TTL) -> None:
        self._tokens.add(token_hash)

    def revoke_session(self, session_id: str, ttl: int = _DEFAULT_TTL) -> None:
        self._sessions.add(session_id)

    def is_token_revoked(self, token_hash: str) -> bool:
        return token_hash in self._tokens

    def is_session_revoked(self, session_id: str) -> bool:
        return session_id in self._sessions

    def clear(self) -> None:
        """For testing: simulate process restart."""
        self._tokens.clear()
        self._sessions.clear()


class _RedisStore:
    """Redis-backed revocation store with fail-closed semantics."""

    def __init__(self, redis_url: str) -> None:
        import redis as _redis_lib
        self._url = redis_url
        self._client = None
        try:
            self._client = _redis_lib.Redis.from_url(
                redis_url,
                socket_connect_timeout=2,
                socket_timeout=2,
                decode_responses=True,
            )
            self._client.ping()
            logger.info("[REVOCATION] Redis connected: %s", redis_url)
        except Exception as exc:
            logger.error("[REVOCATION] Redis connection FAILED: %s", exc)
            self._client = None

    def _key_token(self, token_hash: str) -> str:
        return f"revoked:token:{token_hash}"

    def _key_session(self, session_id: str) -> str:
        return f"revoked:session:{session_id}"

    def _is_available(self) -> bool:
        if self._client is None:
            return False
        try:
            self._client.ping()
            return True
        except Exception:
            return False

    def revoke_token(self, token_hash: str, ttl: int = _DEFAULT_TTL) -> None:
        if not self._is_available():
            logger.error("[REVOCATION] Redis unavailable for token revocation")
            return
        self._client.setex(self._key_token(token_hash), ttl, "1")

    def revoke_session(self, session_id: str, ttl: int = _DEFAULT_TTL) -> None:
        if not self._is_available():
            logger.error("[REVOCATION] Redis unavailable for session revocation")
            return
        self._client.setex(self._key_session(session_id), ttl, "1")

    def is_token_revoked(self, token_hash: str) -> bool:
        """Fail-closed: if Redis is down, treat as revoked."""
        if not self._is_available():
            logger.warning("[REVOCATION] Redis unavailable — fail-closed")
            return True
        return bool(self._client.exists(self._key_token(token_hash)))

    def is_session_revoked(self, session_id: str) -> bool:
        """Fail-closed: if Redis is down, treat as revoked."""
        if not self._is_available():
            logger.warning("[REVOCATION] Redis unavailable — fail-closed")
            return True
        return bool(self._client.exists(self._key_session(session_id)))

    def clear(self) -> None:
        """For testing: flush revocation keys only."""
        if self._is_available():
            for key in self._client.scan_iter("revoked:*"):
                self._client.delete(key)


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_store = None


def _get_store():
    global _store
    if _store is not None:
        return _store

    backend = os.getenv("REVOCATION_BACKEND", "memory").lower()
    if backend == "redis":
        redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
        _store = _RedisStore(redis_url)
    else:
        _store = _MemoryStore()

    return _store


def reset_store() -> None:
    """Reset module-level store. Used in tests to simulate process restart."""
    global _store
    _store = None


# ---------------------------------------------------------------------------
# Public API (drop-in replacement for auth_guard inline functions)
# ---------------------------------------------------------------------------

def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def revoke_token(token: str, ttl: int = _DEFAULT_TTL) -> None:
    """Revoke a bearer token."""
    _get_store().revoke_token(_hash_token(token), ttl)


def revoke_session(session_id: str, ttl: int = _DEFAULT_TTL) -> None:
    """Revoke a session."""
    _get_store().revoke_session(session_id, ttl)


def is_token_revoked(token: str) -> bool:
    """Check if a token has been revoked."""
    return _get_store().is_token_revoked(_hash_token(token))


def is_session_revoked(session_id: str) -> bool:
    """Check if a session has been revoked."""
    return _get_store().is_session_revoked(session_id)
