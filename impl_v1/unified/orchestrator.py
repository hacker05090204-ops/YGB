from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass, field
from datetime import datetime, UTC
import json
import os
from typing import Any, Callable, Dict, Iterable, List, Optional

from impl_v1.agents import AgentOrchestrator, AgentRegistry, RegisteredAgent
from impl_v1.enterprise.training_controller import TrainingController, TrainingMode
from impl_v1.training.accuracy.engine import AccuracyEngine
from impl_v1.training.distributed.distributed_training_orchestrator import (
    DistributedTrainingOrchestrator,
    NodeResource,
    TrainingSnapshot,
    ValidationSnapshot,
)
from impl_v1.training.distributed.scaling_efficiency import (
    measure_efficiency,
    should_disable_node,
)
from impl_v1.training.distributed.training_monitor import TrainingMonitor
from impl_v1.training.voice.streaming_pipeline import (
    StreamingVoicePipeline,
    StreamingVoiceSession,
)

from .memory import UnifiedMemoryStore
from .performance import ComputeSnapshot, PerformanceIntelligence
from .storage import TieredCheckpointStorageEngine


@dataclass
class UnifiedTrainingOutcome:
    parallelism_plan: Dict[str, Any]
    checkpoint_id: str = ""
    rollback_action: Dict[str, Any] = field(default_factory=dict)
    scale_decision: Dict[str, Any] = field(default_factory=dict)
    tuning: Dict[str, Any] = field(default_factory=dict)
    scaling_efficiency: float = 0.0
    disable_node_reason: str = ""
    storage_record: Dict[str, Any] = field(default_factory=dict)


@dataclass
class UnifiedAccuracyOutcome:
    findings: int
    retraining_queue: List[Dict[str, Any]]
    duplicates: List[Dict[str, Any]]
    memory_records: List[str]


