"""
Revocation Store — Redis-backed token/session revocation with TTL.

Backend: controlled by REVOCATION_BACKEND env var.
    "redis"     -> Redis-backed (fail-closed if unavailable)
    "file"      -> File-backed (default, survives restart, no expiration)
    "memory"    -> In-memory (lost on restart)

Redis keys:
    revoked:token:{sha256_hash}    TTL = REVOCATION_TTL_SECONDS
    revoked:session:{session_id}   TTL = REVOCATION_TTL_SECONDS

Fail-closed: if Redis is required and unreachable, revocation checks
return True (i.e. treat as revoked -> deny access).
"""

import hashlib
import json
import logging
import os
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_DEFAULT_TTL = 86400  # 24 hours


class RevocationUnavailableError(RuntimeError):
    """Raised when no revocation backend can safely service a request."""


# ---------------------------------------------------------------------------
# Abstract store interface
# ---------------------------------------------------------------------------

class _MemoryStore:
    """In-memory revocation store."""

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


class _FileStore:
    """File-backed revocation store — survives process restarts.

    Stores revocations as a JSON file on disk.
    No TTL enforcement (revocations persist until manually cleared).
    Recommended as a durable fallback when Redis is unavailable.
    """

    def __init__(self, path: Optional[str] = None) -> None:
        default_path = str(
            Path(__file__).parent.parent.parent / "secure_data" / "revocations.json"
        )
        self._path = Path(path or os.getenv("REVOCATION_FILE_PATH", default_path))
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            logger.error("[REVOCATION] File backend directory create failed: %s", exc)
            raise RevocationUnavailableError(
                f"Revocation file backend unavailable at {self._path}: {exc}"
            ) from exc
        self._data = self._load()

    def _load(self) -> dict:
        if self._path.exists():
            try:
                return json.loads(self._path.read_text(encoding="utf-8"))
            except json.JSONDecodeError as exc:
                logger.warning("[REVOCATION] File load failed, starting empty: %s", exc)
            except OSError as exc:
                logger.error("[REVOCATION] File load failed: %s", exc)
                raise RevocationUnavailableError(
                    f"Revocation file backend unreadable at {self._path}: {exc}"
                ) from exc
        return {"tokens": [], "sessions": []}

    def _save(self) -> None:
        try:
            self._path.write_text(
                json.dumps(self._data, indent=2), encoding="utf-8"
            )
        except OSError as exc:
            logger.error("[REVOCATION] File save failed: %s", exc)
            raise RevocationUnavailableError(
                f"Revocation file backend unavailable at {self._path}: {exc}"
            ) from exc

    def revoke_token(self, token_hash: str, ttl: int = _DEFAULT_TTL) -> None:
        if token_hash not in self._data["tokens"]:
            self._data["tokens"].append(token_hash)
            self._save()

    def revoke_session(self, session_id: str, ttl: int = _DEFAULT_TTL) -> None:
        if session_id not in self._data["sessions"]:
            self._data["sessions"].append(session_id)
            self._save()

    def is_token_revoked(self, token_hash: str) -> bool:
        return token_hash in self._data["tokens"]

    def is_session_revoked(self, session_id: str) -> bool:
        return session_id in self._data["sessions"]

    def clear(self) -> None:
        """For testing: clear all revocations."""
        self._data = {"tokens": [], "sessions": []}
        self._save()


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


