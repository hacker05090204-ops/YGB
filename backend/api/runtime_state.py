"""
runtime_state.py — Thread-safe shared runtime state

Replaces bare `global` variables in server.py with a concurrency-safe
state container. All reads/writes go through this module.

Addresses Risk 12 (Concurrency/State): 5 global mutable variables in
server.py were mutated without any locking.
"""

import threading
from typing import Any, Dict, Optional


class _SafeState:
    """Thread-safe key-value state container with atomic read/write."""

    def __init__(self):
        self._lock = threading.Lock()
        self._data: Dict[str, Any] = {}

    def get(self, key: str, default: Any = None) -> Any:
        with self._lock:
            return self._data.get(key, default)

    def set(self, key: str, value: Any) -> None:
        with self._lock:
            self._data[key] = value

    def increment(self, key: str, amount: int = 1) -> int:
        """Atomic increment, returns new value."""
        with self._lock:
            current = self._data.get(key, 0)
            new_val = current + amount
            self._data[key] = new_val
            return new_val

    def compare_and_set(self, key: str, expected: Any, new_value: Any) -> bool:
        """Atomic compare-and-swap."""
        with self._lock:
            if self._data.get(key) == expected:
                self._data[key] = new_value
                return True
            return False

    def snapshot(self) -> Dict[str, Any]:
        """Return a copy of all state (for debugging/health)."""
        with self._lock:
            return dict(self._data)


# Singleton instance — import and use directly
runtime_state = _SafeState()

# Initialize known keys with defaults
runtime_state.set("gpu_seq_id", 0)
runtime_state.set("stream_seq_id", 0)
runtime_state.set("dashboard_seq_id", 0)
runtime_state.set("active_voice_mode", False)
runtime_state.set("runtime_mode", "MANUAL")
