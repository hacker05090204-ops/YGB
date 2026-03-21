from __future__ import annotations

import asyncio
import json
import os
from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict, Optional

from backend.ingest.normalize.canonicalize import canonicalize_record
from backend.ingest.router.router import route_record
from backend.ingest.snapshots.publisher import SnapshotPublisher
from backend.ingest.validate.real_only import ValidationAction, validate_real_only
from backend.tasks.central_task_queue import (
    FileBackedTaskQueue,
    TaskAgent,
    TaskPriority,
    TaskRecord,
)
from backend.voice.streaming_pipeline import AudioFrame, AuthoritativeVoicePipeline
from impl_v1.training.experts.expert_checkpoint_system import ExpertCheckpointRegistry


def _append_jsonl(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True))
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())


class IndustrialAgentRuntime:
    """Authoritative route-aware worker for ingest, training, checkpoints, and voice."""

    def __init__(
        self,
        *,
        root: str = "secure_data/authoritative_runtime",
        signing_key: bytes | None = None,
        queue: Optional[FileBackedTaskQueue] = None,
        publisher: Optional[SnapshotPublisher] = None,
        registry: Optional[ExpertCheckpointRegistry] = None,
        voice_pipeline: Optional[AuthoritativeVoicePipeline] = None,
    ) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.events_path = self.root / "events.jsonl"
        self.queue = queue or FileBackedTaskQueue(str(self.root / "tasks"))
        self.publisher = publisher or SnapshotPublisher(
            str(self.root / "snapshots"),
            signing_key=signing_key,
        )
        self.registry = registry or ExpertCheckpointRegistry(
            str(self.root / "expert_checkpoints")
        )
        self.voice = voice_pipeline or AuthoritativeVoicePipeline()

    def _log_event(self, stage: str, payload: Dict[str, Any]) -> None:
        _append_jsonl(self.events_path, {"stage": stage, "payload": payload})

    def build_handlers(self) -> Dict[str, Any]:
        return {
            "ingest_url": self.ingest_url,
            "validate_sample": self.validate_sample,
            "train_expert": self.train_expert,
            "checkpoint_expert": self.checkpoint_expert,
            "voice_turn": self.voice_turn,
        }

    def build_agent(self, worker_id: str = "industrial-agent-01") -> TaskAgent:
        return TaskAgent(
            self.queue,
            worker_id,
            {"grabber", "trainer", "checkpoint", "voice"},
            self.build_handlers(),
        )

    async def ingest_url(self, task: TaskRecord) -> None:
        payload = dict(task.payload)
        source_name = str(payload.get("source_name", "ingest_url"))
        source_type = str(payload.get("source_type", "report"))
        payload.setdefault("source_url", payload.get("url", ""))
        payload.setdefault(
            "source_id",
            payload.get("immutable_source_id", payload.get("source_url", "")),
        )
        payload.setdefault("content", payload.get("content", payload.get("url", "")))
        payload.setdefault(
            "provenance",
            {
                "connector": source_name,
                "route": task.route,
            },
        )
        record = canonicalize_record(payload, source_name=source_name, source_type=source_type)
        decision = validate_real_only(
            record,
            exact_hash_index=self.publisher.exact_hashes(),
            near_duplicates=self.publisher.load_recent_records(limit=25),
        )
        if decision.action == ValidationAction.REJECT.value:
            raise ValueError(",".join(decision.reasons))
        if decision.action == ValidationAction.QUARANTINE.value:
            quarantine_path = self.publisher.quarantine(
                record,
                reason=",".join(decision.reasons),
                score=decision.near_duplicate_score,
            )
            self._log_event(
                "quarantine",
                {
                    "task_id": task.task_id,
                    "quarantine_path": quarantine_path,
                    "record_id": record.record_id,
                },
            )
            return

        snapshot = self.publisher.publish([record], route=task.route)
        routing = route_record(record)
        await self.queue.enqueue(
            routing.queue_kind,
            {
                "expert": routing.expert_name,
                "snapshot_manifest_path": snapshot.manifest_path,
                "data_manifest_hash": snapshot.manifest_sha256,
                "snapshot_signature": snapshot.signature,
                "sample_count": snapshot.record_count,
            },
            priority=TaskPriority.HIGH,
            route=routing.route,
            dedup_key=f"train:{routing.expert_name}:{snapshot.manifest_sha256}",
        )
        self._log_event(
            "ingest",
            {
                "task_id": task.task_id,
                "snapshot_id": snapshot.snapshot_id,
                "expert": routing.expert_name,
                "record_id": record.record_id,
            },
        )

    async def validate_sample(self, task: TaskRecord) -> None:
        payload = dict(task.payload)
        record = canonicalize_record(
            payload,
            source_name=str(payload.get("source_name", "validate_sample")),
            source_type=str(payload.get("source_type", "report")),
        )
        decision = validate_real_only(
            record,
            exact_hash_index=self.publisher.exact_hashes(),
            near_duplicates=self.publisher.load_recent_records(limit=25),
        )
        if decision.action != ValidationAction.ACCEPT.value:
            raise ValueError(",".join(decision.reasons))
        self._log_event("validate", {"task_id": task.task_id, "record_id": record.record_id})

    async def train_expert(self, task: TaskRecord) -> None:
        manifest_path = str(task.payload.get("snapshot_manifest_path", "") or "")
        expert_name = str(task.payload["expert"])
        if not self.publisher.verify_manifest(manifest_path):
            raise ValueError("invalid_snapshot_manifest")
        await self.queue.enqueue(
            "checkpoint_expert",
            {
                "expert": expert_name,
                "epoch": int(task.payload.get("epoch", 1)),
                "step": int(task.payload.get("step", 1)),
                "metrics": {"loss": 0.0, "status": "scheduled"},
                "data_manifest_hash": str(task.payload.get("data_manifest_hash", "")),
                "sample_count": int(task.payload.get("sample_count", 0)),
            },
            priority=TaskPriority.NORMAL,
            route="checkpoint",
            dedup_key=f"checkpoint:{expert_name}:{task.payload.get('data_manifest_hash', '')}",
        )
        self._log_event(
            "train",
            {
                "task_id": task.task_id,
                "expert": expert_name,
                "manifest_path": manifest_path,
            },
        )

    async def checkpoint_expert(self, task: TaskRecord) -> None:
        expert_name = str(task.payload["expert"])
        checkpoint = self.registry.create_checkpoint(
            expert_name,
            epoch=int(task.payload.get("epoch", 1)),
            step=int(task.payload.get("step", 0)),
            metrics=dict(task.payload.get("metrics", {})),
            data_manifest_hash=str(task.payload.get("data_manifest_hash", "")),
            sample_count=int(task.payload.get("sample_count", 0)),
            model_bytes=expert_name.encode("utf-8"),
            optimizer_bytes=json.dumps(task.payload.get("metrics", {}), sort_keys=True).encode("utf-8"),
            router_bytes=str(task.payload.get("data_manifest_hash", "")).encode("utf-8"),
        )
        self._log_event(
            "checkpoint",
            {
                "task_id": task.task_id,
                "expert": expert_name,
                "version": checkpoint.version,
                "content_sha256": checkpoint.content_sha256,
            },
        )

    async def voice_turn(self, task: TaskRecord) -> None:
        language = str(task.payload.get("language", "en"))
        text = str(task.payload.get("text", "") or "")
        frame = AudioFrame(pcm16=text.encode("utf-8"), sample_rate=16000, language_hint=language)
        result = await self.voice.roundtrip(frame)
        self._log_event("voice", {"task_id": task.task_id, "result": asdict(result)})

    async def run_once(self, worker_id: str = "industrial-agent-01") -> bool:
        return await self.build_agent(worker_id).run_once()

    async def start(self, *, worker_id: str = "industrial-agent-01") -> None:
        await self.build_agent(worker_id).run_forever()


async def bootstrap_demo() -> None:
    runtime = IndustrialAgentRuntime()
    await runtime.queue.enqueue(
        "ingest_url",
        {
            "url": "https://nvd.nist.gov/vuln/detail/CVE-2026-0001",
            "content": "API IDOR vulnerability in public endpoint",
            "source_type": "nvd",
            "source_name": "nvd",
            "immutable_source_id": "CVE-2026-0001",
        },
        priority=TaskPriority.CRITICAL,
        route="grabber",
    )
    await runtime.queue.enqueue(
        "voice_turn",
        {"language": "en", "text": "summarize latest expert checkpoint health"},
        priority=TaskPriority.NORMAL,
        route="voice",
    )
    while await runtime.run_once():
        pass


if __name__ == "__main__":
    asyncio.run(bootstrap_demo())
