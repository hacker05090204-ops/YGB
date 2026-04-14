import time

from impl_v1.agents import AgentOrchestrator, AgentRegistry, RegisteredAgent
from impl_v1.training.distributed.distributed_training_orchestrator import (
    DistributedTrainingOrchestrator,
    NodeResource,
    TrainingSnapshot,
    ValidationSnapshot,
)
from impl_v1.unified.memory import UnifiedMemoryStore
from impl_v1.unified.performance import ComputeSnapshot, PerformanceIntelligence
from impl_v1.unified.storage import TieredCheckpointStorageEngine


class _FakeStorage:
    def __init__(self):
        self.backend_name = "fake-remote"
        self._writes = {}

    def write(self, path, data):
        self._writes[path] = data
        return True


def test_unified_memory_retrieves_by_history(tmp_path):
    store = UnifiedMemoryStore(str(tmp_path / "memory.json"))
    first = store.remember(
        "accuracy",
        "finding-1",
        prompt="Reflected XSS on search endpoint",
        response={"status": "verified"},
        tags=("xss", "verified"),
    )
    store.remember(
        "voice",
        "session-1",
        prompt="What is the cluster status",
        response={"reply": "healthy"},
        tags=("voice",),
    )

    matches = store.retrieve("reflected xss search", namespace="accuracy", top_k=1)
    assert matches[0].record_id == first.record_id

    updated = store.reinforce(first.record_id, 0.5)
    assert updated is not None
    assert updated.feedback_score == 0.5


def test_tiered_storage_deduplicates_and_builds_delta(tmp_path, monkeypatch):
    fake_storage = _FakeStorage()
    monkeypatch.setattr("impl_v1.unified.storage.get_storage", lambda: fake_storage)

    engine = TieredCheckpointStorageEngine(str(tmp_path / "tiered"))
    blob_a = engine.store_blob("weights.bin", b"same-bytes", mirror_remote=True)
    blob_b = engine.store_blob("weights-copy.bin", b"same-bytes", mirror_remote=True)

    assert blob_b.deduplicated is True
    assert blob_a.sha256 == blob_b.sha256

    parent = engine.store_checkpoint_manifest(
        "ckpt-1",
        {"checkpoint_id": "ckpt-1", "epoch": 1, "loss": 0.3},
        mirror_remote=True,
    )
    child = engine.store_checkpoint_manifest(
        "ckpt-2",
        {"checkpoint_id": "ckpt-2", "epoch": 2, "loss": 0.2, "accuracy": 0.91},
        parent_manifest={"checkpoint_id": "ckpt-1", "epoch": 1, "loss": 0.3},
        parent_checkpoint_id="ckpt-1",
        mirror_remote=True,
    )

    assert set(child.changed_keys) == {"accuracy", "checkpoint_id", "epoch", "loss"}
    hydrated = engine.hydrate_checkpoint("ckpt-2")
    assert hydrated["accuracy"] == 0.91
    assert hydrated["loss"] == 0.2
    assert parent.mirrored is True


def test_performance_intelligence_tunes_batch_and_lr():
    intelligence = PerformanceIntelligence()
    decision = intelligence.analyze(
        ComputeSnapshot(
            batch_size=64,
            learning_rate=0.001,
            gpu_utilization=55.0,
            memory_utilization=45.0,
            latency_ms=120.0,
            cluster_sps=6400.0,
            scaling_efficiency=0.94,
            gradient_accumulation=2,
            zero_stage=1,
        )
    )

    assert decision.batch_size > 64
    assert decision.learning_rate > 0.001
    assert decision.compute_efficiency > 0.0


