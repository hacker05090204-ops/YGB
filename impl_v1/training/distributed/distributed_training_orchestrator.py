"""
Distributed training orchestrator control plane.

This module coordinates:
- multi-agent registry and ranking
- checkpoint trigger decisions and pointer management
- resource-aware parallelism planning
- validation rollback decisions
- scale-up planning from 3B -> 30B -> 70B -> 150B+

It intentionally acts as a control plane. Real tensor serialization and
distributed execution remain delegated to the existing training stack.
"""

from __future__ import annotations

import json
import logging
import math
import os
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

DEFAULT_STATE_PATH = os.path.join(
    "secure_data",
    "distributed_orchestrator_state.json",
)
DEFAULT_CHECKPOINT_DIR = os.path.join(
    "secure_data",
    "distributed_checkpoints",
)

DEFAULT_AGENT_ROLES = [
    "reasoning",
    "code",
    "planning",
    "memory",
    "security",
    "retrieval",
    "evaluation",
    "governance",
]


@dataclass(frozen=True)
class ScaleStage:
    version_tag: str
    total_params: int
    agent_count: int
    default_precision: str


DEFAULT_SCALE_STAGES = [
    ScaleStage("v1_base_3B", 3_000_000_000, 23, "fp32"),
    ScaleStage("v2_scaled_30B", 30_000_000_000, 48, "bf16"),
    ScaleStage("v3_scaled_70B", 70_000_000_000, 72, "bf16"),
    ScaleStage("v4_scaled_150B", 150_000_000_000, 96, "int8"),
]


@dataclass
class CheckpointPolicy:
    step_interval: int = 1_000
    time_interval_sec: int = 1_800
    loss_improvement_delta: float = 0.01
    validation_gain_delta: float = 0.005
    max_history: int = 256


@dataclass
class ValidationPolicy:
    rollback_accuracy_drop: float = 0.03
    rollback_loss_increase: float = 0.10
    max_overfit_gap: float = 0.12
    plateau_patience: int = 3
    scale_accuracy_threshold: float = 0.90


@dataclass
class ResourcePolicy:
    target_effective_batch: int = 2_048
    min_bandwidth_for_full_dp_gbps: float = 25.0
    vram_per_10b_params_gb: float = 8.0


@dataclass
class AgentRecord:
    agent_id: str
    role: str
    parameter_count: int
    precision: str
    task_success_rate: float = 0.0
    benchmark_score: float = 0.0
    validation_gain: float = 0.0
    last_loss: float = 1.0
    health: str = "healthy"
    rank_score: float = 0.0
    last_sync_step: int = 0


@dataclass
class NodeResource:
    node_id: str
    gpu_count: int
    total_vram_gb: float
    available_vram_gb: float
    gpu_utilization: float
    disk_io_mb_s: float
    network_gbps: float
    healthy: bool = True
    supports_fp16: bool = True
    supports_bf16: bool = False


@dataclass
class TrainingSnapshot:
    epoch: int
    step: int
    loss: float
    val_loss: float
    accuracy: float
    benchmark_score: float
    dataset_size: int
    elapsed_sec: float
    config_hash: str
    plateau_count: int = 0


@dataclass
class ValidationSnapshot:
    loss: float
    accuracy: float
    benchmark_score: float
    overfit_gap: float = 0.0
    regression_detected: bool = False
    task_metrics: Dict[str, float] = field(default_factory=dict)


@dataclass
class ParallelismPlan:
    data_parallel: int
    model_parallel: int
    pipeline_parallel: int
    gradient_accumulation: int
    global_batch_size: int
    micro_batch_size: int
    precision: str
    zero_stage: int
    healthy_gpus: int


@dataclass
class CheckpointDecision:
    should_checkpoint: bool
    checkpoint_kind: str
    reasons: List[str]
    is_best: bool


@dataclass
class CheckpointRecord:
    checkpoint_id: str
    version_tag: str
    checkpoint_kind: str
    epoch: int
    step: int
    loss: float
    accuracy: float
    benchmark_score: float
    config_hash: str
    created_at: str
    manifest_path: str
    weights_format: str = "safetensors"
    sharded: bool = False
    includes_optimizer_state: bool = True
    includes_scheduler_state: bool = True
    includes_rng_state: bool = True
    includes_metadata: bool = True
    sync_targets: List[str] = field(default_factory=list)
    is_latest: bool = True
    is_best: bool = False


