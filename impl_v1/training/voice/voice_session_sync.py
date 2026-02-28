"""
Voice Session Sync — Multi-device consistency.

Provides:
  - Monotonic sequence IDs per user session
  - Conflict resolution for simultaneous commands
  - Exactly-once execution via idempotency keys
  - Device registry for active voice sessions
"""

import logging
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, UTC
from typing import Optional, Dict, Set

logger = logging.getLogger(__name__)


# =============================================================================
# TYPES
# =============================================================================

@dataclass
class DeviceSession:
    """Active voice session on a device."""
    device_id: str
    user_id: str
    session_id: str
    started_at: str
    last_active: str
    sequence_id: int = 0
    is_primary: bool = False


@dataclass
class SyncResult:
    """Result of a sync operation."""
    accepted: bool
    reason: str
    sequence_id: int
    device_id: str


# =============================================================================
# SESSION MANAGER
# =============================================================================

class VoiceSessionManager:
    """Multi-device voice session management.

    Rules:
      - Each user can have multiple device sessions
      - One device is "primary" (latest to start listening)
      - Sequence IDs are monotonic per user
      - Conflict: latest-writer-wins with sequence validation
    """

    def __init__(self):
        self._sessions: Dict[str, DeviceSession] = {}  # device_id -> session
        self._user_sequences: Dict[str, int] = {}  # user_id -> seq
        self._processed_keys: Set[str] = set()

    def register_device(self, device_id: str, user_id: str) -> DeviceSession:
        """Register a device for voice. Returns session."""
        session = DeviceSession(
            device_id=device_id,
            user_id=user_id,
            session_id=f"VSS-{uuid.uuid4().hex[:12].upper()}",
            started_at=datetime.now(UTC).isoformat(),
            last_active=datetime.now(UTC).isoformat(),
            sequence_id=self._get_next_seq(user_id),
            is_primary=True,
        )

        # Demote all other sessions for this user
        for sid, s in self._sessions.items():
            if s.user_id == user_id and s.device_id != device_id:
                s.is_primary = False

        self._sessions[device_id] = session
        return session

    def unregister_device(self, device_id: str):
        """Remove a device session."""
        self._sessions.pop(device_id, None)

    def submit_command(self, device_id: str, idempotency_key: str,
                       sequence_id: int) -> SyncResult:
        """Submit a command from a device with sequence validation.

        Returns SyncResult indicating acceptance or rejection.
        """
        session = self._sessions.get(device_id)
        if not session:
            return SyncResult(
                accepted=False,
                reason="Device not registered",
                sequence_id=-1,
                device_id=device_id,
            )

        # Exactly-once: check idempotency key
        if idempotency_key in self._processed_keys:
            return SyncResult(
                accepted=False,
                reason="Duplicate command (already processed)",
                sequence_id=sequence_id,
                device_id=device_id,
            )

        # Sequence validation: must be >= last known
        user_seq = self._user_sequences.get(session.user_id, 0)
        if sequence_id < user_seq:
            return SyncResult(
                accepted=False,
                reason=f"Stale sequence ({sequence_id} < {user_seq})",
                sequence_id=user_seq,
                device_id=device_id,
            )

        # Accept
        new_seq = self._get_next_seq(session.user_id)
        self._processed_keys.add(idempotency_key)
        session.last_active = datetime.now(UTC).isoformat()
        session.sequence_id = new_seq

        return SyncResult(
            accepted=True,
            reason="OK",
            sequence_id=new_seq,
            device_id=device_id,
        )

    def get_active_devices(self, user_id: str) -> list:
        """Get all active devices for a user."""
        return [
            {
                "device_id": s.device_id,
                "session_id": s.session_id,
                "is_primary": s.is_primary,
                "last_active": s.last_active,
                "sequence_id": s.sequence_id,
            }
            for s in self._sessions.values()
            if s.user_id == user_id
        ]

    def get_primary_device(self, user_id: str) -> Optional[str]:
        """Get the primary device for a user."""
        for s in self._sessions.values():
            if s.user_id == user_id and s.is_primary:
                return s.device_id
        return None

    def _get_next_seq(self, user_id: str) -> int:
        seq = self._user_sequences.get(user_id, 0) + 1
        self._user_sequences[user_id] = seq
        return seq

    def clear(self):
        """Clear all sessions (for testing)."""
        self._sessions.clear()
        self._user_sequences.clear()
        self._processed_keys.clear()
