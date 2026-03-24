"""Central async orchestration runtime for the YGB backend.

This module coordinates request handling, workflow planning, agent routing,
telemetry, retries, caching, notifications, and verification while preserving
the existing governance boundaries.
"""

from __future__ import annotations

import asyncio
import gc
import hashlib
import inspect
import json
import math
import os
import shutil
import time
import tracemalloc
import uuid
from collections import OrderedDict, deque
from dataclasses import dataclass, field
from datetime import UTC, datetime
from statistics import mean
from typing import Any, Awaitable, Callable, Dict, List, Optional, Sequence, TypeVar
from urllib.parse import urlparse
from pathlib import Path

import httpx
from fastapi import Request
from fastapi.responses import JSONResponse, Response

from distributed_runtime import DistributedClusterCoordinator
from impl_v1.training.evaluation.accuracy_metrics import (
    AccuracyFeedbackStore,
    EvaluationRecord,
    StrategyFeedbackStore,
    token_overlap,
)

T = TypeVar("T")


async def _run_maybe_async(func: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
    """Run sync or async callables without blocking the event loop."""
    if inspect.iscoroutinefunction(func):
        return await func(*args, **kwargs)
    return await asyncio.to_thread(func, *args, **kwargs)


@dataclass(slots=True)
class AgentProfile:
    """Simple runtime agent description used for task routing."""

    name: str
    specialties: tuple[str, ...]
    description: str
    max_concurrency: int = 1


@dataclass(slots=True)
class ExecutionStrategy:
    """Reasoned execution strategy for a task."""

    agent_name: str
    task_type: str
    crawl_depth: int
    concurrency: int
    payload_profile: str
    verification_level: str
    priority: str
    rate_limit_per_host: int
    notes: list[str] = field(default_factory=list)


@dataclass(slots=True)
class OrchestrationPlan:
    """Plan returned by the thinking layer before execution."""

    request_id: str
    task_type: str
    strategy: ExecutionStrategy
    created_at: str
    context_summary: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class VerificationOutcome:
    """Result from the accuracy / verification layer."""

    fingerprint: str
    status: str
    confidence: float
    duplicate: bool
    ml_score: float
    notes: list[str] = field(default_factory=list)


class QueueOverloadedError(RuntimeError):
    """Raised when backpressure rejects a task submission."""


@dataclass(slots=True)
class PayloadVerificationResult:
    """Result from safe response verification for an existing finding."""

    confirmed: bool
    confidence: float
    notes: list[str] = field(default_factory=list)


@dataclass(slots=True)
class ResourceSnapshot:
    """Lightweight system resource snapshot."""

    cpu_load_ratio: float
    memory_load_ratio: float
    gpu_memory_ratio: float
    request_pressure: float
    queue_pressure: float
    overloaded: bool
    suggested_concurrency_scale: float
    suggested_batch_scale: float
    paused_training: bool


@dataclass(slots=True)
class MemoryExperience:
    """Vectorized experience stored per-agent namespace."""

    memory_id: str
    namespace: str
    content: str
    metadata: dict[str, Any]
    vector: dict[str, float]
    created_at: str


class AsyncLRUCache:
    """Tiny async-aware LRU cache with TTL support."""

    def __init__(self, maxsize: int = 512):
        self.maxsize = maxsize
        self._lock = asyncio.Lock()
        self._entries: OrderedDict[str, tuple[float, Any]] = OrderedDict()

    async def get(self, key: str) -> Any:
        async with self._lock:
            if key not in self._entries:
                return None
            expires_at, value = self._entries[key]
            if expires_at and expires_at < time.time():
                self._entries.pop(key, None)
                return None
            self._entries.move_to_end(key)
            return value

    async def set(self, key: str, value: Any, ttl_seconds: float = 60.0) -> Any:
        async with self._lock:
            expires_at = time.time() + ttl_seconds if ttl_seconds > 0 else 0.0
            self._entries[key] = (expires_at, value)
            self._entries.move_to_end(key)
            while len(self._entries) > self.maxsize:
                self._entries.popitem(last=False)
            return value

    async def get_or_set(
        self,
        key: str,
        factory: Callable[[], T] | Callable[[], Awaitable[T]],
        ttl_seconds: float = 60.0,
    ) -> T:
        cached = await self.get(key)
        if cached is not None:
            return cached
        value = await _run_maybe_async(factory)
        await self.set(key, value, ttl_seconds=ttl_seconds)
        return value

    async def clear(self) -> None:
        async with self._lock:
            self._entries.clear()


def _tokenize(text: str) -> list[str]:
    normalized = []
    current = []
    for char in text.lower():
        if char.isalnum() or char in {"_", "-"}:
            current.append(char)
        elif current:
            normalized.append("".join(current))
            current = []
    if current:
        normalized.append("".join(current))
    return normalized[:128]


def _vectorize(text: str) -> dict[str, float]:
    tokens = _tokenize(text)
    if not tokens:
        return {"__empty__": 1.0}
    counts: dict[str, float] = {}
    for token in tokens:
        counts[token] = counts.get(token, 0.0) + 1.0
    norm = math.sqrt(sum(value * value for value in counts.values())) or 1.0
    return {token: value / norm for token, value in counts.items()}


def _cosine_similarity(left: dict[str, float], right: dict[str, float]) -> float:
    if len(left) > len(right):
        left, right = right, left
    return sum(value * right.get(token, 0.0) for token, value in left.items())


class VectorMemoryStore:
    """Per-agent vector memory with retrieval and experience reuse."""

    def __init__(self, max_entries_per_namespace: int = 256) -> None:
        self.max_entries_per_namespace = max_entries_per_namespace
        self._entries: dict[str, deque[MemoryExperience]] = {}
        self._lock = asyncio.Lock()

    async def add(
        self, namespace: str, content: str, metadata: Optional[dict[str, Any]] = None
    ) -> MemoryExperience:
        experience = MemoryExperience(
            memory_id=f"MEM-{uuid.uuid4().hex[:12].upper()}",
            namespace=namespace,
            content=content[:2000],
            metadata=dict(metadata or {}),
            vector=_vectorize(content),
            created_at=datetime.now(UTC).isoformat(),
        )
        async with self._lock:
            bucket = self._entries.setdefault(
                namespace,
                deque(maxlen=self.max_entries_per_namespace),
            )
            bucket.append(experience)
        return experience

    async def retrieve(
        self,
        namespace: str,
        query: str,
        *,
        limit: int = 5,
        minimum_score: float = 0.2,
    ) -> list[dict[str, Any]]:
        query_vector = _vectorize(query)
        async with self._lock:
            bucket = list(self._entries.get(namespace, deque()))
        ranked = []
        for entry in bucket:
            score = _cosine_similarity(query_vector, entry.vector)
            if score >= minimum_score:
                ranked.append(
                    {
                        "memory_id": entry.memory_id,
                        "score": round(score, 4),
                        "content": entry.content,
                        "metadata": entry.metadata,
                        "created_at": entry.created_at,
                    }
                )
        ranked.sort(key=lambda item: item["score"], reverse=True)
        return ranked[:limit]

    async def snapshot(self) -> dict[str, Any]:
        async with self._lock:
            return {
                namespace: [
                    {
                        "memory_id": entry.memory_id,
                        "content": entry.content,
                        "metadata": entry.metadata,
                        "created_at": entry.created_at,
                    }
                    for entry in bucket
                ]
                for namespace, bucket in self._entries.items()
            }

    async def restore(self, snapshot: dict[str, Any]) -> None:
        async with self._lock:
            self._entries.clear()
            for namespace, records in snapshot.items():
                bucket: deque[MemoryExperience] = deque(
                    maxlen=self.max_entries_per_namespace
                )
                for record in records:
                    content = str(record.get("content", ""))
                    bucket.append(
                        MemoryExperience(
                            memory_id=str(
                                record.get("memory_id")
                                or f"MEM-{uuid.uuid4().hex[:12].upper()}"
                            ),
                            namespace=namespace,
                            content=content,
                            metadata=dict(record.get("metadata") or {}),
                            vector=_vectorize(content),
                            created_at=str(
                                record.get("created_at")
                                or datetime.now(UTC).isoformat()
                            ),
                        )
                    )
                self._entries[namespace] = bucket

    def counts(self) -> dict[str, int]:
        return {namespace: len(bucket) for namespace, bucket in self._entries.items()}


class AgentIsolationManager:
    """Enforces per-agent dataset, memory, and routing isolation."""

    def __init__(self) -> None:
        self._dataset_namespaces: dict[str, set[str]] = {}
        self._memory_namespaces: dict[str, str] = {}
        self._memory_limits_mb: dict[str, int] = {}

    def register(self, agent: AgentProfile) -> None:
        default_namespace = agent.name.replace("agent", "memory").replace("-", "_")
        self._memory_namespaces[agent.name] = default_namespace
        self._memory_limits_mb[agent.name] = max(64, agent.max_concurrency * 64)
        if "training" in agent.specialties or "ml" in agent.specialties:
            allowed = {"training_dataset", "holdout_dataset", default_namespace}
        elif "crawl" in agent.specialties or "bounty" in agent.specialties:
            allowed = {"crawl_cache", "verification_cache", default_namespace}
        elif "voice" in agent.specialties:
            allowed = {"voice_intents", default_namespace}
        else:
            allowed = {default_namespace}
        self._dataset_namespaces[agent.name] = allowed

    def memory_namespace(self, agent_name: str) -> str:
        return self._memory_namespaces.get(agent_name, agent_name.replace("-", "_"))

    def assert_dataset_access(self, agent_name: str, namespace: str) -> None:
        allowed = self._dataset_namespaces.get(
            agent_name, {self.memory_namespace(agent_name)}
        )
        if namespace not in allowed:
            raise PermissionError(
                f"Agent {agent_name} cannot access dataset namespace '{namespace}'"
            )

    def memory_limit_mb(self, agent_name: str) -> int:
        return self._memory_limits_mb.get(agent_name, 64)

    def snapshot(self) -> dict[str, Any]:
        return {
            "datasets": {
                name: sorted(values)
                for name, values in self._dataset_namespaces.items()
            },
            "memory_namespaces": dict(self._memory_namespaces),
            "memory_limits_mb": dict(self._memory_limits_mb),
        }


class ResourceGovernor:
    """Tracks CPU, memory, GPU, and queue pressure for adaptive throttling."""

    def __init__(self) -> None:
        self.max_cpu_ratio = float(os.getenv("YGB_MAX_CPU_RATIO", "0.92"))
        self.max_memory_ratio = float(os.getenv("YGB_MAX_MEMORY_RATIO", "0.9"))
        self.max_gpu_ratio = float(os.getenv("YGB_MAX_GPU_RATIO", "0.9"))
        self._paused_training = False
        try:
            import psutil  # type: ignore

            self._psutil = psutil
        except Exception:
            self._psutil = None

    def _cpu_ratio(self) -> float:
        if self._psutil is not None:
            return min(self._psutil.cpu_percent(interval=None) / 100.0, 1.0)
        if hasattr(os, "getloadavg"):
            load = os.getloadavg()[0]
            cpu_count = os.cpu_count() or 1
            return min(load / cpu_count, 1.0)
        return 0.0

    def _memory_ratio(self) -> float:
        if self._psutil is not None:
            return min(self._psutil.virtual_memory().percent / 100.0, 1.0)
        current_bytes = peak_bytes = 0
        if tracemalloc.is_tracing():
            current_bytes, peak_bytes = tracemalloc.get_traced_memory()
        limit_bytes = max(peak_bytes, current_bytes, 1)
        return min(current_bytes / limit_bytes, 1.0)

    def _gpu_ratio(self) -> float:
        try:
            import torch

            if torch.cuda.is_available():
                reserved = float(torch.cuda.memory_reserved())
                total = float(torch.cuda.get_device_properties(0).total_memory)
                if total > 0:
                    return min(reserved / total, 1.0)
        except Exception:
            pass
        return 0.0

    def snapshot(
        self, *, queue_pressure: float, request_pressure: float
    ) -> ResourceSnapshot:
        cpu_ratio = self._cpu_ratio()
        memory_ratio = self._memory_ratio()
        gpu_ratio = self._gpu_ratio()
        overloaded = (
            cpu_ratio >= self.max_cpu_ratio
            or memory_ratio >= self.max_memory_ratio
            or gpu_ratio >= self.max_gpu_ratio
            or queue_pressure >= 1.0
        )
        pressure = max(
            cpu_ratio / self.max_cpu_ratio,
            memory_ratio / self.max_memory_ratio,
            gpu_ratio / max(self.max_gpu_ratio, 0.01),
            queue_pressure,
            request_pressure,
        )
        scale = max(0.25, 1.0 - max(0.0, pressure - 0.7))
        batch_scale = max(0.25, 1.0 - max(0.0, pressure - 0.6))
        self._paused_training = overloaded and (
            gpu_ratio >= self.max_gpu_ratio or memory_ratio >= self.max_memory_ratio
        )
        return ResourceSnapshot(
            cpu_load_ratio=round(cpu_ratio, 4),
            memory_load_ratio=round(memory_ratio, 4),
            gpu_memory_ratio=round(gpu_ratio, 4),
            request_pressure=round(request_pressure, 4),
            queue_pressure=round(queue_pressure, 4),
            overloaded=overloaded,
            suggested_concurrency_scale=round(scale, 4),
            suggested_batch_scale=round(batch_scale, 4),
            paused_training=self._paused_training,
        )


class StatePersistence:
    """Persists orchestrator state for restart recovery."""

    def __init__(self, state_path: Optional[Path] = None) -> None:
        self.state_path = state_path or (
            Path(__file__).parent.parent / "reports" / "orchestrator_state.json"
        )
        self.sync_dir = Path(
            os.getenv("YGB_CHECKPOINT_SYNC_DIR", str(self.state_path.parent / "sync"))
        )

    async def save(self, payload: dict[str, Any]) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self.sync_dir.mkdir(parents=True, exist_ok=True)
        await asyncio.to_thread(
            self.state_path.write_text, json.dumps(payload, indent=2), encoding="utf-8"
        )
        manifest_path = self.sync_dir / "latest_orchestrator_state.json"
        await asyncio.to_thread(shutil.copy2, self.state_path, manifest_path)

    async def load(self) -> dict[str, Any]:
        if not self.state_path.exists():
            return {}
        try:
            raw = await asyncio.to_thread(self.state_path.read_text, encoding="utf-8")
            data = json.loads(raw)
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}