@dataclass
class ScaleDecision:
    should_scale: bool
    reasons: List[str]
    source_version: str
    target_version: str = ""
    target_total_params: int = 0
    target_agent_count: int = 0
    target_precision: str = ""
    freeze_checkpoint_id: str = ""
    warm_start: bool = False
    learning_rate_scale: float = 1.0
    expansion_strategy: str = ""


@dataclass
class RecoveryAction:
    action: str
    checkpoint_id: str
    notes: str
    redistributed_nodes: List[str] = field(default_factory=list)
    parallelism: Optional[Dict[str, Any]] = None


@dataclass
class KnowledgeSharingPlan:
    distillation_pairs: List[Dict[str, str]]
    averaging_group: List[str]
    timestamp: str


@dataclass
class DecisionEvent:
    category: str
    detail: str
    timestamp: str
    payload: Dict[str, Any] = field(default_factory=dict)


class DistributedTrainingOrchestrator:
    """Persistent control plane for distributed multi-agent training."""

    def __init__(
        self,
        *,
        state_path: str = DEFAULT_STATE_PATH,
        checkpoint_dir: str = DEFAULT_CHECKPOINT_DIR,
        scale_stages: Optional[List[ScaleStage]] = None,
        checkpoint_policy: Optional[CheckpointPolicy] = None,
        validation_policy: Optional[ValidationPolicy] = None,
        resource_policy: Optional[ResourcePolicy] = None,
        agent_roles: Optional[List[str]] = None,
    ):
        self.state_path = state_path
        self.checkpoint_dir = checkpoint_dir
        self.scale_stages = list(scale_stages or DEFAULT_SCALE_STAGES)
        self.checkpoint_policy = checkpoint_policy or CheckpointPolicy()
        self.validation_policy = validation_policy or ValidationPolicy()
        self.resource_policy = resource_policy or ResourcePolicy()
        self.agent_roles = list(agent_roles or DEFAULT_AGENT_ROLES)

        self._agents: Dict[str, AgentRecord] = {}
        self._nodes: Dict[str, NodeResource] = {}
        self._checkpoints: List[CheckpointRecord] = []
        self._validation_history: List[ValidationSnapshot] = []
        self._decision_log: List[DecisionEvent] = []
        self._parallelism_plan: Optional[ParallelismPlan] = None
        self._current_stage_index = 0
        self._latest_checkpoint_id = ""
        self._best_checkpoint_id = ""
        self._best_accuracy = 0.0
        self._best_loss: Optional[float] = None
        self._last_checkpoint_step = 0
        self._last_checkpoint_at = 0.0

        if not self._load_state():
            self._bootstrap_initial_state()

    @property
    def current_stage(self) -> ScaleStage:
        return self.scale_stages[self._current_stage_index]

    @property
    def latest_checkpoint_id(self) -> str:
        return self._latest_checkpoint_id

    @property
    def best_checkpoint_id(self) -> str:
        return self._best_checkpoint_id

    def _bootstrap_initial_state(self) -> None:
        stage = self.current_stage
        param_per_agent = stage.total_params // stage.agent_count
        for idx in range(stage.agent_count):
            role = self.agent_roles[idx % len(self.agent_roles)]
            agent = AgentRecord(
                agent_id=f"agent_{idx + 1:02d}",
                role=role,
                parameter_count=param_per_agent,
                precision=stage.default_precision,
            )
            self._agents[agent.agent_id] = agent
        self._log_event(
            "bootstrap",
            f"Initialized {stage.agent_count} agents for {stage.version_tag}",
            {
                "version_tag": stage.version_tag,
                "total_params": stage.total_params,
                "agent_count": stage.agent_count,
            },
        )
        self._persist_state()

    def _load_state(self) -> bool:
        if not os.path.exists(self.state_path):
            return False
        try:
            with open(self.state_path, "r", encoding="utf-8") as handle:
                payload = json.load(handle)
        except (OSError, json.JSONDecodeError):
            return False

        try:
            self._current_stage_index = int(payload.get("current_stage_index", 0))
            self._latest_checkpoint_id = str(payload.get("latest_checkpoint_id", ""))
            self._best_checkpoint_id = str(payload.get("best_checkpoint_id", ""))
            self._best_accuracy = float(payload.get("best_accuracy", 0.0))
            best_loss = payload.get("best_loss")
            self._best_loss = None if best_loss is None else float(best_loss)
            self._last_checkpoint_step = int(payload.get("last_checkpoint_step", 0))
            self._last_checkpoint_at = float(payload.get("last_checkpoint_at", 0.0))
            self._agents = {
                item["agent_id"]: AgentRecord(**item)
                for item in payload.get("agents", [])
            }
            self._nodes = {
                item["node_id"]: NodeResource(**item)
                for item in payload.get("nodes", [])
            }
            self._checkpoints = [
                CheckpointRecord(**item)
                for item in payload.get("checkpoints", [])
            ]
            self._validation_history = [
                ValidationSnapshot(**item)
                for item in payload.get("validation_history", [])
            ]
            self._decision_log = [
                DecisionEvent(**item)
                for item in payload.get("decision_log", [])
            ]
            parallelism_payload = payload.get("parallelism_plan")
            if parallelism_payload:
                self._parallelism_plan = ParallelismPlan(**parallelism_payload)
        except (KeyError, TypeError, ValueError):
            return False
        return True

    def _persist_state(self) -> None:
        os.makedirs(os.path.dirname(self.state_path) or ".", exist_ok=True)
        payload = {
            "current_stage_index": self._current_stage_index,
            "latest_checkpoint_id": self._latest_checkpoint_id,
            "best_checkpoint_id": self._best_checkpoint_id,
            "best_accuracy": self._best_accuracy,
            "best_loss": self._best_loss,
            "last_checkpoint_step": self._last_checkpoint_step,
            "last_checkpoint_at": self._last_checkpoint_at,
            "agents": [asdict(agent) for agent in self._agents.values()],
            "nodes": [asdict(node) for node in self._nodes.values()],
            "checkpoints": [asdict(record) for record in self._checkpoints],
            "validation_history": [
                asdict(item) for item in self._validation_history[-128:]
            ],
            "decision_log": [asdict(item) for item in self._decision_log[-512:]],
            "parallelism_plan": (
                asdict(self._parallelism_plan) if self._parallelism_plan else None
            ),
        }
        tmp_path = f"{self.state_path}.tmp"
        with open(tmp_path, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_path, self.state_path)

    def _log_event(
        self,
        category: str,
        detail: str,
        payload: Optional[Dict[str, Any]] = None,
    ) -> None:
        event = DecisionEvent(
            category=category,
            detail=detail,
            timestamp=datetime.now().isoformat(),
            payload=payload or {},
        )
        self._decision_log.append(event)
        logger.info("[ORCH] %s: %s", category.upper(), detail)

    def get_agent_registry(self) -> List[AgentRecord]:
        return sorted(
            self._agents.values(),
            key=lambda item: (-item.rank_score, item.agent_id),
        )

    def update_agent_metrics(
        self,
        agent_id: str,
        *,
        task_success_rate: float,
        benchmark_score: float,
        validation_gain: float,
        last_loss: float,
        last_sync_step: int = 0,
    ) -> AgentRecord:
        agent = self._agents[agent_id]
        agent.task_success_rate = max(0.0, min(1.0, task_success_rate))
        agent.benchmark_score = max(0.0, min(1.0, benchmark_score))
        agent.validation_gain = max(-1.0, min(1.0, validation_gain))
        agent.last_loss = max(0.0, last_loss)
        agent.last_sync_step = max(agent.last_sync_step, last_sync_step)
        agent.rank_score = round(
            (agent.task_success_rate * 0.35)
            + (agent.benchmark_score * 0.45)
            + (max(0.0, 1.0 - agent.last_loss) * 0.15)
            + (max(0.0, agent.validation_gain) * 0.05),
            6,
        )
        self._persist_state()
        return agent

    def build_knowledge_sharing_plan(self) -> KnowledgeSharingPlan:
        ranked = self.get_agent_registry()
        if not ranked:
            return KnowledgeSharingPlan([], [], datetime.now().isoformat())

        half = max(1, len(ranked) // 2)
        top = ranked[:half]
        bottom = list(reversed(ranked[half:]))
        pairs = []
        for teacher, student in zip(top, bottom):
            pairs.append(
                {
                    "teacher": teacher.agent_id,
                    "student": student.agent_id,
                    "teacher_role": teacher.role,
                    "student_role": student.role,
                }
            )
        averaging_group = [agent.agent_id for agent in ranked[: min(4, len(ranked))]]
        plan = KnowledgeSharingPlan(
            distillation_pairs=pairs,
            averaging_group=averaging_group,
            timestamp=datetime.now().isoformat(),
        )
        self._log_event(
            "knowledge_sync",
            f"Prepared {len(pairs)} distillation pairs",
            {
                "averaging_group": averaging_group,
            },
        )
        self._persist_state()
        return plan

    def register_node(self, resource: NodeResource) -> None:
        self._nodes[resource.node_id] = resource
        self._log_event(
            "node_register",
            f"Registered node {resource.node_id}",
            {
                "gpu_count": resource.gpu_count,
                "available_vram_gb": resource.available_vram_gb,
                "network_gbps": resource.network_gbps,
                "healthy": resource.healthy,
            },
        )
        self._persist_state()

    def plan_parallelism(self) -> ParallelismPlan:
        healthy_nodes = [node for node in self._nodes.values() if node.healthy]
        healthy_gpus = sum(node.gpu_count for node in healthy_nodes)
        total_vram = sum(node.available_vram_gb for node in healthy_nodes)
        min_bandwidth = min(
            (node.network_gbps for node in healthy_nodes),
            default=0.0,
        )
        supports_bf16 = healthy_nodes and all(
            node.supports_bf16 for node in healthy_nodes
        )
        supports_fp16 = healthy_nodes and all(
            node.supports_fp16 for node in healthy_nodes
        )

        if healthy_gpus <= 0:
            plan = ParallelismPlan(
                data_parallel=1,
                model_parallel=1,
                pipeline_parallel=1,
                gradient_accumulation=self.resource_policy.target_effective_batch,
                global_batch_size=1,
                micro_batch_size=1,
                precision="fp32",
                zero_stage=0,
                healthy_gpus=0,
            )
            self._parallelism_plan = plan
            self._persist_state()
            return plan

        avg_vram = total_vram / healthy_gpus
        if self.current_stage.default_precision == "int8":
            precision = "int8"
        elif supports_bf16:
            precision = "bf16"
        elif supports_fp16:
            precision = "fp16"
        else:
            precision = "fp32"

        if avg_vram >= 80:
            micro_batch = 8
        elif avg_vram >= 40:
            micro_batch = 4
        elif avg_vram >= 20:
            micro_batch = 2
        else:
            micro_batch = 1

        if min_bandwidth >= self.resource_policy.min_bandwidth_for_full_dp_gbps:
            data_parallel = min(healthy_gpus, 8)
        elif healthy_gpus >= 4:
            data_parallel = 2
        else:
            data_parallel = 1

        stage_scale = max(
            1,
            math.ceil(self.current_stage.total_params / 30_000_000_000),
        )
        remaining_parallel = max(1, healthy_gpus // data_parallel)
        pipeline_parallel = min(max(1, stage_scale), remaining_parallel)
        model_parallel = max(1, remaining_parallel // pipeline_parallel)

        per_step_batch = max(1, micro_batch * data_parallel)
        gradient_accumulation = max(
            1,
            math.ceil(self.resource_policy.target_effective_batch / per_step_batch),
        )
        global_batch_size = per_step_batch * gradient_accumulation

        if healthy_gpus >= 8:
            zero_stage = 3
        elif healthy_gpus >= 4:
            zero_stage = 2
        else:
            zero_stage = 1

        plan = ParallelismPlan(
            data_parallel=data_parallel,
            model_parallel=model_parallel,
            pipeline_parallel=pipeline_parallel,
            gradient_accumulation=gradient_accumulation,
            global_batch_size=global_batch_size,
            micro_batch_size=micro_batch,
            precision=precision,
            zero_stage=zero_stage,
            healthy_gpus=healthy_gpus,
        )
        self._parallelism_plan = plan
        self._log_event(
            "parallelism",
            (
                f"DP={plan.data_parallel}, MP={plan.model_parallel}, "
                f"PP={plan.pipeline_parallel}, precision={plan.precision}"
            ),
            asdict(plan),
        )
        self._persist_state()
        return plan

    def evaluate_checkpoint_need(
        self,
        training: TrainingSnapshot,
        validation: ValidationSnapshot,
        *,
        now: Optional[float] = None,
    ) -> CheckpointDecision:
        now_ts = time.time() if now is None else float(now)
        reasons: List[str] = []

        if not self._checkpoints:
            reasons.append("bootstrap")
        if training.step - self._last_checkpoint_step >= self.checkpoint_policy.step_interval:
            reasons.append("step_interval")
        if (
            self._last_checkpoint_at <= 0.0
            or now_ts - self._last_checkpoint_at >= self.checkpoint_policy.time_interval_sec
        ):
            reasons.append("time_interval")
        if self._best_loss is None or (
            self._best_loss - training.loss >= self.checkpoint_policy.loss_improvement_delta
        ):
            reasons.append("loss_improvement")
        if (
            validation.accuracy - self._best_accuracy
            >= self.checkpoint_policy.validation_gain_delta
        ):
            reasons.append("validation_gain")

        is_best = (
            validation.accuracy >= self._best_accuracy
            and (
                validation.accuracy > self._best_accuracy
                or self._best_checkpoint_id == ""
            )
        )
        if "bootstrap" in reasons or "time_interval" in reasons:
            kind = "full"
        else:
            kind = "delta"

        return CheckpointDecision(
            should_checkpoint=bool(reasons),
            checkpoint_kind=kind,
            reasons=reasons,
            is_best=is_best,
        )

    def record_checkpoint(
        self,
        training: TrainingSnapshot,
        validation: ValidationSnapshot,
        *,
        now: Optional[float] = None,
        sync_targets: Optional[List[str]] = None,
    ) -> Optional[CheckpointRecord]:
        decision = self.evaluate_checkpoint_need(training, validation, now=now)
        if not decision.should_checkpoint:
            return None

        version_dir = os.path.join(self.checkpoint_dir, self.current_stage.version_tag)
        checkpoint_id = (
            f"{self.current_stage.version_tag}_e{training.epoch:04d}"
            f"_s{training.step:08d}_{decision.checkpoint_kind}"
        )
        checkpoint_path = os.path.join(version_dir, checkpoint_id)
        manifest_path = os.path.join(checkpoint_path, "manifest.json")
        os.makedirs(checkpoint_path, exist_ok=True)

        sharded = self.current_stage.total_params >= 30_000_000_000
        record = CheckpointRecord(
            checkpoint_id=checkpoint_id,
            version_tag=self.current_stage.version_tag,
            checkpoint_kind=decision.checkpoint_kind,
            epoch=training.epoch,
            step=training.step,
            loss=training.loss,
            accuracy=validation.accuracy,
            benchmark_score=validation.benchmark_score,
            config_hash=training.config_hash,
            created_at=datetime.now().isoformat(),
            manifest_path=manifest_path,
            sharded=sharded,
            sync_targets=list(
                sync_targets or ["local_nvme", "remote_object_store", "peer_node"]
            ),
            is_latest=True,
            is_best=decision.is_best,
        )

        manifest = {
            "checkpoint_id": record.checkpoint_id,
            "checkpoint_kind": record.checkpoint_kind,
            "version_tag": record.version_tag,
            "artifacts": {
                "model_weights": {"format": "safetensors", "sharded": sharded},
                "optimizer_state": {"included": True, "sharded": sharded},
                "scheduler_state": {"included": True},
                "rng_state": {"included": True},
                "training_metadata": {
                    "epoch": training.epoch,
                    "step": training.step,
                    "loss": training.loss,
                    "accuracy": validation.accuracy,
                    "config_hash": training.config_hash,
                },
            },
            "reasons": decision.reasons,
            "sync_targets": record.sync_targets,
        }
        self._atomic_write_json(manifest_path, manifest)

        self._latest_checkpoint_id = record.checkpoint_id
        self._last_checkpoint_step = training.step
        self._last_checkpoint_at = time.time() if now is None else float(now)
        self._best_loss = (
            training.loss
            if self._best_loss is None
            else min(self._best_loss, training.loss)
        )
        if decision.is_best:
            self._best_accuracy = validation.accuracy
            self._best_checkpoint_id = record.checkpoint_id

        self._checkpoints.append(record)
        self._checkpoints = self._checkpoints[-self.checkpoint_policy.max_history :]
        self._write_checkpoint_pointers()
        self._log_event(
            "checkpoint",
            f"Recorded {record.checkpoint_kind} checkpoint {record.checkpoint_id}",
            {
                "reasons": decision.reasons,
                "is_best": decision.is_best,
                "sync_targets": record.sync_targets,
            },
        )
        self._persist_state()
        return record

    def _write_checkpoint_pointers(self) -> None:
        pointers_path = os.path.join(self.checkpoint_dir, "pointers.json")
        self._atomic_write_json(
            pointers_path,
            {
                "latest_checkpoint_id": self._latest_checkpoint_id,
                "best_checkpoint_id": self._best_checkpoint_id,
                "updated_at": datetime.now().isoformat(),
            },
        )

    def register_validation(
        self,
        training: TrainingSnapshot,
        validation: ValidationSnapshot,
    ) -> Optional[RecoveryAction]:
        self._validation_history.append(validation)

        accuracy_drop = max(0.0, self._best_accuracy - validation.accuracy)
        loss_increase = 0.0
        if self._best_loss is not None:
            loss_increase = max(0.0, validation.loss - self._best_loss)

        should_rollback = (
            validation.regression_detected
            or accuracy_drop >= self.validation_policy.rollback_accuracy_drop
            or loss_increase >= self.validation_policy.rollback_loss_increase
            or validation.overfit_gap >= self.validation_policy.max_overfit_gap
        )

        self._persist_state()
        if not should_rollback or not self._best_checkpoint_id:
            return None

        notes = (
            "Validation degradation detected. Roll back to best checkpoint "
            "and reduce effective batch pressure."
        )
        action = RecoveryAction(
            action="rollback_to_best",
            checkpoint_id=self._best_checkpoint_id,
            notes=notes,
            redistributed_nodes=[
                node.node_id for node in self._nodes.values() if node.healthy
            ],
            parallelism=(asdict(self.plan_parallelism()) if self._nodes else None),
        )
        self._log_event(
            "rollback",
            notes,
            {
                "checkpoint_id": self._best_checkpoint_id,
                "accuracy_drop": accuracy_drop,
                "loss_increase": loss_increase,
                "overfit_gap": validation.overfit_gap,
            },
        )
        self._persist_state()
        return action

    def evaluate_scaling(
        self,
        training: TrainingSnapshot,
        validation: ValidationSnapshot,
    ) -> ScaleDecision:
        source_stage = self.current_stage
        if self._current_stage_index >= len(self.scale_stages) - 1:
            return ScaleDecision(
                should_scale=False,
                reasons=["already_at_max_stage"],
                source_version=source_stage.version_tag,
            )

        next_stage = self.scale_stages[self._current_stage_index + 1]
        reasons: List[str] = []

        if training.plateau_count >= self.validation_policy.plateau_patience:
            reasons.append("loss_plateau")
        if training.dataset_size >= source_stage.total_params // 10:
            reasons.append("dataset_growth")
        if validation.accuracy >= self.validation_policy.scale_accuracy_threshold:
            reasons.append("performance_threshold")

        healthy_gpus = sum(
            node.gpu_count for node in self._nodes.values() if node.healthy
        )
        total_vram = sum(
            node.available_vram_gb for node in self._nodes.values() if node.healthy
        )
        required_vram = (
            next_stage.total_params / 10_000_000_000
        ) * self.resource_policy.vram_per_10b_params_gb
        if healthy_gpus > 0 and total_vram >= required_vram:
            reasons.append("compute_available")

        compute_ready = "compute_available" in reasons
        trigger_ready = any(
            reason in reasons
            for reason in ("loss_plateau", "dataset_growth", "performance_threshold")
        )
        if not (compute_ready and trigger_ready):
            return ScaleDecision(
                should_scale=False,
                reasons=reasons or ["conditions_not_met"],
                source_version=source_stage.version_tag,
            )

        freeze_checkpoint_id = self._best_checkpoint_id or self._latest_checkpoint_id
        lr_scale = round(
            math.sqrt(source_stage.total_params / next_stage.total_params),
            6,
        )
        return ScaleDecision(
            should_scale=True,
            reasons=reasons,
            source_version=source_stage.version_tag,
            target_version=next_stage.version_tag,
            target_total_params=next_stage.total_params,
            target_agent_count=next_stage.agent_count,
            target_precision=next_stage.default_precision,
            freeze_checkpoint_id=freeze_checkpoint_id,
            warm_start=True,
            learning_rate_scale=lr_scale,
            expansion_strategy="layer_expansion+weight_interpolation+partial_reuse",
        )

    def apply_scale(self, decision: ScaleDecision) -> None:
        if not decision.should_scale:
            return

        target_index = next(
            idx
            for idx, stage in enumerate(self.scale_stages)
            if stage.version_tag == decision.target_version
        )
        self._current_stage_index = target_index
        stage = self.current_stage
        param_per_agent = stage.total_params // stage.agent_count

        ranked_agents = self.get_agent_registry()
        retained = ranked_agents[: min(len(ranked_agents), stage.agent_count)]
        rebuilt: Dict[str, AgentRecord] = {}
        for idx in range(stage.agent_count):
            if idx < len(retained):
                agent = retained[idx]
                agent.parameter_count = param_per_agent
                agent.precision = stage.default_precision
            else:
                role = self.agent_roles[idx % len(self.agent_roles)]
                agent = AgentRecord(
                    agent_id=f"agent_{idx + 1:02d}",
                    role=role,
                    parameter_count=param_per_agent,
                    precision=stage.default_precision,
                )
            rebuilt[agent.agent_id] = agent
        self._agents = rebuilt
        self._log_event(
            "scale",
            (
                f"Scaled {decision.source_version} -> {decision.target_version} "
                f"using {decision.expansion_strategy}"
            ),
            {
                "freeze_checkpoint_id": decision.freeze_checkpoint_id,
                "learning_rate_scale": decision.learning_rate_scale,
                "agent_count": stage.agent_count,
            },
        )
        self._persist_state()

    def handle_node_failure(self, node_id: str) -> RecoveryAction:
        if node_id in self._nodes:
            self._nodes[node_id].healthy = False
        healthy_nodes = [node.node_id for node in self._nodes.values() if node.healthy]
        parallelism = asdict(self.plan_parallelism()) if self._nodes else None
        checkpoint_id = self._latest_checkpoint_id or self._best_checkpoint_id
        action_name = "resume_from_latest" if checkpoint_id else "pause_training"
        notes = (
            f"Node failure detected for {node_id}. Redistribute workload across "
            f"{len(healthy_nodes)} healthy nodes."
        )
        action = RecoveryAction(
            action=action_name,
            checkpoint_id=checkpoint_id,
            notes=notes,
            redistributed_nodes=healthy_nodes,
            parallelism=parallelism,
        )
        self._log_event(
            "node_failure",
            notes,
            {
                "failed_node": node_id,
                "checkpoint_id": checkpoint_id,
                "healthy_nodes": healthy_nodes,
            },
        )
        self._persist_state()
        return action

    def get_state_snapshot(self) -> Dict[str, Any]:
        return {
            "version_tag": self.current_stage.version_tag,
            "latest_checkpoint_id": self._latest_checkpoint_id,
            "best_checkpoint_id": self._best_checkpoint_id,
            "agent_count": len(self._agents),
            "healthy_nodes": len(
                [node for node in self._nodes.values() if node.healthy]
            ),
            "parallelism_plan": (
                asdict(self._parallelism_plan) if self._parallelism_plan else None
            ),
            "decision_events": len(self._decision_log),
        }

    @staticmethod
    def _atomic_write_json(path: str, payload: Dict[str, Any]) -> None:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        tmp_path = f"{path}.tmp"
        with open(tmp_path, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_path, path)
