"""
field_scheduler.py — Field Training Scheduler (Phase 1)

Maintain field_queue.json:
- Round-robin rotation
- Priority-based ordering
- 10-min idle auto-continue
- Skip fields with no new data
"""

import json
import logging
import os
import time
from dataclasses import dataclass, asdict, field
from datetime import datetime
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

QUEUE_PATH = os.path.join('secure_data', 'field_queue.json')
IDLE_THRESHOLD_SEC = 600  # 10 minutes


@dataclass
class FieldEntry:
    """A field in the training queue."""
    field_name: str
    priority: int = 50
    dataset_hash: str = ""
    last_trained: str = ""
    status: str = "pending"     # pending / training / completed / skipped
    has_new_data: bool = True
    epochs_completed: int = 0
    best_accuracy: float = 0.0


@dataclass
class SchedulerState:
    """Scheduler state."""
    current_field: Optional[str]
    queue: List[FieldEntry]
    rotation_index: int
    auto_mode: bool
    idle_since: float


class FieldScheduler:
    """Round-robin field training scheduler.

    Picks next field on completion. Auto-continues after 10min idle.
    Skips fields with no new data.
    """

    def __init__(self, queue_path: str = QUEUE_PATH):
        self.queue_path = queue_path
        self._queue: List[FieldEntry] = []
        self._current: Optional[str] = None
        self._rotation_idx: int = 0
        self._auto_mode: bool = True
        self._idle_since: float = 0.0
        self._load()

    def add_field(self, entry: FieldEntry):
        """Add a field to the queue."""
        # Avoid duplicate
        for e in self._queue:
            if e.field_name == entry.field_name:
                e.priority = entry.priority
                e.dataset_hash = entry.dataset_hash
                e.has_new_data = entry.has_new_data
                self._save()
                return
        self._queue.append(entry)
        self._queue.sort(key=lambda f: -f.priority)
        self._save()
        logger.info(
            f"[SCHEDULER] Added: {entry.field_name} priority={entry.priority}"
        )

    def next_field(self) -> Optional[FieldEntry]:
        """Get next field to train using round-robin.

        Skips fields with no new data.
        """
        if not self._queue:
            return None

        attempts = 0
        while attempts < len(self._queue):
            idx = self._rotation_idx % len(self._queue)
            entry = self._queue[idx]
            self._rotation_idx += 1
            attempts += 1

            if not entry.has_new_data:
                entry.status = "skipped"
                logger.info(f"[SCHEDULER] Skipped (no new data): {entry.field_name}")
                continue

            if entry.status == "completed":
                continue

            entry.status = "training"
            self._current = entry.field_name
            self._idle_since = 0.0
            self._save()

            logger.info(f"[SCHEDULER] → Training: {entry.field_name}")
            return entry

        logger.info("[SCHEDULER] Queue exhausted — no trainable fields")
        return None

    def complete_field(
        self,
        field_name: str,
        accuracy: float = 0.0,
        epochs: int = 0,
    ):
        """Mark a field as completed."""
        for e in self._queue:
            if e.field_name == field_name:
                e.status = "completed"
                e.best_accuracy = accuracy
                e.epochs_completed = epochs
                e.last_trained = datetime.now().isoformat()
                e.has_new_data = False
                break
        self._current = None
        self._idle_since = time.time()
        self._save()
        logger.info(
            f"[SCHEDULER] ✓ Completed: {field_name} "
            f"acc={accuracy:.4f} epochs={epochs}"
        )

    def should_auto_continue(self) -> bool:
        """Check if idle long enough to auto-continue."""
        if not self._auto_mode:
            return False
        if self._current is not None:
            return False
        if self._idle_since <= 0:
            return False
        return (time.time() - self._idle_since) >= IDLE_THRESHOLD_SEC

    def reset_queue(self):
        """Reset all fields to pending for next rotation cycle."""
        for e in self._queue:
            e.status = "pending"
            e.has_new_data = True
        self._rotation_idx = 0
        self._save()

    def get_state(self) -> SchedulerState:
        return SchedulerState(
            current_field=self._current,
            queue=list(self._queue),
            rotation_index=self._rotation_idx,
            auto_mode=self._auto_mode,
            idle_since=self._idle_since,
        )

    @property
    def current_field(self) -> Optional[str]:
        return self._current

    @property
    def queue_size(self) -> int:
        return len(self._queue)

    def _save(self):
        os.makedirs(os.path.dirname(self.queue_path) or '.', exist_ok=True)
        data = [asdict(e) for e in self._queue]
        with open(self.queue_path, 'w') as f:
            json.dump(data, f, indent=2)

    def _load(self):
        if os.path.exists(self.queue_path):
            try:
                with open(self.queue_path) as f:
                    data = json.load(f)
                self._queue = [FieldEntry(**d) for d in data]
            except (json.JSONDecodeError, IOError):
                self._queue = []