class AgentRegistry:
    """Registry for backend task routing."""

    def __init__(self) -> None:
        self._agents: dict[str, AgentProfile] = {}

    def register(self, agent: AgentProfile) -> None:
        self._agents[agent.name] = agent

    def all(self) -> list[AgentProfile]:
        return sorted(self._agents.values(), key=lambda agent: agent.name)

    def select(
        self, task_type: str, context: Optional[dict[str, Any]] = None
    ) -> AgentProfile:
        context = context or {}
        target = str(context.get("target") or context.get("target_url") or "").lower()
        preferred = [
            agent for agent in self._agents.values() if task_type in agent.specialties
        ]
        if preferred:
            if "voice" in task_type:
                return preferred[0]
            if any(
                token in target
                for token in ("admin", "api", "auth", "login", "graphql")
            ):
                preferred = sorted(
                    preferred, key=lambda item: item.max_concurrency, reverse=True
                )
            return preferred[0]
        return self._agents["workflow-orchestrator"]


class TaskReasoner:
    """Thinking layer that builds execution strategies before work starts."""

    def __init__(
        self,
        agent_registry: AgentRegistry,
        strategy_feedback: Optional[StrategyFeedbackStore] = None,
        accuracy_feedback: Optional[AccuracyFeedbackStore] = None,
    ):
        self.agent_registry = agent_registry
        self.strategy_feedback = strategy_feedback or StrategyFeedbackStore()
        self.accuracy_feedback = accuracy_feedback or AccuracyFeedbackStore()

    def plan(
        self, task_type: str, context: Optional[dict[str, Any]] = None
    ) -> OrchestrationPlan:
        context = context or {}
        target = str(context.get("target") or context.get("target_url") or "")
        mode = str(context.get("mode") or "READ_ONLY").upper()
        parsed = urlparse(target if "://" in target else f"https://{target}")
        host = parsed.netloc.lower()
        path = parsed.path.lower()
        high_value = any(
            token in host or token in path
            for token in ("admin", "api", "auth", "login", "billing", "graphql")
        )
        real_mode = mode == "REAL"
        task_key = task_type.lower()
        agent = self.agent_registry.select(task_key, context)

        if task_key in {"workflow", "crawl", "bounty"}:
            crawl_depth = 6 if high_value or real_mode else 3
            concurrency = 6 if high_value else 4
            payload_profile = "guarded-active" if real_mode else "passive-verified"
            verification_level = "deep" if high_value else "standard"
            priority = "high" if high_value else "medium"
            rate_limit = 4 if high_value else 2
        elif task_key in {"training", "ml"}:
            crawl_depth = 0
            concurrency = 1
            payload_profile = "batch-training"
            verification_level = "metrics-and-holdout"
            priority = "high"
            rate_limit = 1
        elif task_key == "voice":
            crawl_depth = 0
            concurrency = 1
            payload_profile = "intent-safe"
            verification_level = "strict"
            priority = "medium"
            rate_limit = 1
        else:
            crawl_depth = 1
            concurrency = 2
            payload_profile = "standard"
            verification_level = "standard"
            priority = "low"
            rate_limit = 2

        notes = []
        if high_value:
            notes.append("High-value target: deeper crawl and verification enabled")
        if real_mode:
            notes.append("REAL mode: guarded-active payload profile selected")
        else:
            notes.append("READ_ONLY mode: passive verification selected")

        historical = self.strategy_feedback.get(
            strategy_name=agent.name,
            task_type=task_key,
        )
        recent_false_positive_rate = 0.0
        if task_key in {"workflow", "crawl", "bounty"}:
            recent_false_positive_rate = max(
                self.accuracy_feedback.recent_false_positive_rate("SQLI"),
                self.accuracy_feedback.recent_false_positive_rate("XSS"),
                self.accuracy_feedback.recent_false_positive_rate("IDOR"),
            )

        if historical.runs >= 3 and historical.score < 0.72:
            concurrency = max(1, concurrency - 1)
            crawl_depth = max(1, crawl_depth - 1)
            verification_level = "strict"
            payload_profile = "passive-verified"
            notes.append(
                f"Historical precision dropped to {historical.precision:.2%}; strategy tightened"
            )
        elif (
            historical.runs >= 3
            and historical.score > 0.9
            and task_key in {"workflow", "crawl", "bounty"}
        ):
            crawl_depth += 1
            notes.append(
                f"Historical precision {historical.precision:.2%}; deeper verification budget granted"
            )

        if recent_false_positive_rate >= 0.15:
            verification_level = "strict"
            concurrency = max(1, concurrency - 1)
            notes.append(
                f"Recent false-positive rate {recent_false_positive_rate:.2%}; verification tightened"
            )

        strategy = ExecutionStrategy(
            agent_name=agent.name,
            task_type=task_key,
            crawl_depth=crawl_depth,
            concurrency=concurrency,
            payload_profile=payload_profile,
            verification_level=verification_level,
            priority=priority,
            rate_limit_per_host=rate_limit,
            notes=notes,
        )
        return OrchestrationPlan(
            request_id=f"ORC-{uuid.uuid4().hex[:12].upper()}",
            task_type=task_key,
            strategy=strategy,
            created_at=datetime.now(UTC).isoformat(),
            context_summary={"host": host, "mode": mode, "high_value": high_value},
        )


