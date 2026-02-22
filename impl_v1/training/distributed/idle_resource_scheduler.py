"""
idle_resource_scheduler.py — Idle Resource Scheduler (Phase 5)

Detects idle GPU/CPU resources and safely assigns background tasks.
Owner override always allowed.
"""

import logging
import os
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

# Thresholds
GPU_IDLE_THRESHOLD = 10.0    # % utilization
CPU_IDLE_THRESHOLD = 20.0    # % utilization
THERMAL_SAFE_MAX = 80.0      # °C
IDLE_DURATION_SEC = 30.0     # Must be idle for this long


@dataclass
class ResourceSnapshot:
    """Snapshot of system resources."""
    gpu_util_pct: float = 100.0
    cpu_util_pct: float = 100.0
    gpu_temp_c: float = 0.0
    gpu_memory_used_pct: float = 100.0
    timestamp: str = ""


@dataclass
class ScheduledTask:
    """A task scheduled on idle resources."""
    task_id: str
    name: str
    priority: int           # Lower = less important
    requires_gpu: bool
    func: Optional[Callable] = None
    status: str = "pending"  # pending / running / done / cancelled
    started_at: str = ""
    completed_at: str = ""


@dataclass
class SchedulerState:
    """State of the idle resource scheduler."""
    idle_since: Optional[str] = None
    owner_override: bool = False
    tasks: List[dict] = field(default_factory=list)
    last_check: str = ""


class IdleResourceScheduler:
    """Manages background tasks on idle resources.

    Rules:
    1. GPU idle > threshold for > duration → idle
    2. CPU idle > threshold → idle
    3. Thermal safe (< max temp)
    4. Owner override always cancels background tasks
    """

    def __init__(
        self,
        gpu_threshold: float = GPU_IDLE_THRESHOLD,
        cpu_threshold: float = CPU_IDLE_THRESHOLD,
        thermal_max: float = THERMAL_SAFE_MAX,
        idle_duration: float = IDLE_DURATION_SEC,
    ):
        self.gpu_threshold = gpu_threshold
        self.cpu_threshold = cpu_threshold
        self.thermal_max = thermal_max
        self.idle_duration = idle_duration
        self._tasks: List[ScheduledTask] = []
        self._idle_start: Optional[float] = None
        self._owner_override = False

    def check_resources(
        self,
        snapshot: Optional[ResourceSnapshot] = None,
    ) -> ResourceSnapshot:
        """Check current resource state.

        If no snapshot provided, uses safe defaults (busy).
        """
        if snapshot is None:
            snapshot = self._probe_resources()
        snapshot.timestamp = datetime.now().isoformat()
        return snapshot

    def is_idle(self, snapshot: ResourceSnapshot) -> bool:
        """Check if the system is idle enough for background tasks."""
        if self._owner_override:
            return False

        gpu_idle = snapshot.gpu_util_pct <= self.gpu_threshold
        cpu_idle = snapshot.cpu_util_pct <= self.cpu_threshold
        thermal_safe = snapshot.gpu_temp_c <= self.thermal_max

        if gpu_idle and cpu_idle and thermal_safe:
            now = time.time()
            if self._idle_start is None:
                self._idle_start = now
                return False  # Need to wait for duration

            elapsed = now - self._idle_start
            if elapsed >= self.idle_duration:
                return True
            return False
        else:
            self._idle_start = None
            return False

    def add_task(self, task: ScheduledTask):
        """Add a background task to the queue."""
        self._tasks.append(task)
        logger.info(
            f"[SCHEDULER] Task added: {task.name} "
            f"(gpu={task.requires_gpu}, priority={task.priority})"
        )

    def run_pending(self, snapshot: ResourceSnapshot) -> List[str]:
        """Run pending tasks if idle.

        Returns list of task IDs that were started.
        """
        if not self.is_idle(snapshot):
            return []

        started = []
        for task in self._tasks:
            if task.status != "pending":
                continue

            if task.requires_gpu and snapshot.gpu_memory_used_pct > 80:
                continue  # Not enough GPU memory

            task.status = "running"
            task.started_at = datetime.now().isoformat()

            if task.func:
                try:
                    task.func()
                    task.status = "done"
                    task.completed_at = datetime.now().isoformat()
                except Exception as e:
                    task.status = "failed"
                    logger.error(f"[SCHEDULER] Task {task.name} failed: {e}")
            else:
                task.status = "done"
                task.completed_at = datetime.now().isoformat()

            started.append(task.task_id)

            logger.info(
                f"[SCHEDULER] Task {task.name}: {task.status}"
            )

        return started

    def owner_override(self):
        """Owner reclaims resources — cancel all running background tasks."""
        self._owner_override = True
        cancelled = 0
        for task in self._tasks:
            if task.status == "running":
                task.status = "cancelled"
                cancelled += 1

        logger.info(
            f"[SCHEDULER] OWNER OVERRIDE: {cancelled} tasks cancelled"
        )
        return cancelled

    def release_override(self):
        """Release owner override — allow idle scheduling again."""
        self._owner_override = False
        self._idle_start = None
        logger.info("[SCHEDULER] Owner override released")

    def get_task_summary(self) -> dict:
        """Get summary of all tasks."""
        summary = {
            'total': len(self._tasks),
            'pending': sum(1 for t in self._tasks if t.status == 'pending'),
            'running': sum(1 for t in self._tasks if t.status == 'running'),
            'done': sum(1 for t in self._tasks if t.status == 'done'),
            'cancelled': sum(1 for t in self._tasks if t.status == 'cancelled'),
        }
        return summary

    @staticmethod
    def _probe_resources() -> ResourceSnapshot:
        """Probe actual resources. Returns safe defaults if unavailable."""
        gpu_util = 100.0
        gpu_temp = 0.0
        gpu_mem = 100.0
        cpu_util = 50.0

        try:
            import subprocess
            r = subprocess.run(
                ['nvidia-smi',
                 '--query-gpu=utilization.gpu,temperature.gpu,memory.used,memory.total',
                 '--format=csv,noheader,nounits'],
                capture_output=True, text=True, timeout=5,
            )
            if r.returncode == 0:
                parts = r.stdout.strip().split(',')
                if len(parts) >= 4:
                    gpu_util = float(parts[0].strip())
                    gpu_temp = float(parts[1].strip())
                    mem_used = float(parts[2].strip())
                    mem_total = float(parts[3].strip())
                    gpu_mem = (mem_used / max(mem_total, 1)) * 100
        except Exception:
            pass

        try:
            import psutil
            cpu_util = psutil.cpu_percent(interval=0.1)
        except Exception:
            pass

        return ResourceSnapshot(
            gpu_util_pct=gpu_util,
            cpu_util_pct=cpu_util,
            gpu_temp_c=gpu_temp,
            gpu_memory_used_pct=gpu_mem,
        )
