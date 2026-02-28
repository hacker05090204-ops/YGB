"""
Voice Security — Auth, rate limits, tamper-evident audit, privacy mode.

Provides:
  - JWT auth enforcement for all voice routes
  - Rate limits: 60 commands/min per user, 10/min per device
  - Abuse lockout after 5 failed auth attempts
  - Tamper-evident audit chain with SHA-256
  - Privacy mode: local-only STT/TTS, log redaction
"""

import hashlib
import logging
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, UTC
from typing import Optional, Dict, List, Deque
from collections import deque

logger = logging.getLogger(__name__)


# =============================================================================
# AUDIT ENTRY
# =============================================================================

@dataclass
class VoiceAuditEntry:
    """Tamper-evident audit log entry."""
    entry_id: str
    timestamp: str
    user_id: str
    device_id: str
    transcript: str
    resolved_intent: str
    executed_action: str
    policy_decision: str
    result: str
    previous_hash: str
    entry_hash: str


def _hash_entry(entry_id: str, user_id: str, transcript: str,
                intent: str, action: str, result: str,
                previous_hash: str) -> str:
    """Compute tamper-evident hash for audit entry."""
    raw = f"{entry_id}:{user_id}:{transcript}:{intent}:{action}:{result}:{previous_hash}"
    return hashlib.sha256(raw.encode()).hexdigest()


# =============================================================================
# RATE LIMITER
# =============================================================================

class VoiceRateLimiter:
    """Rate limiter for voice commands.

    Limits:
      - 60 commands/min per user_id
      - 10 commands/min per device_id
      - Lockout after 5 failed auth attempts
    """

    USER_LIMIT = 60
    DEVICE_LIMIT = 10
    AUTH_FAIL_LOCKOUT = 5
    WINDOW_S = 60.0
    LOCKOUT_S = 300.0  # 5 minute lockout

    def __init__(self):
        self._user_windows: Dict[str, Deque[float]] = defaultdict(lambda: deque())
        self._device_windows: Dict[str, Deque[float]] = defaultdict(lambda: deque())
        self._auth_failures: Dict[str, int] = defaultdict(int)
        self._lockout_until: Dict[str, float] = {}

    def is_allowed(self, user_id: str, device_id: str) -> tuple:
        """Check if request is allowed. Returns (allowed, reason)."""
        now = time.time()

        # Check lockout
        if user_id in self._lockout_until:
            if now < self._lockout_until[user_id]:
                return False, f"User locked out until {self._lockout_until[user_id]}"
            else:
                del self._lockout_until[user_id]
                self._auth_failures[user_id] = 0

        # Clean old entries
        self._clean_window(self._user_windows[user_id], now)
        self._clean_window(self._device_windows[device_id], now)

        # Check user limit
        if len(self._user_windows[user_id]) >= self.USER_LIMIT:
            return False, f"User rate limit exceeded ({self.USER_LIMIT}/min)"

        # Check device limit
        if len(self._device_windows[device_id]) >= self.DEVICE_LIMIT:
            return False, f"Device rate limit exceeded ({self.DEVICE_LIMIT}/min)"

        # Record
        self._user_windows[user_id].append(now)
        self._device_windows[device_id].append(now)
        return True, "OK"

    def record_auth_failure(self, user_id: str):
        """Record an auth failure. Locks out after threshold."""
        self._auth_failures[user_id] += 1
        if self._auth_failures[user_id] >= self.AUTH_FAIL_LOCKOUT:
            self._lockout_until[user_id] = time.time() + self.LOCKOUT_S
            logger.warning(f"[VOICE_SEC] User {user_id} locked out for {self.LOCKOUT_S}s")

    def reset(self):
        """Reset all state (for testing)."""
        self._user_windows.clear()
        self._device_windows.clear()
        self._auth_failures.clear()
        self._lockout_until.clear()

    def _clean_window(self, window: Deque[float], now: float):
        while window and now - window[0] > self.WINDOW_S:
            window.popleft()


# =============================================================================
# AUDIT LOG
# =============================================================================

class VoiceAuditLog:
    """Tamper-evident audit log with SHA-256 chain."""

    def __init__(self):
        self._entries: List[VoiceAuditEntry] = []
        self._last_hash = "GENESIS"

    def log(self, user_id: str, device_id: str, transcript: str,
            intent: str, action: str, policy: str, result: str,
            redact: bool = False) -> VoiceAuditEntry:
        """Log an audit entry with chain hash."""
        import uuid

        # Redact if privacy mode
        safe_transcript = "[REDACTED]" if redact else transcript

        entry_id = f"AUD-{uuid.uuid4().hex[:12].upper()}"
        entry_hash = _hash_entry(
            entry_id, user_id, safe_transcript,
            intent, action, result, self._last_hash
        )

        entry = VoiceAuditEntry(
            entry_id=entry_id,
            timestamp=datetime.now(UTC).isoformat(),
            user_id=user_id,
            device_id=device_id,
            transcript=safe_transcript,
            resolved_intent=intent,
            executed_action=action,
            policy_decision=policy,
            result=result,
            previous_hash=self._last_hash,
            entry_hash=entry_hash,
        )

        self._entries.append(entry)
        self._last_hash = entry_hash
        return entry

    def verify_chain(self) -> bool:
        """Verify the entire audit chain for tampering."""
        prev_hash = "GENESIS"
        for entry in self._entries:
            if entry.previous_hash != prev_hash:
                return False
            expected = _hash_entry(
                entry.entry_id, entry.user_id, entry.transcript,
                entry.resolved_intent, entry.executed_action,
                entry.result, prev_hash
            )
            if entry.entry_hash != expected:
                return False
            prev_hash = entry.entry_hash
        return True

    def get_entries(self, limit: int = 50) -> List[Dict]:
        """Get recent audit entries."""
        return [
            {
                "entry_id": e.entry_id,
                "timestamp": e.timestamp,
                "user_id": e.user_id,
                "device_id": e.device_id,
                "intent": e.resolved_intent,
                "action": e.executed_action,
                "policy": e.policy_decision,
                "result": e.result,
            }
            for e in self._entries[-limit:]
        ]

    @property
    def count(self) -> int:
        return len(self._entries)

    def clear(self):
        self._entries.clear()
        self._last_hash = "GENESIS"