class TelemetryMonitor:
    """Low-overhead runtime telemetry collector."""

    def __init__(self) -> None:
        self.started_at = time.time()
        self.request_latencies_ms: deque[float] = deque(maxlen=4096)
        self.request_totals: dict[str, int] = {}
        self.error_totals: dict[str, int] = {}
        self.background_latencies_ms: deque[float] = deque(maxlen=1024)

    def record_request(self, route_key: str, duration_ms: float, success: bool) -> None:
        self.request_latencies_ms.append(duration_ms)
        self.request_totals[route_key] = self.request_totals.get(route_key, 0) + 1
        if not success:
            self.error_totals[route_key] = self.error_totals.get(route_key, 0) + 1

    def record_background(self, duration_ms: float) -> None:
        self.background_latencies_ms.append(duration_ms)

    def snapshot(self) -> dict[str, Any]:
        current_bytes = peak_bytes = 0
        if tracemalloc.is_tracing():
            current_bytes, peak_bytes = tracemalloc.get_traced_memory()

        gpu_metrics = {
            "available": False,
            "memory_allocated_mb": 0.0,
            "memory_reserved_mb": 0.0,
        }
        try:
            import torch

            if torch.cuda.is_available():
                gpu_metrics = {
                    "available": True,
                    "memory_allocated_mb": round(
                        torch.cuda.memory_allocated() / 1024 / 1024, 2
                    ),
                    "memory_reserved_mb": round(
                        torch.cuda.memory_reserved() / 1024 / 1024, 2
                    ),
                }
        except Exception:
            pass

        latencies = list(self.request_latencies_ms)
        bg_latencies = list(self.background_latencies_ms)
        sorted_latencies = sorted(latencies)
        p95 = 0.0
        if sorted_latencies:
            idx = max(0, int(len(sorted_latencies) * 0.95) - 1)
            p95 = sorted_latencies[idx]

        uptime = max(time.time() - self.started_at, 1.0)
        total_requests = sum(self.request_totals.values())

        return {
            "uptime_seconds": round(uptime, 2),
            "request_count": total_requests,
            "requests_per_second": round(total_requests / uptime, 2),
            "avg_request_latency_ms": round(mean(latencies), 2) if latencies else 0.0,
            "p95_request_latency_ms": round(p95, 2),
            "avg_background_latency_ms": round(mean(bg_latencies), 2)
            if bg_latencies
            else 0.0,
            "memory_current_mb": round(current_bytes / 1024 / 1024, 2),
            "memory_peak_mb": round(peak_bytes / 1024 / 1024, 2),
            "gc_counts": gc.get_count(),
            "errors": dict(self.error_totals),
            "gpu": gpu_metrics,
        }


