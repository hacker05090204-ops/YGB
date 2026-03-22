"""Watchdog-based incremental training trigger."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

from backend.ingestion._integrity import log_module_sha256
from backend.observability.metrics import metrics_registry
from backend.training.incremental_trainer import IncrementalTrainer

logger = logging.getLogger("ygb.training.data_watcher")


class DataWatcher(FileSystemEventHandler):
    def __init__(
        self,
        watch_path: str = "data/raw",
        trainer: Optional[IncrementalTrainer] = None,
        state_path: str = "checkpoints/training_state.json",
        observer_factory=Observer,
        scheduler_factory=BackgroundScheduler,
    ) -> None:
        super().__init__()
        self.watch_path = watch_path
        self.trainer = trainer or IncrementalTrainer()
        self.state_path = Path(state_path)
        self.observer = observer_factory()
        self.scheduler = None
        self.scheduler_factory = scheduler_factory
        self.new_file_count = 0
        self.last_trigger_time = self._load_last_trigger_time()

    def _load_last_trigger_time(self) -> datetime:
        if self.state_path.exists():
            payload = json.loads(self.state_path.read_text(encoding="utf-8"))
            timestamp = payload.get("last_training_time")
            if timestamp:
                return datetime.fromisoformat(str(timestamp).replace("Z", "+00:00"))
        return datetime.now(timezone.utc)

    def on_created(self, event) -> None:
        if not event.is_directory and str(event.src_path).endswith(".json"):
            self.new_file_count += 1
            self._check_trigger()

    def _check_trigger(self) -> None:
        time_since = (datetime.now(timezone.utc) - self.last_trigger_time).total_seconds()
        if self.new_file_count > 500 or time_since > 21600:
            logger.info(
                "data watcher trigger fired",
                extra={"event": "data_watcher_trigger", "new_file_count": self.new_file_count, "time_since": time_since},
            )
            metrics_registry.increment("data_watcher_trigger_count")
            self.trainer.run_incremental_epoch()
            self.new_file_count = 0
            self.last_trigger_time = datetime.now(timezone.utc)

    def start(self) -> None:
        try:
            self.observer.schedule(self, self.watch_path, recursive=True)
            self.observer.start()
        except Exception:
            logger.warning("watchdog observer failed; enabling scheduler fallback", exc_info=True)
            self.scheduler = self.scheduler_factory()
            self.scheduler.add_job(
                self.trainer.run_incremental_epoch,
                trigger=IntervalTrigger(hours=6),
            )
            self.scheduler.start()

    def stop(self) -> None:
        if getattr(self.observer, "is_alive", lambda: False)():
            self.observer.stop()
            self.observer.join()
        if self.scheduler is not None:
            self.scheduler.shutdown(wait=False)


MODULE_SHA256 = log_module_sha256(__file__, logger, __name__)
