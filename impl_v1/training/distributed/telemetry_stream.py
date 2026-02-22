"""
telemetry_stream.py — WebSocket Telemetry Stream (Phase 2)

Expose /training/stream endpoint.
Relay telemetry to frontend.
Calculate ETA = remaining_samples / sps.
"""

import asyncio
import json
import logging
import time
from dataclasses import dataclass, asdict
from datetime import datetime
from typing import Dict, List, Optional, Set

logger = logging.getLogger(__name__)

STALL_TIMEOUT_SEC = 10.0


@dataclass
class TelemetryFrame:
    """A single telemetry frame sent to frontend."""
    epoch: int
    batch: int
    total_batches: int
    samples_processed: int
    total_samples: int
    samples_per_sec: float
    gpu_utilization: float
    gpu_memory_mb: float
    gpu_temp: float
    loss: float
    running_accuracy: float
    learning_rate: float
    eta_seconds: float
    stalled: bool
    timestamp: str


class TelemetryStream:
    """Manages telemetry streaming to WebSocket clients.

    Records telemetry from training loop and relays to connected
    frontend clients as JSON frames.
    """

    def __init__(self):
        self._current: Optional[TelemetryFrame] = None
        self._history: List[TelemetryFrame] = []
        self._subscribers: Set = set()
        self._last_update: float = 0.0
        self._training_active: bool = False
        self._total_samples: int = 0

    def start_training(self, total_samples: int):
        """Mark training as active."""
        self._training_active = True
        self._total_samples = total_samples
        self._last_update = time.time()
        logger.info(
            f"[TELEMETRY_STREAM] Training started: {total_samples} samples"
        )

    def stop_training(self):
        """Mark training as complete."""
        self._training_active = False
        logger.info("[TELEMETRY_STREAM] Training stopped")

    def record(
        self,
        epoch: int,
        batch: int,
        total_batches: int,
        samples_processed: int,
        samples_per_sec: float,
        gpu_utilization: float = 0.0,
        gpu_memory_mb: float = 0.0,
        gpu_temp: float = 0.0,
        loss: float = 0.0,
        running_accuracy: float = 0.0,
        learning_rate: float = 0.0,
    ) -> TelemetryFrame:
        """Record a telemetry snapshot."""
        # Calculate ETA
        remaining = max(0, self._total_samples - samples_processed)
        eta = remaining / max(samples_per_sec, 0.001)

        # Stall detection
        now = time.time()
        stalled = (
            self._training_active and
            self._last_update > 0 and
            (now - self._last_update) >= STALL_TIMEOUT_SEC
        )

        frame = TelemetryFrame(
            epoch=epoch,
            batch=batch,
            total_batches=total_batches,
            samples_processed=samples_processed,
            total_samples=self._total_samples,
            samples_per_sec=round(samples_per_sec, 2),
            gpu_utilization=round(gpu_utilization, 4),
            gpu_memory_mb=round(gpu_memory_mb, 2),
            gpu_temp=round(gpu_temp, 1),
            loss=round(loss, 6),
            running_accuracy=round(running_accuracy, 4),
            learning_rate=round(learning_rate, 8),
            eta_seconds=round(eta, 1),
            stalled=stalled,
            timestamp=datetime.now().isoformat(),
        )

        self._current = frame
        self._history.append(frame)
        self._last_update = now

        return frame

    def get_current(self) -> Optional[TelemetryFrame]:
        """Get current telemetry frame."""
        if self._current and self._training_active:
            # Check for stall
            elapsed = time.time() - self._last_update
            if elapsed >= STALL_TIMEOUT_SEC:
                self._current.stalled = True
        return self._current

    def get_history(self, last_n: int = 100) -> List[TelemetryFrame]:
        """Get recent telemetry history."""
        return self._history[-last_n:]

    def get_loss_history(self) -> List[dict]:
        """Get loss values over time for graph."""
        return [
            {
                'epoch': f.epoch,
                'batch': f.batch,
                'loss': f.loss,
                'accuracy': f.running_accuracy,
                'timestamp': f.timestamp,
            }
            for f in self._history
        ]

    def to_json(self, frame: Optional[TelemetryFrame] = None) -> str:
        """Serialize frame to JSON for WebSocket."""
        f = frame or self._current
        if f is None:
            return json.dumps({"status": "no_data"})
        return json.dumps(asdict(f))

    @property
    def is_stalled(self) -> bool:
        if not self._training_active:
            return False
        return (time.time() - self._last_update) >= STALL_TIMEOUT_SEC

    @property
    def is_active(self) -> bool:
        return self._training_active


# =============================================================================
# WebSocket endpoint handler (for use with any ASGI framework)
# =============================================================================

async def training_stream_handler(
    stream: TelemetryStream,
    send_fn,
    interval: float = 1.0,
):
    """Stream telemetry frames at 1-second intervals.

    Args:
        stream: TelemetryStream instance
        send_fn: async callable(json_str) to send to client
        interval: seconds between frames
    """
    while stream.is_active:
        frame = stream.get_current()
        if frame:
            await send_fn(stream.to_json(frame))
        await asyncio.sleep(interval)