class TelegramNotifier:
    """Optional Telegram notifier for real-time backend alerts."""

    def __init__(self) -> None:
        self.bot_token = os.getenv("YGB_TELEGRAM_BOT_TOKEN", "")
        self.chat_id = os.getenv("YGB_TELEGRAM_CHAT_ID", "")

    @property
    def enabled(self) -> bool:
        return bool(self.bot_token and self.chat_id)

    async def send(self, client: httpx.AsyncClient, message: str) -> bool:
        if not self.enabled:
            return False
        try:
            await client.post(
                f"https://api.telegram.org/bot{self.bot_token}/sendMessage",
                json={"chat_id": self.chat_id, "text": message[:4000]},
            )
            return True
        except Exception:
            return False


class AccuracyEngine:
    """Confidence, duplicate, and advisory-ML verification engine."""

    def __init__(self, feedback_store: Optional[AccuracyFeedbackStore] = None) -> None:
        self.feedback_store = feedback_store or AccuracyFeedbackStore()
        self._ml_available = False
        self._run_inference = None
        self._make_auto_mode_decision = None
        self._local_model_status_cls = None
        try:
            from impl_v1.phase49.governors.g38_self_trained_model import (  # type: ignore
                LocalModelStatus,
                make_auto_mode_decision,
                run_inference,
            )

            self._local_model_status_cls = LocalModelStatus
            self._make_auto_mode_decision = make_auto_mode_decision
            self._run_inference = run_inference
            self._ml_available = True
        except Exception:
            self._ml_available = False

    def _build_fingerprint(self, category: str, title: str, url: str) -> str:
        raw = f"{category}|{title}|{url}".strip().lower()
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]

    def _category_threshold(self, category: str) -> float:
        recent_fpr = self.feedback_store.recent_false_positive_rate(category)
        return min(0.9, 0.58 + (recent_fpr * 0.4))

    def _semantic_duplicate(
        self,
        *,
        category: str,
        title: str,
        url: str,
        prior_findings: Optional[Sequence[dict[str, str]]] = None,
    ) -> tuple[bool, list[str]]:
        if not prior_findings:
            return False, []
        current_title = str(title or "")
        current_url = str(url or "")
        current_host = urlparse(current_url).netloc.lower()
        for prior in prior_findings:
            prior_category = str(prior.get("category") or "")
            if prior_category.upper() != category.upper():
                continue
            prior_title = str(prior.get("title") or "")
            overlap = token_overlap(current_title, prior_title)
            if overlap < 0.82:
                continue
            prior_url = str(prior.get("url") or "")
            prior_host = urlparse(prior_url).netloc.lower()
            if current_host and prior_host and current_host == prior_host:
                return True, [
                    f"Semantic duplicate suppressed (title overlap {overlap:.2f})"
                ]
        return False, []

    def _heuristic_confidence(
        self, category: str, severity: str, evidence: dict[str, Any]
    ) -> tuple[float, list[str], str]:
        severity_weight = {
            "CRITICAL": 0.95,
            "HIGH": 0.88,
            "MEDIUM": 0.78,
            "LOW": 0.68,
            "INFO": 0.55,
        }
        confidence = severity_weight.get(severity.upper(), 0.6)
        notes: list[str] = []
        status = "LIKELY"

        if category in {"HEADERS", "COOKIE", "SSL", "CSP", "CLICKJACKING"}:
            confidence = max(confidence, 0.98)
            status = "CONFIRMED"
            notes.append("Configuration finding verified from response metadata")
        if evidence.get("sql_errors"):
            confidence = max(confidence, 0.99)
            status = "CONFIRMED"
            notes.append("Observed SQL error signature in response")
        if evidence.get("reflected_parameters"):
            confidence = max(confidence, 0.86)
            notes.append("Observed reflected user-controlled parameter")
        if evidence.get("payload_tested"):
            confidence = max(confidence, 0.9)
            notes.append("Passive payload validation completed")
        if evidence.get("response_validated"):
            confidence = max(confidence, 0.94)
            status = "CONFIRMED"
            notes.append("Response validation confirmed expected unsafe behavior")
        if evidence.get("exploit_confirmed"):
            confidence = max(confidence, 0.98)
            status = "CONFIRMED"
            notes.append("Exploit confirmation succeeded in safe validation path")
        if evidence.get("needs_manual_review"):
            confidence = min(confidence, 0.72)
            status = "NEEDS_REVIEW"
            notes.append("Manual review recommended due to heuristic-only detection")

        return confidence, notes, status

    def _ml_score(
        self, category: str, severity: str, title: str, description: str, url: str
    ) -> tuple[float, list[str]]:
        if (
            not self._ml_available
            or self._run_inference is None
            or self._make_auto_mode_decision is None
            or self._local_model_status_cls is None
        ):
            return 0.0, []
        try:
            features = (
                min(len(title) / 120.0, 1.0),
                min(len(description) / 500.0, 1.0),
                1.0 if "http" in url else 0.0,
                1.0 if category in {"SQLI", "XSS", "SSRF", "CVE"} else 0.25,
                {
                    "CRITICAL": 1.0,
                    "HIGH": 0.85,
                    "MEDIUM": 0.6,
                    "LOW": 0.35,
                    "INFO": 0.15,
                }.get(severity.upper(), 0.2),
                min(sum(ch.isdigit() for ch in description) / 20.0, 1.0),
                1.0 if "error" in description.lower() else 0.0,
                1.0 if "missing" in title.lower() else 0.0,
            )
            model_status = self._local_model_status_cls(
                status_id="ORCH-ML-STATUS",
                checkpoint_path="runtime",
                epoch=0,
                train_accuracy=0.0,
                val_accuracy=0.0,
                is_valid=True,
                integrity_hash="runtime",
                created_at=datetime.now(UTC).isoformat(),
                last_trained_at=datetime.now(UTC).isoformat(),
            )
            inference = self._run_inference(features, model_status)
            decision = self._make_auto_mode_decision(
                self._build_fingerprint(category, title, url), inference
            )
            notes = [
                f"Advisory ML score={inference.real_probability:.2f}",
                f"Advisory action={decision.recommended_action}",
            ]
            return float(inference.real_probability), notes
        except Exception:
            return 0.0, []

    def verify(
        self,
        *,
        category: str,
        severity: str,
        title: str,
        description: str,
        url: str,
        evidence: Optional[dict[str, Any]] = None,
        seen_fingerprints: Optional[set[str]] = None,
        prior_findings: Optional[Sequence[dict[str, str]]] = None,
        strategy_name: str = "",
        task_type: str = "",
    ) -> VerificationOutcome:
        evidence = evidence or {}
        fingerprint = self._build_fingerprint(category, title, url)
        duplicate = bool(seen_fingerprints and fingerprint in seen_fingerprints)
        semantic_duplicate, semantic_notes = self._semantic_duplicate(
            category=category,
            title=title,
            url=url,
            prior_findings=prior_findings,
        )
        duplicate = duplicate or semantic_duplicate
        heuristic_confidence, notes, status = self._heuristic_confidence(
            category, severity, evidence
        )
        notes.extend(semantic_notes)
        ml_score, ml_notes = self._ml_score(category, severity, title, description, url)
        notes.extend(ml_notes)
        confidence = heuristic_confidence
        if ml_score > 0:
            confidence = min(0.995, (heuristic_confidence * 0.75) + (ml_score * 0.25))
        threshold = self._category_threshold(category)
        real_check_confirmed = bool(
            evidence.get("response_validated")
            or evidence.get("exploit_confirmed")
            or evidence.get("proof_verified")
            or evidence.get("sql_errors")
        )
        verification_failed = bool(
            evidence.get("verification_failed")
            or (
                evidence.get("payload_tested")
                and not real_check_confirmed
                and not evidence.get("needs_manual_review")
                and confidence < max(threshold, 0.75)
            )
        )
        if duplicate:
            status = "DUPLICATE"
            notes.append("Duplicate finding fingerprint suppressed")
            confidence = min(confidence, 0.2)
        elif verification_failed:
            status = "REJECTED_FALSE_POSITIVE"
            confidence = min(confidence, 0.15)
            notes.append("False-positive candidate rejected by verification layer")
        elif real_check_confirmed:
            status = "CONFIRMED"
            confidence = max(confidence, 0.97)
            notes.append("Real verification checks confirmed this finding")
        elif confidence < threshold:
            status = "REJECTED_FALSE_POSITIVE"
            confidence = min(confidence, threshold)
            notes.append(
                f"Confidence {confidence:.2f} below category threshold {threshold:.2f}"
            )

        validated_statuses = {"CONFIRMED", "REJECTED_FALSE_POSITIVE", "DUPLICATE"}
        if status in validated_statuses:
            actual_positive = status == "CONFIRMED"
            self.feedback_store.add(
                EvaluationRecord(
                    fingerprint=fingerprint,
                    category=category,
                    severity=severity,
                    title=title,
                    description=description,
                    url=url,
                    predicted_positive=True,
                    actual_positive=actual_positive,
                    verification_status=status,
                    confidence=round(confidence, 4),
                    ml_score=round(ml_score, 4),
                    strategy_name=strategy_name,
                    task_type=task_type,
                    duplicate=duplicate,
                    false_positive=not actual_positive,
                    false_negative=False,
                    validated=True,
                    validation_source="verification-layer",
                    evidence=dict(evidence),
                )
            )
        return VerificationOutcome(
            fingerprint=fingerprint,
            status=status,
            confidence=round(confidence, 4),
            duplicate=duplicate,
            ml_score=round(ml_score, 4),
            notes=notes,
        )