class UnifiedAIOrchestrator:
    """Global control plane spanning training, agents, voice, memory, and storage."""

    def __init__(
        self,
        *,
        state_path: str = os.path.join("reports", "unified_system_status.json"),
        memory_path: str = os.path.join("secure_data", "unified_memory.json"),
        storage_root: str = os.path.join("secure_data", "tiered_storage"),
        training_dashboard_path: str = os.path.join("reports", "unified_training_dashboard.json"),
        agent_registry: Optional[AgentRegistry] = None,
        distributed_orchestrator: Optional[DistributedTrainingOrchestrator] = None,
        accuracy_engine: Optional[AccuracyEngine] = None,
        voice_pipeline: Optional[StreamingVoicePipeline] = None,
    ):
        self.state_path = state_path
        self.agent_registry = agent_registry or AgentRegistry()
        self.agent_orchestrator = AgentOrchestrator(self.agent_registry)
        self.training_controller = TrainingController()
        self.distributed_orchestrator = distributed_orchestrator or DistributedTrainingOrchestrator()
        self.accuracy_engine = accuracy_engine or AccuracyEngine()
        self.memory = UnifiedMemoryStore(memory_path)
        self.storage = TieredCheckpointStorageEngine(storage_root)
        self.performance = PerformanceIntelligence()
        self.monitor = TrainingMonitor(training_dashboard_path)
        self.voice_pipeline = voice_pipeline or StreamingVoicePipeline(self.agent_orchestrator)
        self._voice_sessions: Dict[str, StreamingVoiceSession] = {}
        self._executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="unified-system")
        self._latest_checkpoint_manifest: Dict[str, Any] = {}
        self._register_builtin_agents()
        self._write_status()

    def _register_builtin_agents(self) -> None:
        if self.agent_registry.get("voice-stream") is None:
            self.agent_registry.register(
                RegisteredAgent(
                    agent_id="voice-stream",
                    role="voice",
                    subscriptions=["voice.reasoning"],
                    capabilities=["voice", "reasoning"],
                    handler=self._voice_reasoning_agent,
                    metadata={"managed_by": "unified_orchestrator"},
                )
            )
        if self.agent_registry.get("memory-manager") is None:
            self.agent_registry.register(
                RegisteredAgent(
                    agent_id="memory-manager",
                    role="memory",
                    subscriptions=["memory.retrieve"],
                    capabilities=["memory", "retrieval"],
                    handler=self._memory_agent,
                    metadata={"managed_by": "unified_orchestrator"},
                )
            )
        if self.agent_registry.get("scaling-controller") is None:
            self.agent_registry.register(
                RegisteredAgent(
                    agent_id="scaling-controller",
                    role="scaling",
                    subscriptions=["scaling.plan"],
                    capabilities=["scaling", "training"],
                    handler=self._scaling_agent,
                    metadata={"managed_by": "unified_orchestrator"},
                )
            )

    def _voice_reasoning_agent(self, message: Any) -> Dict[str, Any]:
        transcript = str(message.payload.get("transcript", "")).strip()
        related = self.memory.retrieve(transcript, top_k=2) if transcript else []
        hint = related[0].prompt if related else ""
        text = transcript if not hint else f"{transcript} | context:{hint}"
        return {
            "text": text,
            "memory_hits": len(related),
            "session_id": message.payload.get("session_id", ""),
        }

    def _memory_agent(self, message: Any) -> Dict[str, Any]:
        query = str(message.payload.get("query", ""))
        namespace = message.payload.get("namespace")
        matches = self.memory.retrieve(query, namespace=namespace, top_k=int(message.payload.get("top_k", 5)))
        return {
            "matches": [
                {
                    "record_id": entry.record_id,
                    "prompt": entry.prompt,
                    "namespace": entry.namespace,
                    "tags": list(entry.tags),
                }
                for entry in matches
            ]
        }

    def _scaling_agent(self, _message: Any) -> Dict[str, Any]:
        return self.distributed_orchestrator.get_state_snapshot()

    def start_training(self, mode: TrainingMode = TrainingMode.MANUAL_CONTINUOUS) -> tuple[bool, str]:
        result = self.training_controller.start(mode)
        self._write_status()
        return result

    def stop_training(self) -> tuple[bool, str]:
        result = self.training_controller.stop()
        self._write_status()
        return result

    def run_parallel(self, tasks: Dict[str, Callable[[], Any]]) -> Dict[str, Any]:
        results: Dict[str, Any] = {}
        futures = {
            self._executor.submit(task): name
            for name, task in tasks.items()
        }
        for future in as_completed(futures):
            results[futures[future]] = future.result()
        return results

    def coordinate_training(
        self,
        training: TrainingSnapshot,
        validation: ValidationSnapshot,
        *,
        per_node_sps: Dict[str, float],
        single_node_baselines: Dict[str, float],
        node_resources: Iterable[NodeResource] = (),
        current_batch_size: Optional[int] = None,
        current_learning_rate: float = 0.001,
        latency_ms: float = 100.0,
        gpu_utilization: float = 75.0,
        memory_utilization: float = 70.0,
    ) -> UnifiedTrainingOutcome:
        for resource in node_resources:
            self.distributed_orchestrator.register_node(resource)

        parallelism = self.distributed_orchestrator.plan_parallelism()
        checkpoint = self.distributed_orchestrator.record_checkpoint(training, validation)
        rollback = self.distributed_orchestrator.register_validation(training, validation)
        scale_decision = self.distributed_orchestrator.evaluate_scaling(training, validation)

        cluster_sps = float(sum(per_node_sps.values()))
        scaling_metrics = measure_efficiency(
            epoch=training.epoch,
            cluster_sps=cluster_sps,
            per_node_sps=per_node_sps,
            single_node_baselines=single_node_baselines,
        )
        should_disable, disable_reason = should_disable_node(scaling_metrics)
        if not should_disable:
            disable_reason = ""

        batch_size = current_batch_size or parallelism.global_batch_size
        tuning = self.performance.analyze(
            ComputeSnapshot(
                batch_size=batch_size,
                learning_rate=current_learning_rate,
                gpu_utilization=gpu_utilization,
                memory_utilization=memory_utilization,
                latency_ms=latency_ms,
                cluster_sps=cluster_sps,
                scaling_efficiency=scaling_metrics.efficiency,
                gradient_accumulation=parallelism.gradient_accumulation,
                zero_stage=parallelism.zero_stage,
            )
        )

        self.monitor.record_throughput(
            step=training.step,
            epoch=training.epoch,
            samples_per_second=cluster_sps,
            batch_size=batch_size,
        )
        self.monitor.record_gpu()

        storage_record: Dict[str, Any] = {}
        if checkpoint is not None:
            manifest = {
                "checkpoint_id": checkpoint.checkpoint_id,
                "epoch": checkpoint.epoch,
                "step": checkpoint.step,
                "accuracy": checkpoint.accuracy,
                "loss": checkpoint.loss,
                "version_tag": checkpoint.version_tag,
                "parallelism": asdict(parallelism),
                "tuning": asdict(tuning),
            }
            delta = self.storage.store_checkpoint_manifest(
                checkpoint.checkpoint_id,
                manifest,
                parent_manifest=self._latest_checkpoint_manifest,
                parent_checkpoint_id=self._latest_checkpoint_manifest.get("checkpoint_id", ""),
            )
            self._latest_checkpoint_manifest = manifest
            storage_record = asdict(delta)

        if scale_decision.should_scale:
            self.distributed_orchestrator.apply_scale(scale_decision)

        outcome = UnifiedTrainingOutcome(
            parallelism_plan=asdict(parallelism),
            checkpoint_id=checkpoint.checkpoint_id if checkpoint else "",
            rollback_action=asdict(rollback) if rollback else {},
            scale_decision=asdict(scale_decision),
            tuning=asdict(tuning),
            scaling_efficiency=scaling_metrics.efficiency,
            disable_node_reason=disable_reason,
            storage_record=storage_record,
        )
        self.memory.remember(
            "training",
            f"epoch:{training.epoch}:step:{training.step}",
            prompt="training coordination snapshot",
            response=asdict(outcome),
            tags=("training", self.distributed_orchestrator.current_stage.version_tag),
            metrics={
                "accuracy": validation.accuracy,
                "loss": training.loss,
                "scaling_efficiency": scaling_metrics.efficiency,
            },
        )
        self._write_status(last_training=asdict(outcome))
        return outcome

    def run_accuracy_loop(
        self,
        predictions: Iterable[Dict[str, Any]],
    ) -> UnifiedAccuracyOutcome:
        result = self.accuracy_engine.run(predictions)
        memory_records: List[str] = []
        for finding in result.findings:
            entry = self.memory.remember(
                "accuracy",
                finding.finding_id,
                prompt=finding.title,
                response={
                    "category": finding.category,
                    "payload": finding.payload,
                    "verification": finding.verification,
                    "confidence": finding.confidence,
                    "proof": finding.proof,
                    "duplicate": finding.duplicate,
                    "reasoning": finding.reasoning,
                    "retraining_signal": finding.retraining_signal,
                },
                tags=finding.memory_tags,
                references=(finding.fingerprint,),
                metrics={
                    "confidence": float(finding.confidence.get("calibrated_confidence", 0.0)),
                },
            )
            memory_records.append(entry.record_id)

        outcome = UnifiedAccuracyOutcome(
            findings=len(result.findings),
            retraining_queue=result.retraining_queue,
            duplicates=result.duplicates,
            memory_records=memory_records,
        )
        self._write_status(last_accuracy=asdict(outcome))
        return outcome

    def process_voice_chunk(
        self,
        session_id: str,
        chunk: bytes,
        *,
        recipient: str = "voice-stream",
    ) -> List[Dict[str, Any]]:
        session = self._voice_sessions.setdefault(
            session_id,
            StreamingVoiceSession(session_id=session_id),
        )
        events = self.voice_pipeline.stream_roundtrip(session, chunk, recipient=recipient)
        transcript = events[0].payload.get("text", "")
        reply = events[1].payload.get("text", "")
        self.memory.remember(
            "voice",
            session_id,
            prompt=str(transcript),
            response={
                "reply": reply,
                "events": [
                    {"event_type": event.event_type, "payload": event.payload}
                    for event in events
                ],
            },
            tags=("voice", recipient),
        )
        rendered = [
            {"event_type": event.event_type, "payload": event.payload}
            for event in events
        ]
        self._write_status(last_voice={"session_id": session_id, "events": rendered})
        return rendered

    def get_system_status(self) -> Dict[str, Any]:
        training_status = self.training_controller.get_status()
        return {
            "updated_at": datetime.now(UTC).isoformat(),
            "training_controller": {
                "mode": training_status.mode.value,
                "is_running": training_status.is_running,
                "current_epoch": training_status.current_epoch,
                "total_epochs": training_status.total_epochs,
                "last_checkpoint": training_status.last_checkpoint,
                "started_at": training_status.started_at,
                "stopped_at": training_status.stopped_at,
            },
            "distributed": self.distributed_orchestrator.get_state_snapshot(),
            "memory": self.memory.stats(),
            "storage": self.storage.get_status(),
            "performance": self.performance.latest(),
            "agents": [
                {
                    "agent_id": agent.agent_id,
                    "role": agent.role,
                    "capabilities": list(agent.capabilities),
                }
                for agent in self.agent_registry.list_agents()
            ],
            "voice_sessions": len(self._voice_sessions),
        }

    def _write_status(self, **extra: Any) -> None:
        payload = {
            **self.get_system_status(),
            **extra,
        }
        os.makedirs(os.path.dirname(self.state_path) or ".", exist_ok=True)
        tmp = f"{self.state_path}.tmp"
        with open(tmp, "w", encoding="utf-8") as handle:
            json.dump(self._normalize(payload), handle, indent=2)
            handle.write("\n")
        os.replace(tmp, self.state_path)

    def close(self) -> None:
        self._executor.shutdown(wait=True)

    def _normalize(self, value: Any) -> Any:
        if isinstance(value, bytes):
            return {"__bytes__": True, "size": len(value)}
        if isinstance(value, dict):
            return {str(key): self._normalize(item) for key, item in value.items()}
        if isinstance(value, list):
            return [self._normalize(item) for item in value]
        if isinstance(value, tuple):
            return [self._normalize(item) for item in value]
        return value
