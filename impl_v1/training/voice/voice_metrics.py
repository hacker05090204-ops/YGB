"""
Voice Metrics — Observability and SLO tracking.

Emits:
  - wake_to_transcript_ms
  - transcript_to_intent_ms
  - intent_to_action_ms
  - end_to_end_success_rate
  - stt_confidence_distribution
  - blocked_by_policy_count
  - retry_count
  - failure_rate_by_stage
"""

import time
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, UTC
from typing import Dict, List


@dataclass
class VoiceTimings:
    """Timing breakdown for a single voice command."""
    command_id: str
    wake_to_transcript_ms: float = 0.0
    transcript_to_intent_ms: float = 0.0
    intent_to_action_ms: float = 0.0
    total_ms: float = 0.0
    success: bool = False
    stage_failed: str = ""


class VoiceMetricsCollector:
    """Collects voice pipeline metrics for SLO monitoring."""

    def __init__(self):
        self._timings: List[VoiceTimings] = []
        self._confidence_samples: List[float] = []
        self._blocked_by_policy = 0
        self._retry_count = 0
        self._failures_by_stage: Dict[str, int] = defaultdict(int)
        self._total_commands = 0
        self._successful_commands = 0

    def record_timing(self, timing: VoiceTimings):
        """Record timing for a command."""
        self._timings.append(timing)
        self._total_commands += 1
        if timing.success:
            self._successful_commands += 1
        elif timing.stage_failed:
            self._failures_by_stage[timing.stage_failed] += 1

    def record_confidence(self, confidence: float):
        self._confidence_samples.append(confidence)

    def record_policy_block(self):
        self._blocked_by_policy += 1

    def record_retry(self):
        self._retry_count += 1

    @property
    def success_rate(self) -> float:
        if self._total_commands == 0:
            return 0.0
        return self._successful_commands / self._total_commands

    @property
    def avg_confidence(self) -> float:
        if not self._confidence_samples:
            return 0.0
        return sum(self._confidence_samples) / len(self._confidence_samples)

    def get_latency_percentiles(self) -> Dict[str, float]:
        """Get P50/P95/P99 total latency."""
        if not self._timings:
            return {"p50": 0.0, "p95": 0.0, "p99": 0.0}

        totals = sorted(t.total_ms for t in self._timings)
        n = len(totals)
        return {
            "p50": totals[int(n * 0.5)] if n > 0 else 0.0,
            "p95": totals[int(n * 0.95)] if n > 1 else totals[-1],
            "p99": totals[int(n * 0.99)] if n > 1 else totals[-1],
        }

    def get_health(self) -> Dict:
        """Get full health report for /api/voice/metrics."""
        percs = self.get_latency_percentiles()
        return {
            "total_commands": self._total_commands,
            "successful_commands": self._successful_commands,
            "success_rate": round(self.success_rate, 4),
            "avg_confidence": round(self.avg_confidence, 3),
            "blocked_by_policy": self._blocked_by_policy,
            "retry_count": self._retry_count,
            "failures_by_stage": dict(self._failures_by_stage),
            "latency_percentiles_ms": percs,
            "confidence_samples": len(self._confidence_samples),
            "slo_met": self.success_rate >= 0.99,
            "timestamp": datetime.now(UTC).isoformat(),
        }

    def clear(self):
        """Reset all metrics (for testing)."""
        self._timings.clear()
        self._confidence_samples.clear()
        self._blocked_by_policy = 0
        self._retry_count = 0
        self._failures_by_stage.clear()
        self._total_commands = 0
        self._successful_commands = 0


# Module-level collector
_collector = VoiceMetricsCollector()


def get_metrics_collector() -> VoiceMetricsCollector:
    return _collector


def get_voice_health() -> Dict:
    return _collector.get_health()