def test_agent_orchestrator_routes_by_capability_and_parallel():
    registry = AgentRegistry()
    registry.register(
        RegisteredAgent(
            agent_id="planner",
            role="planning",
            capabilities=["reasoning"],
            subscriptions=["plan"],
            handler=lambda message: {"agent": "planner", "topic": message.topic},
        )
    )
    registry.register(
        RegisteredAgent(
            agent_id="worker-a",
            role="worker",
            capabilities=["execution"],
            subscriptions=["run"],
            handler=lambda message: {"agent": "worker-a", "value": message.payload["value"]},
        )
    )
    registry.register(
        RegisteredAgent(
            agent_id="worker-b",
            role="worker",
            capabilities=["execution"],
            subscriptions=["run"],
            handler=lambda message: {"agent": "worker-b", "value": message.payload["value"]},
        )
    )

    orchestrator = AgentOrchestrator(registry)
    routed = orchestrator.route_by_capability("system", "reasoning", "plan", {"value": 1})
    parallel = orchestrator.send_parallel("system", ["worker-a", "worker-b"], "run", {"value": 7})

    assert routed["agent"] == "planner"
    assert {item["agent_id"] for item in parallel.responses} == {"worker-a", "worker-b"}


def test_unified_orchestrator_connects_training_accuracy_and_voice(tmp_path, monkeypatch):
    fake_storage = _FakeStorage()
    monkeypatch.setattr("impl_v1.unified.storage.get_storage", lambda: fake_storage)
    monkeypatch.setattr(
        "impl_v1.enterprise.training_controller.TrainingController.STATE_FILE",
        tmp_path / "training_state.json",
    )

    from impl_v1.unified.orchestrator import UnifiedAIOrchestrator

    distributed = DistributedTrainingOrchestrator(
        state_path=str(tmp_path / "distributed_state.json"),
        checkpoint_dir=str(tmp_path / "distributed_checkpoints"),
    )
    orchestrator = UnifiedAIOrchestrator(
        state_path=str(tmp_path / "unified_status.json"),
        memory_path=str(tmp_path / "memory.json"),
        storage_root=str(tmp_path / "tiered_storage"),
        training_dashboard_path=str(tmp_path / "dashboard.json"),
        distributed_orchestrator=distributed,
        agent_registry=AgentRegistry(),
    )

    training = TrainingSnapshot(
        epoch=1,
        step=1000,
        loss=0.2,
        val_loss=0.21,
        accuracy=0.91,
        benchmark_score=0.88,
        dataset_size=400000000,
        elapsed_sec=60.0,
        config_hash="cfg-1",
        plateau_count=3,
    )
    validation = ValidationSnapshot(
        loss=0.21,
        accuracy=0.91,
        benchmark_score=0.88,
        overfit_gap=0.03,
    )
    node = NodeResource(
        node_id="node-1",
        gpu_count=1,
        total_vram_gb=24.0,
        available_vram_gb=18.0,
        gpu_utilization=72.0,
        disk_io_mb_s=1500.0,
        network_gbps=40.0,
        healthy=True,
        supports_fp16=True,
        supports_bf16=True,
    )

    training_outcome = orchestrator.coordinate_training(
        training,
        validation,
        per_node_sps={"node-1": 1200.0},
        single_node_baselines={"node-1": 1000.0},
        node_resources=[node],
        current_batch_size=64,
        current_learning_rate=0.001,
        latency_ms=140.0,
        gpu_utilization=72.0,
        memory_utilization=68.0,
    )
    accuracy_outcome = orchestrator.run_accuracy_loop(
        [
            {
                "finding_id": "f1",
                "category": "xss",
                "title": "Search XSS",
                "url": "https://target/search",
                "expected_status": 200,
            },
            {
                "finding_id": "f2",
                "category": "xss",
                "title": "Search XSS",
                "url": "https://target/search",
                "expected_status": 200,
            },
        ]
    )
    voice_events = orchestrator.process_voice_chunk("voice-1", b"hello cluster")
    follow_up_events = orchestrator.process_voice_chunk("voice-1", b"status please")
    status = orchestrator.get_system_status()
    orchestrator.close()

    assert training_outcome.parallelism_plan["healthy_gpus"] == 1
    assert accuracy_outcome.findings == 1
    assert voice_events[1]["payload"]["text"].startswith("hello cluster")
    assert follow_up_events[1]["payload"]["text"].endswith("context:hello cluster")
    assert "user: hello cluster" in follow_up_events[1]["payload"]["conversation_context"]
    assert status["memory"]["entries"] >= 3