@dataclass(slots=True)
class QueuedTask:
    task_id: str
    name: str
    task_type: str
    func: Callable[..., Any]
    args: tuple[Any, ...]
    kwargs: dict[str, Any]
    future: asyncio.Future[Any]
    priority: str = "medium"
    submitted_at: float = field(default_factory=time.time)
    retries_remaining: int = 2


class AsyncTaskQueue:
    """Shared async task queue with retry support."""

    PRIORITY_ORDER = {"high": 0, "medium": 1, "low": 2}

    def __init__(
        self,
        telemetry: TelemetryMonitor,
        worker_count: int = 2,
        max_queue_size: int = 512,
    ) -> None:
        self.telemetry = telemetry
        self.worker_count = worker_count
        self.max_queue_size = max_queue_size
        self._queue: asyncio.PriorityQueue[tuple[int, float, QueuedTask]] = (
            asyncio.PriorityQueue(maxsize=max_queue_size)
        )
        self._workers: list[asyncio.Task[Any]] = []
        self._running = False

    def queue_pressure(self) -> float:
        return min(self._queue.qsize() / max(self.max_queue_size, 1), 1.0)

    def is_overloaded(self) -> bool:
        return self._queue.full() or self.queue_pressure() >= 0.9

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        for idx in range(self.worker_count):
            self._workers.append(
                asyncio.create_task(
                    self._worker(idx), name=f"ygb-orchestrator-worker-{idx}"
                )
            )

    async def shutdown(self) -> None:
        self._running = False
        for worker in self._workers:
            worker.cancel()
        if self._workers:
            await asyncio.gather(*self._workers, return_exceptions=True)
        self._workers.clear()

    async def submit(
        self,
        name: str,
        task_type: str,
        func: Callable[..., Any],
        priority: str = "medium",
        *args: Any,
        **kwargs: Any,
    ) -> Any:
        loop = asyncio.get_running_loop()
        future: asyncio.Future[Any] = loop.create_future()
        normalized_priority = priority if priority in self.PRIORITY_ORDER else "medium"
        if self.is_overloaded() and normalized_priority == "low":
            raise QueueOverloadedError(
                f"Task queue overloaded; rejected low-priority task {name}"
            )

        task = QueuedTask(
            task_id=f"TSK-{uuid.uuid4().hex[:12].upper()}",
            name=name,
            task_type=task_type,
            func=func,
            args=args,
            kwargs=kwargs,
            future=future,
            priority=normalized_priority,
        )
        await self._queue.put(
            (self.PRIORITY_ORDER[normalized_priority], task.submitted_at, task)
        )
        return await future

    async def _worker(self, _: int) -> None:
        while self._running:
            _, _, task = await self._queue.get()
            started = time.perf_counter()
            try:
                if inspect.iscoroutinefunction(task.func):
                    result = await task.func(*task.args, **task.kwargs)
                else:
                    result = await asyncio.to_thread(
                        task.func, *task.args, **task.kwargs
                    )
                if not task.future.done():
                    task.future.set_result(result)
            except Exception as exc:
                if task.retries_remaining > 0 and self._running:
                    task.retries_remaining -= 1
                    await self._queue.put(
                        (self.PRIORITY_ORDER.get(task.priority, 1), time.time(), task)
                    )
                elif not task.future.done():
                    task.future.set_exception(exc)
            finally:
                self.telemetry.record_background((time.perf_counter() - started) * 1000)
                self._queue.task_done()

    def snapshot(self) -> dict[str, Any]:
        return {
            "queued": self._queue.qsize(),
            "workers": len(self._workers),
            "running": self._running,
            "max_queue_size": self.max_queue_size,
            "queue_pressure": round(self.queue_pressure(), 4),
            "overloaded": self.is_overloaded(),
        }


