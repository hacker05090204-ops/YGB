# Phase-46: Mutual Exclusion Contract Engine
"""Vector-level locks, pre-browser enforcement, deterministic blocking."""

from dataclasses import dataclass
from enum import Enum
from typing import Dict, Optional, List
import uuid
from datetime import datetime


class LockState(Enum):
    """CLOSED ENUM - 5 members"""
    FREE = "FREE"
    HELD = "HELD"
    PENDING = "PENDING"
    EXPIRED = "EXPIRED"
    DENIED = "DENIED"


class LockScope(Enum):
    """CLOSED ENUM - 4 members"""
    VECTOR = "VECTOR"
    TARGET = "TARGET"
    GLOBAL = "GLOBAL"
    SESSION = "SESSION"


class LockDecision(Enum):
    """CLOSED ENUM - 4 members"""
    GRANT = "GRANT"
    DENY = "DENY"
    WAIT = "WAIT"
    REVOKE = "REVOKE"


@dataclass(frozen=True)
class LockRequest:
    """Frozen dataclass for lock request."""
    request_id: str
    holder_id: str
    resource_id: str
    scope: LockScope
    timestamp: str
    ttl_seconds: int


@dataclass(frozen=True)
class Lock:
    """Frozen dataclass for an active lock."""
    lock_id: str
    holder_id: str
    resource_id: str
    scope: LockScope
    acquired_at: str
    expires_at: str
    state: LockState


@dataclass(frozen=True)
class LockResult:
    """Frozen dataclass for lock operation result."""
    request_id: str
    decision: LockDecision
    lock: Optional[Lock]
    reason: str


# Global lock registry (simulated - in real impl would be persistent)
_lock_registry: Dict[str, Lock] = {}


def check_lock_available(resource_id: str, scope: LockScope) -> bool:
    """Check if a lock is available."""
    key = f"{scope.value}:{resource_id}"
    if key not in _lock_registry:
        return True
    
    existing = _lock_registry[key]
    if existing.state in [LockState.FREE, LockState.EXPIRED]:
        return True
    
    return False


def acquire_lock(request: LockRequest) -> LockResult:
    """Attempt to acquire a lock. DENY-BY-DEFAULT."""
    key = f"{request.scope.value}:{request.resource_id}"
    
    # Check if lock already held
    if not check_lock_available(request.resource_id, request.scope):
        return LockResult(
            request_id=request.request_id,
            decision=LockDecision.DENY,
            lock=None,
            reason="Resource already locked",
        )
    
    # Grant lock
    lock = Lock(
        lock_id=f"LCK-{uuid.uuid4().hex[:16].upper()}",
        holder_id=request.holder_id,
        resource_id=request.resource_id,
        scope=request.scope,
        acquired_at=request.timestamp,
        expires_at=request.timestamp,  # Would add TTL in real impl
        state=LockState.HELD,
    )
    
    _lock_registry[key] = lock
    
    return LockResult(
        request_id=request.request_id,
        decision=LockDecision.GRANT,
        lock=lock,
        reason="Lock acquired",
    )


def release_lock(resource_id: str, scope: LockScope, holder_id: str) -> bool:
    """Release a held lock."""
    key = f"{scope.value}:{resource_id}"
    
    if key not in _lock_registry:
        return False
    
    existing = _lock_registry[key]
    if existing.holder_id != holder_id:
        return False  # Cannot release someone else's lock
    
    del _lock_registry[key]
    return True


def clear_all_locks():
    """Clear all locks (for testing)."""
    _lock_registry.clear()
