import json

import torch

from impl_v1.agents import AgentOrchestrator, AgentRegistry, RegisteredAgent
from impl_v1.training.accuracy.engine import AccuracyEngine
from impl_v1.training.distributed.advanced_checkpointing import AsyncDistributedCheckpointManager
from impl_v1.training.voice.streaming_pipeline import StreamingVoicePipeline, StreamingVoiceSession


def test_advanced_checkpoint_roundtrip(tmp_path):
    manager = AsyncDistributedCheckpointManager(str(tmp_path))
    model_state = {"layer.weight": torch.ones(2, 2), "layer.bias": torch.zeros(2)}
    optimizer_state = {
        "optimizer_state_dict": {
            "state": {},
            "param_groups": [{"lr": 0.001}],
        },
        "epoch": 3,
        "dataset_hash": "abc123",
        "per_epoch": [{"epoch": 1, "accuracy": 0.5}],
    }
    scheduler_state = {"last_epoch": 3}

    future = manager.save_async(
        name="latest",
        model_state=model_state,
        optimizer_state=optimizer_state,
        scheduler_state=scheduler_state,
        meta={"epoch": 3, "accuracy": 0.8},
        rank=0,
        world_size=1,
        is_latest=True,
        is_best=True,
    )
    future.result()

    loaded = manager.load_latest_valid(rank=0)
    manager.close()

    assert loaded is not None
    assert loaded.optimizer_state["dataset_hash"] == "abc123"
    assert torch.equal(loaded.model_state["layer.weight"], model_state["layer.weight"])


def test_agent_voice_and_accuracy_pipeline():
    registry = AgentRegistry()
    registry.register(
        RegisteredAgent(
            agent_id="voice-stream",
            role="voice",
            subscriptions=["voice.reasoning"],
            handler=lambda message: {"text": f"ack:{message.payload['transcript']}"},
        )
    )
    orchestrator = AgentOrchestrator(registry)
    pipeline = StreamingVoicePipeline(orchestrator)
    session = StreamingVoiceSession(session_id="s1")

    events = pipeline.stream_roundtrip(session, b"hello world")
    assert events[1].payload["text"] == "ack:hello world"

    engine = AccuracyEngine()
    result = engine.run([
        {"finding_id": "f1", "category": "xss", "title": "XSS", "url": "https://a", "expected_status": 200},
        {"finding_id": "f2", "category": "xss", "title": "XSS", "url": "https://a", "expected_status": 200},
    ])
    assert len(result.findings) == 1

    agent_manifest = json.loads(open(".agents/registry.json", "r", encoding="utf-8").read())
    assert agent_manifest["version"] == 1