class _RedisFileFallbackStore:
    """Redis-backed revocation with durable file fallback."""

    def __init__(
        self,
        redis_store: _RedisStore,
        file_store: Optional[_FileStore],
        file_error: Optional[Exception] = None,
    ) -> None:
        self._redis_store = redis_store
        self._file_store = file_store
        self._file_error = file_error

    def _redis_available(self) -> bool:
        try:
            return self._redis_store._is_available()
        except Exception as exc:
            logger.error("[REVOCATION] Redis availability check failed: %s", exc)
            return False

    def _raise_unavailable(self, action: str, cause: Optional[Exception] = None) -> None:
        message = (
            "Redis revocation backend is unavailable and file fallback is unavailable; "
            f"cannot {action}."
        )
        if cause is not None:
            raise RevocationUnavailableError(message) from cause
        raise RevocationUnavailableError(message)

    def _record_file_error(self, errors: list[Exception]) -> None:
        if self._file_error is not None:
            errors.append(self._file_error)

    def revoke_token(self, token_hash: str, ttl: int = _DEFAULT_TTL) -> None:
        redis_success = False
        file_success = False
        errors: list[Exception] = []

        if self._redis_available():
            try:
                self._redis_store.revoke_token(token_hash, ttl)
                redis_success = True
            except Exception as exc:
                logger.error("[REVOCATION] Redis token revoke failed: %s", exc)
                errors.append(exc)
        else:
            logger.warning("[REVOCATION] Redis unavailable for token revoke — using file fallback")

        if self._file_store is not None:
            try:
                self._file_store.revoke_token(token_hash, ttl)
                file_success = True
            except RevocationUnavailableError as exc:
                logger.error("[REVOCATION] File fallback token revoke failed: %s", exc)
                errors.append(exc)
        else:
            self._record_file_error(errors)

        if redis_success or file_success:
            return

        self._raise_unavailable("revoke token", errors[0] if errors else None)

    def revoke_session(self, session_id: str, ttl: int = _DEFAULT_TTL) -> None:
        redis_success = False
        file_success = False
        errors: list[Exception] = []

        if self._redis_available():
            try:
                self._redis_store.revoke_session(session_id, ttl)
                redis_success = True
            except Exception as exc:
                logger.error("[REVOCATION] Redis session revoke failed: %s", exc)
                errors.append(exc)
        else:
            logger.warning("[REVOCATION] Redis unavailable for session revoke — using file fallback")

        if self._file_store is not None:
            try:
                self._file_store.revoke_session(session_id, ttl)
                file_success = True
            except RevocationUnavailableError as exc:
                logger.error("[REVOCATION] File fallback session revoke failed: %s", exc)
                errors.append(exc)
        else:
            self._record_file_error(errors)

        if redis_success or file_success:
            return

        self._raise_unavailable("revoke session", errors[0] if errors else None)

    def is_token_revoked(self, token_hash: str) -> bool:
        results: list[bool] = []
        errors: list[Exception] = []

        if self._redis_available():
            try:
                results.append(self._redis_store.is_token_revoked(token_hash))
            except Exception as exc:
                logger.error("[REVOCATION] Redis token lookup failed: %s", exc)
                errors.append(exc)
        else:
            logger.warning("[REVOCATION] Redis unavailable for token lookup — checking file fallback")

        if self._file_store is not None:
            try:
                results.append(self._file_store.is_token_revoked(token_hash))
            except RevocationUnavailableError as exc:
                logger.error("[REVOCATION] File fallback token lookup failed: %s", exc)
                errors.append(exc)
        elif not results:
            self._record_file_error(errors)

        if results:
            return any(results)

        self._raise_unavailable("check token revocation", errors[0] if errors else None)

    def is_session_revoked(self, session_id: str) -> bool:
        results: list[bool] = []
        errors: list[Exception] = []

        if self._redis_available():
            try:
                results.append(self._redis_store.is_session_revoked(session_id))
            except Exception as exc:
                logger.error("[REVOCATION] Redis session lookup failed: %s", exc)
                errors.append(exc)
        else:
            logger.warning("[REVOCATION] Redis unavailable for session lookup — checking file fallback")

        if self._file_store is not None:
            try:
                results.append(self._file_store.is_session_revoked(session_id))
            except RevocationUnavailableError as exc:
                logger.error("[REVOCATION] File fallback session lookup failed: %s", exc)
                errors.append(exc)
        elif not results:
            self._record_file_error(errors)

        if results:
            return any(results)

        self._raise_unavailable("check session revocation", errors[0] if errors else None)

    def clear(self) -> None:
        cleared = False
        errors: list[Exception] = []

        if self._redis_available():
            try:
                self._redis_store.clear()
                cleared = True
            except Exception as exc:
                logger.error("[REVOCATION] Redis clear failed: %s", exc)
                errors.append(exc)

        if self._file_store is not None:
            try:
                self._file_store.clear()
                cleared = True
            except RevocationUnavailableError as exc:
                logger.error("[REVOCATION] File fallback clear failed: %s", exc)
                errors.append(exc)
        elif not cleared:
            self._record_file_error(errors)

        if cleared:
            return

        self._raise_unavailable("clear revocations", errors[0] if errors else None)


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_store = None


def _get_store():
    global _store
    if _store is not None:
        return _store

    backend = os.getenv("REVOCATION_BACKEND", "file").lower()
    if backend == "redis":
        redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
        redis_store = _RedisStore(redis_url)
        file_store = None
        file_error = None
        try:
            file_store = _FileStore()
        except RevocationUnavailableError as exc:
            logger.error("[REVOCATION] File fallback initialization failed: %s", exc)
            file_error = exc
        _store = _RedisFileFallbackStore(redis_store, file_store=file_store, file_error=file_error)
    elif backend == "file":
        _store = _FileStore()
    else:
        _store = _MemoryStore()

    return _store


def reset_store() -> None:
    """Reset module-level store. Used in tests to simulate process restart."""
    global _store
    _store = None


def get_backend_health() -> dict:
    """Return health status of the revocation backend for monitoring."""
    store = _get_store()
    backend = os.getenv("REVOCATION_BACKEND", "file").lower()
    health = {
        "backend": backend,
        "type": type(store).__name__,
        "available": True,
    }
    if isinstance(store, _RedisStore):
        health["available"] = store._is_available()
        health["fail_mode"] = "closed"
    elif isinstance(store, _RedisFileFallbackStore):
        health["available"] = store._redis_available() or store._file_store is not None
        health["fail_mode"] = "closed"
        health["redis_available"] = store._redis_available()
        health["file_fallback_available"] = store._file_store is not None
        if store._file_store is not None:
            health["file_path"] = str(store._file_store._path)
        if store._file_error is not None:
            health["file_error"] = str(store._file_error)
    elif isinstance(store, _FileStore):
        health["file_path"] = str(store._path)
        health["file_exists"] = store._path.exists()
    elif isinstance(store, _MemoryStore):
        health["warning"] = "In-memory store — revocations lost on restart"
    return health


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
