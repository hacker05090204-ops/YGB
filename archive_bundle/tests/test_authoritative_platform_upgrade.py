import asyncio

from backend.ingest.normalize.canonicalize import canonicalize_record
from backend.ingest.snapshots.publisher import SnapshotPublisher
from backend.ingest.validate.real_only import ValidationAction, validate_real_only
from backend.tasks.central_task_queue import FileBackedTaskQueue, TaskPriority, TaskState
from backend.tasks.industrial_agent import IndustrialAgentRuntime
from backend.voice.streaming_pipeline import AudioFrame, AuthoritativeVoicePipeline
from impl_v1.training.experts.expert_checkpoint_system import ExpertCheckpointRegistry


def _run(coro):
    return asyncio.run(coro)


def test_file_backed_queue_dedup_and_dead_letter(tmp_path):
    queue = FileBackedTaskQueue(str(tmp_path / "queue"))
    task_1 = _run(
        queue.enqueue(
            "ingest_url",
            {"url": "https://example.com/report/1"},
            priority=TaskPriority.HIGH,
            route="grabber",
            max_attempts=1,
        )
    )
    task_2 = _run(
        queue.enqueue(
            "ingest_url",
            {"url": "https://example.com/report/1"},
            priority=TaskPriority.HIGH,
            route="grabber",
            max_attempts=1,
        )
    )
    assert task_1.task_id == task_2.task_id

    leased = _run(queue.lease("grabber-01", ["grabber"]))
    assert leased is not None
    assert leased.task_id == task_1.task_id
    _run(queue.heartbeat(task_1.task_id, "grabber-01"))
    finished = _run(queue.finish(task_1.task_id, "grabber-01", ok=False, error="boom"))
    assert finished.state == TaskState.DEAD_LETTER.value


def test_real_only_snapshot_publish_and_duplicate_reject(tmp_path):
    publisher = SnapshotPublisher(str(tmp_path / "snapshots"), signing_key=b"test-signing-key")
    record = canonicalize_record(
        {
            "source_id": "CVE-2026-0001",
            "source_url": "https://nvd.nist.gov/vuln/detail/CVE-2026-0001",
            "source_type": "nvd",
            "source_name": "nvd",
            "content": "API IDOR vulnerability in a public endpoint",
            "provenance": {"connector": "nvd"},
        },
        source_name="nvd",
        source_type="nvd",
    )
    decision = validate_real_only(record, exact_hash_index=publisher.exact_hashes())
    assert decision.action == ValidationAction.ACCEPT.value

    snapshot = publisher.publish([record], route="trainer")
    assert publisher.verify_manifest(snapshot.manifest_path) is True

    duplicate = validate_real_only(record, exact_hash_index=publisher.exact_hashes())
    assert duplicate.action == ValidationAction.REJECT.value
    assert "duplicate_exact_hash" in duplicate.reasons


def test_expert_checkpoint_registry_tracks_lineage(tmp_path):
    registry = ExpertCheckpointRegistry(str(tmp_path / "experts"))
    first = registry.create_checkpoint(
        "idor",
        epoch=1,
        step=10,
        metrics={"loss": 0.12},
        data_manifest_hash="manifest-a",
        sample_count=100,
        model_bytes=b"model-a",
        optimizer_bytes=b"optim-a",
        router_bytes=b"router-a",
    )
    second = registry.create_checkpoint(
        "idor",
        epoch=2,
        step=20,
        metrics={"loss": 0.08},
        data_manifest_hash="manifest-b",
        sample_count=120,
        model_bytes=b"model-b",
        optimizer_bytes=b"optim-b",
        router_bytes=b"router-b",
    )
    assert second.parent_sha256 == first.content_sha256
    assert registry.latest("idor")["checkpoint_id"] == second.checkpoint_id
    assert registry.verify_lineage("idor") is True


def test_industrial_agent_processes_ingest_train_and_checkpoint(tmp_path):
    runtime = IndustrialAgentRuntime(
        root=str(tmp_path / "runtime"),
        signing_key=b"test-signing-key",
    )
    _run(
        runtime.queue.enqueue(
            "ingest_url",
            {
                "url": "https://nvd.nist.gov/vuln/detail/CVE-2026-0002",
                "content": "IDOR vulnerability allows unauthorized access",
                "source_type": "nvd",
                "source_name": "nvd",
                "immutable_source_id": "CVE-2026-0002",
            },
            priority=TaskPriority.CRITICAL,
            route="grabber",
        )
    )

    while _run(runtime.run_once()):
        pass

    latest = runtime.registry.latest("idor")
    assert latest is not None
    assert latest["data_manifest_hash"]
    assert runtime.publisher.exact_hashes()
    assert runtime.queue.list_tasks(states={TaskState.SUCCEEDED.value})


def test_authoritative_voice_pipeline_roundtrip(tmp_path):
    pipeline = AuthoritativeVoicePipeline()
    result = _run(
        pipeline.roundtrip(
            AudioFrame(
                pcm16=b"hello expert status",
                sample_rate=16000,
                language_hint="en",
            )
        )
    )
    assert result.status == "ok"
    assert result.transcript is not None
    assert result.synthesis is not None
    assert "hello expert status" in result.conversation_context