class BackendOrchestrator:
    """Central orchestration control plane for the YGB backend."""

    def __init__(self) -> None:
        self.cache = AsyncLRUCache(maxsize=1024)
        self.agents = AgentRegistry()
        self.isolation = AgentIsolationManager()
        self.accuracy_feedback = AccuracyFeedbackStore()
        self.strategy_feedback = StrategyFeedbackStore()
        self.reasoner = TaskReasoner(
            self.agents,
            self.strategy_feedback,
            self.accuracy_feedback,
        )
        self.telemetry = TelemetryMonitor()
        self.accuracy = AccuracyEngine(self.accuracy_feedback)
        self.notifier = TelegramNotifier()
        self.vector_memory = VectorMemoryStore(max_entries_per_namespace=256)
        self.resource_governor = ResourceGovernor()
        self.state_persistence = StatePersistence()
        self.cluster = DistributedClusterCoordinator()
        self.task_queue = AsyncTaskQueue(
            self.telemetry,
            worker_count=max(2, int(os.getenv("YGB_ORCHESTRATOR_WORKERS", "2"))),
            max_queue_size=max(
                32, int(os.getenv("YGB_ORCHESTRATOR_QUEUE_SIZE", "512"))
            ),
        )
        self.http_client: Optional[httpx.AsyncClient] = None
        self._cleanup_task: Optional[asyncio.Task[Any]] = None
        self._persist_task: Optional[asyncio.Task[Any]] = None
        self._status_task: Optional[asyncio.Task[Any]] = None
        self._cluster_task: Optional[asyncio.Task[Any]] = None
        self._state_policies: dict[str, dict[str, Any]] = {}
        self._state_access: dict[str, dict[str, float]] = {}
        self._state_store_refs: dict[str, dict[str, Any]] = {}
        self._request_counter = 0
        self._resource_snapshot = ResourceSnapshot(
            0.0, 0.0, 0.0, 0.0, 0.0, False, 1.0, 1.0, False
        )
        self._recovered_state: dict[str, Any] = {}
        self._state_dirty = False
        self._status_snapshot: dict[str, Any] = {}
        self._status_providers: dict[str, Callable[[], Any]] = {}

    async def startup(self) -> None:
        if self.http_client is None:
            self.http_client = httpx.AsyncClient(
                follow_redirects=True,
                timeout=httpx.Timeout(20.0, connect=10.0),
                limits=httpx.Limits(max_connections=40, max_keepalive_connections=20),
                headers={"User-Agent": "YGB-Orchestrator/2.0"},
            )
        if not tracemalloc.is_tracing():
            tracemalloc.start()
        await self.cluster.startup()
        self._recovered_state = await self.state_persistence.load()
        if not self._recovered_state:
            self._recovered_state = await self.cluster.load_canonical_state()
        self._register_default_agents()
        await self._restore_vector_memory()
        self._restore_learning_state()
        await self.task_queue.start()
        if self._cleanup_task is None:
            self._cleanup_task = asyncio.create_task(
                self._cleanup_loop(), name="ygb-store-cleanup"
            )
        if self._persist_task is None:
            self._persist_task = asyncio.create_task(
                self._persist_loop(), name="ygb-state-persist"
            )
        if self._status_task is None:
            self._status_task = asyncio.create_task(
                self._status_loop(), name="ygb-status-cache"
            )
        if self._cluster_task is None:
            self._cluster_task = asyncio.create_task(
                self._cluster_loop(), name="ygb-cluster-loop"
            )
        await self.refresh_status_snapshot()

    async def shutdown(self) -> None:
        if self._cluster_task is not None:
            self._cluster_task.cancel()
            await asyncio.gather(self._cluster_task, return_exceptions=True)
            self._cluster_task = None
        if self._status_task is not None:
            self._status_task.cancel()
            await asyncio.gather(self._status_task, return_exceptions=True)
            self._status_task = None
        if self._persist_task is not None:
            self._persist_task.cancel()
            await asyncio.gather(self._persist_task, return_exceptions=True)
            self._persist_task = None
        if self._cleanup_task is not None:
            self._cleanup_task.cancel()
            await asyncio.gather(self._cleanup_task, return_exceptions=True)
            self._cleanup_task = None
        await self._persist_state(force=True)
        await self.task_queue.shutdown()
        await self.cache.clear()
        if self.http_client is not None:
            await self.http_client.aclose()
            self.http_client = None
        await self.cluster.shutdown()

    def _register_default_agents(self) -> None:
        if self.agents.all():
            return
        self.agents.register(
            AgentProfile(
                "workflow-orchestrator",
                ("workflow", "request"),
                "Routes and supervises workflow execution",
                6,
            )
        )
        self.agents.register(
            AgentProfile(
                "crawler-agent",
                ("crawl", "bounty"),
                "Optimized async crawler and analyzer",
                8,
            )
        )
        self.agents.register(
            AgentProfile(
                "training-agent",
                ("training", "ml"),
                "GPU training and online learning coordinator",
                1,
            )
        )
        self.agents.register(
            AgentProfile(
                "voice-agent", ("voice",), "Voice intent analysis and routing", 2
            )
        )
        self.agents.register(
            AgentProfile(
                "notification-agent", ("notification",), "Realtime alert delivery", 4
            )
        )
        for agent in self.agents.all():
            self.isolation.register(agent)

    async def _restore_vector_memory(self) -> None:
        memory_snapshot = (
            self._recovered_state.get("vector_memory")
            if isinstance(self._recovered_state, dict)
            else None
        )
        if isinstance(memory_snapshot, dict):
            await self.vector_memory.restore(memory_snapshot)

    def _restore_learning_state(self) -> None:
        if not isinstance(self._recovered_state, dict):
            return
        strategy_snapshot = self._recovered_state.get("strategy_feedback")
        if isinstance(strategy_snapshot, dict):
            self.strategy_feedback.restore(strategy_snapshot)

    async def apply_recovered_state(
        self, store_name: str, store: dict[str, Any]
    ) -> None:
        if not isinstance(self._recovered_state, dict):
            return
        stores = self._recovered_state.get("stores")
        if not isinstance(stores, dict):
            return
        recovered = stores.get(store_name)
        if not isinstance(recovered, dict):
            return
        store.clear()
        store.update(recovered)
        self._state_store_refs[store_name] = store
        now = time.time()
        self._state_access[store_name] = {key: now for key in store.keys()}

    def configure_state_store(
        self, name: str, *, ttl_seconds: float, max_items: int
    ) -> None:
        self._state_policies[name] = {
            "ttl_seconds": ttl_seconds,
            "max_items": max_items,
        }
        self._state_access.setdefault(name, {})

    def remember_state(
        self, store_name: str, store: dict[str, Any], key: str, value: Any
    ) -> Any:
        self._state_store_refs[store_name] = store
        store[key] = value
        self._state_access.setdefault(store_name, {})[key] = time.time()
        self._prune_store(store_name, store)
        self._state_dirty = True
        return value

    def touch_state(self, store_name: str, key: str) -> None:
        self._state_access.setdefault(store_name, {})[key] = time.time()
        self._state_dirty = True

    def drop_state(self, store_name: str, store: dict[str, Any], key: str) -> None:
        store.pop(key, None)
        self._state_access.setdefault(store_name, {}).pop(key, None)
        self._state_dirty = True

    def _prune_store(self, store_name: str, store: dict[str, Any]) -> None:
        policy = self._state_policies.get(store_name)
        access = self._state_access.setdefault(store_name, {})
        if not policy:
            return
        ttl_seconds = float(policy["ttl_seconds"])
        max_items = int(policy["max_items"])
        now = time.time()
        expired = [key for key, seen in access.items() if (now - seen) > ttl_seconds]
        for key in expired:
            store.pop(key, None)
            access.pop(key, None)
        while len(store) > max_items and access:
            oldest_key = min(access, key=access.get)
            store.pop(oldest_key, None)
            access.pop(oldest_key, None)

    async def _cleanup_loop(self) -> None:
        while True:
            await asyncio.sleep(60)
            for store_name, store in list(self._state_store_refs.items()):
                self._prune_store(store_name, store)
            self._resource_snapshot = self.resource_governor.snapshot(
                queue_pressure=self.task_queue.queue_pressure(),
                request_pressure=min(
                    self.telemetry.snapshot().get("requests_per_second", 0.0) / 50.0,
                    1.0,
                ),
            )

    async def _cluster_loop(self) -> None:
        while True:
            await self.cluster.heartbeat({"queue": self.task_queue.snapshot()})
            await self.cluster.ensure_leader()
            anomalies = await self.cluster.detect_anomalies()
            if anomalies:
                await self._recover_from_cluster(anomalies)
            if anomalies and self.http_client is not None:
                await self.notifier.send(
                    self.http_client,
                    f"YGB cluster anomaly detected on {self.cluster.node_id}: {anomalies[0]['type']}",
                )
            await asyncio.sleep(self.cluster.heartbeat_interval_seconds)

    async def _recover_from_cluster(self, anomalies: list[dict[str, Any]]) -> None:
        anomaly_types = {item.get("type") for item in anomalies}
        if "state_divergence" not in anomaly_types:
            return
        canonical = await self.cluster.load_canonical_state()
        stores = canonical.get("stores") if isinstance(canonical, dict) else None
        if not isinstance(stores, dict):
            return
        for name, store in self._state_store_refs.items():
            recovered = stores.get(name)
            if isinstance(recovered, dict):
                store.clear()
                store.update(recovered)
                self._state_access[name] = {key: time.time() for key in store.keys()}
        self._state_dirty = True

    async def _persist_loop(self) -> None:
        while True:
            await asyncio.sleep(15)
            await self._persist_state(force=False)

    async def _status_loop(self) -> None:
        while True:
            await asyncio.sleep(5)
            await self.refresh_status_snapshot()

    def register_status_provider(self, name: str, provider: Callable[[], Any]) -> None:
        self._status_providers[name] = provider

    async def refresh_status_snapshot(self) -> dict[str, Any]:
        snapshot = self.snapshot()
        snapshot["cluster"] = await self.cluster.snapshot()
        providers: dict[str, Any] = {}
        for name, provider in self._status_providers.items():
            try:
                providers[name] = await _run_maybe_async(provider)
            except Exception as exc:
                providers[name] = {"error": str(exc)}
        snapshot["providers"] = providers
        snapshot["generated_at"] = datetime.now(UTC).isoformat()
        self._status_snapshot = snapshot
        return snapshot

    def get_cached_status_snapshot(self) -> dict[str, Any]:
        return self._status_snapshot or self.snapshot()

    async def _persist_state(self, *, force: bool) -> None:
        if not force and not self._state_dirty:
            return
        stores = {name: dict(store) for name, store in self._state_store_refs.items()}
        payload = {
            "saved_at": datetime.now(UTC).isoformat(),
            "stores": stores,
            "state_access": {
                name: dict(values) for name, values in self._state_access.items()
            },
            "vector_memory": await self.vector_memory.snapshot(),
            "strategy_feedback": self.strategy_feedback.snapshot(),
            "accuracy_feedback": self.accuracy_feedback.summary(),
            "telemetry": self.telemetry.snapshot(),
            "resource_snapshot": {
                "cpu_load_ratio": self._resource_snapshot.cpu_load_ratio,
                "memory_load_ratio": self._resource_snapshot.memory_load_ratio,
                "gpu_memory_ratio": self._resource_snapshot.gpu_memory_ratio,
                "request_pressure": self._resource_snapshot.request_pressure,
                "queue_pressure": self._resource_snapshot.queue_pressure,
                "overloaded": self._resource_snapshot.overloaded,
                "suggested_concurrency_scale": self._resource_snapshot.suggested_concurrency_scale,
                "suggested_batch_scale": self._resource_snapshot.suggested_batch_scale,
                "paused_training": self._resource_snapshot.paused_training,
            },
        }
        await self.state_persistence.save(payload)
        await self.cluster.replicate_state(payload)
        self._state_dirty = False

    def plan_task(
        self, task_type: str, context: Optional[dict[str, Any]] = None
    ) -> OrchestrationPlan:
        plan = self.reasoner.plan(task_type, context)
        scale = self._resource_snapshot.suggested_concurrency_scale
        if scale < 1.0:
            plan.strategy.concurrency = max(
                1, int(math.ceil(plan.strategy.concurrency * scale))
            )
            plan.strategy.notes.append(
                f"Adaptive throttling applied: concurrency scaled to {plan.strategy.concurrency}"
            )
        if self.task_queue.queue_pressure() >= 0.75 and plan.strategy.task_type in {
            "workflow",
            "crawl",
            "bounty",
        }:
            plan.strategy.crawl_depth = max(1, plan.strategy.crawl_depth - 1)
            plan.strategy.notes.append("Queue pressure detected: crawl depth reduced")
        return plan

    async def handle_http_request(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        self._request_counter += 1
        task_type = self._infer_task_type(request.url.path)
        self._resource_snapshot = self.resource_governor.snapshot(
            queue_pressure=self.task_queue.queue_pressure(),
            request_pressure=min(
                self.telemetry.snapshot().get("requests_per_second", 0.0) / 50.0, 1.0
            ),
        )
        plan = self.plan_task(
            task_type, {"target": str(request.url), "method": request.method}
        )
        protected_path = request.url.path in {"/api/health", "/api/orchestrator/status"}
        if (
            self._resource_snapshot.overloaded
            and plan.strategy.priority == "low"
            and not protected_path
        ):
            response = JSONResponse(
                status_code=503,
                content={
                    "error": "backend_overloaded",
                    "message": "System is under heavy load; low-priority request rejected",
                    "request_id": plan.request_id,
                },
            )
            response.headers["Retry-After"] = "5"
            response.headers["X-YGB-Orchestrated"] = "true"
            response.headers["X-YGB-Agent"] = plan.strategy.agent_name
            response.headers["X-YGB-Request-Id"] = plan.request_id
            response.headers["X-YGB-Task-Type"] = plan.task_type
            return response
        request.state.orchestration_plan = plan
        started = time.perf_counter()
        success = False
        try:
            response = await call_next(request)
            success = response.status_code < 500
        except Exception as exc:
            if self.http_client is not None:
                await self.notifier.send(
                    self.http_client,
                    f"YGB backend error: {request.method} {request.url.path}\n{exc}",
                )
            self.telemetry.record_request(
                f"{request.method} {request.url.path}",
                (time.perf_counter() - started) * 1000,
                False,
            )
            raise
        duration_ms = (time.perf_counter() - started) * 1000
        self.telemetry.record_request(
            f"{request.method} {request.url.path}", duration_ms, success
        )
        response.headers.setdefault("Cache-Control", "no-store")
        response.headers["X-YGB-Orchestrated"] = "true"
        response.headers["X-YGB-Agent"] = plan.strategy.agent_name
        response.headers["X-YGB-Request-Id"] = plan.request_id
        response.headers["X-YGB-Latency-Ms"] = f"{duration_ms:.2f}"
        response.headers["X-YGB-Task-Type"] = plan.task_type
        return response

    async def submit_background(
        self,
        name: str,
        task_type: str,
        func: Callable[..., Any],
        priority: str = "medium",
        *args: Any,
        **kwargs: Any,
    ) -> Any:
        return await self.task_queue.submit(
            name, task_type, func, priority, *args, **kwargs
        )

    def dispatch_background(
        self,
        name: str,
        task_type: str,
        func: Callable[..., Any],
        priority: str = "medium",
        *args: Any,
        **kwargs: Any,
    ) -> None:
        async def _runner() -> None:
            try:
                await self.submit_background(
                    name, task_type, func, priority, *args, **kwargs
                )
            except QueueOverloadedError:
                if self.http_client is not None:
                    await self.notifier.send(
                        self.http_client,
                        f"YGB backpressure rejected task: {name}",
                    )
            except Exception as exc:
                if self.http_client is not None:
                    await self.notifier.send(
                        self.http_client,
                        f"YGB background task failed: {name}\n{exc}",
                    )

        asyncio.create_task(_runner(), name=f"ygb-bg-{name}")

    async def remember_experience(
        self,
        agent_name: str,
        content: str,
        metadata: Optional[dict[str, Any]] = None,
        *,
        namespace: Optional[str] = None,
    ) -> MemoryExperience:
        namespace = namespace or self.isolation.memory_namespace(agent_name)
        self.isolation.assert_dataset_access(agent_name, namespace)
        experience = await self.vector_memory.add(namespace, content, metadata)
        await self.cluster.publish_memory(
            namespace,
            {
                "memory_id": experience.memory_id,
                "content": experience.content,
                "metadata": experience.metadata,
                "created_at": experience.created_at,
                "node_id": self.cluster.node_id,
            },
        )
        self._state_dirty = True
        return experience

    async def retrieve_experience(
        self,
        agent_name: str,
        query: str,
        *,
        namespace: Optional[str] = None,
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        namespace = namespace or self.isolation.memory_namespace(agent_name)
        self.isolation.assert_dataset_access(agent_name, namespace)
        local = await self.vector_memory.retrieve(namespace, query, limit=limit)
        shared = await self.cluster.read_shared_memory(namespace, limit=limit * 2)
        if not shared:
            return local

        seen_ids = {item["memory_id"] for item in local if item.get("memory_id")}
        for record in shared:
            memory_id = str(record.get("memory_id", ""))
            if memory_id and memory_id in seen_ids:
                continue
            score = _cosine_similarity(
                _vectorize(query), _vectorize(str(record.get("content", "")))
            )
            if score >= 0.2:
                local.append(
                    {
                        "memory_id": memory_id,
                        "score": round(score, 4),
                        "content": record.get("content", ""),
                        "metadata": record.get("metadata", {}),
                        "created_at": record.get("created_at"),
                    }
                )
        local.sort(key=lambda item: item.get("score", 0.0), reverse=True)
        return local[:limit]

    def record_strategy_outcome(
        self,
        *,
        strategy_name: str,
        task_type: str,
        verified_findings: int,
        rejected_findings: int,
        duplicate_findings: int,
    ) -> dict[str, Any]:
        entry = self.strategy_feedback.record(
            strategy_name=strategy_name,
            task_type=task_type,
            verified_findings=verified_findings,
            rejected_findings=rejected_findings,
            duplicate_findings=duplicate_findings,
        )
        self._state_dirty = True
        return entry.to_dict()

    def snapshot(self) -> dict[str, Any]:
        return {
            "telemetry": self.telemetry.snapshot(),
            "queue": self.task_queue.snapshot(),
            "resources": {
                "cpu_load_ratio": self._resource_snapshot.cpu_load_ratio,
                "memory_load_ratio": self._resource_snapshot.memory_load_ratio,
                "gpu_memory_ratio": self._resource_snapshot.gpu_memory_ratio,
                "request_pressure": self._resource_snapshot.request_pressure,
                "queue_pressure": self._resource_snapshot.queue_pressure,
                "overloaded": self._resource_snapshot.overloaded,
                "suggested_concurrency_scale": self._resource_snapshot.suggested_concurrency_scale,
                "suggested_batch_scale": self._resource_snapshot.suggested_batch_scale,
                "paused_training": self._resource_snapshot.paused_training,
            },
            "agents": [
                {
                    "name": agent.name,
                    "specialties": list(agent.specialties),
                    "description": agent.description,
                    "max_concurrency": agent.max_concurrency,
                }
                for agent in self.agents.all()
            ],
            "isolation": self.isolation.snapshot(),
            "memory": {"namespaces": self.vector_memory.counts()},
            "accuracy": self.accuracy_feedback.summary(),
            "strategy_feedback": self.strategy_feedback.snapshot(),
            "cluster": self._status_snapshot.get("cluster")
            if self._status_snapshot
            else {},
            "stores": {
                name: {
                    "tracked": len(items),
                    **policy,
                }
                for name, items in self._state_access.items()
                for policy in [self._state_policies.get(name, {})]
            },
            "recovered": bool(self._recovered_state),
        }

    def _infer_task_type(self, path: str) -> str:
        lowered = path.lower()
        if "voice" in lowered:
            return "voice"
        if (
            "g38" in lowered
            or "training" in lowered
            or "dataset" in lowered
            or "gpu" in lowered
        ):
            return "training"
        if (
            "bounty" in lowered
            or "workflow" in lowered
            or lowered.startswith("/ws/bounty")
        ):
            return "workflow"
        if lowered.startswith("/ws/hunter") or "hunter" in lowered:
            return "crawl"
        return "request"

    def cache_headers(self, *, max_age: int, immutable: bool = False) -> dict[str, str]:
        value = f"public, max-age={max_age}"
        if immutable:
            value += ", immutable"
        return {"Cache-Control": value}
