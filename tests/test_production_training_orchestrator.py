import json

import pytest
import torch

from impl_v1.training.distributed.production_training_orchestrator import (
    AgentIsolationProfile,
    ProductionTrainingOrchestrator,
)


class _FakeStorage:
    def __init__(self):
        self.writes = {}

    def write(self, path, data):
        self.writes[path] = bytes(data)
        return True


@pytest.fixture
def fake_safetensors(monkeypatch):
    import impl_v1.training.distributed.production_training_orchestrator as orch_mod
    import training.safetensors_io as safetensors_io

    def fake_save_safetensors(tensors, path, metadata=None, convert_fp16=False):
        materialized = {
            key: value.detach().cpu().clone()
            for key, value in tensors.items()
        }
        torch.save({"tensors": materialized, "metadata": metadata or {}}, path)
        file_hash = safetensors_io._compute_file_hash(path)
        tensor_hash = safetensors_io._compute_tensor_hash(materialized)
        return file_hash, tensor_hash

    def fake_load_safetensors(path, device="cpu", verify_hash=True):
        payload = torch.load(path, map_location=device, weights_only=False)
        return payload["tensors"]

    monkeypatch.setattr(orch_mod, "save_safetensors", fake_save_safetensors)
    monkeypatch.setattr(orch_mod, "load_safetensors", fake_load_safetensors)
    return orch_mod


@pytest.fixture
def orchestrator(tmp_path, monkeypatch, fake_safetensors):
    fake_storage = _FakeStorage()
    monkeypatch.setattr(
        "impl_v1.training.distributed.production_training_orchestrator.get_storage",
        lambda: fake_storage,
    )
    orch = ProductionTrainingOrchestrator(
        secure_root=str(tmp_path / "secure_data"),
        checkpoint_step_interval=5,
        checkpoint_time_interval_sec=60,
        bootstrap_default_agents=False,
    )
    orch.register_agent(
        AgentIsolationProfile(
            agent_id="api",
            role="api",
            required_keywords=("api", "endpoint"),
            blocked_keywords=("mobile",),
        )
    )
    orch.register_agent(
        AgentIsolationProfile(
            agent_id="mobile",
            role="mobile",
            required_keywords=("mobile", "android", "ios"),
            blocked_keywords=("api",),
        )
    )
    yield orch, fake_storage
    orch.close()


def _api_sample():
    return {
        "title": "API endpoint auth bypass",
        "summary": "API endpoint leaked auth headers",
        "endpoint": "/api/v1/users",
        "parameters": "id=7",
        "source_tag": "scanner",
        "bug_type": "api",
        "tags": ["backend"],
    }


def test_dataset_validation_enforces_isolation_and_dedup(orchestrator):
    orch, _ = orchestrator
    report = orch.validate_dataset(
        "api",
        [
            _api_sample(),
            _api_sample(),
            {
                "title": "Mobile deep link issue",
                "summary": "Mobile app deep link hijack",
                "bug_type": "mobile",
                "tags": ["android"],
            },
        ],
    )

    assert report.accepted_count == 1
    assert report.deduplicated_count == 1
    assert report.rejected_count == 1

    contamination = orch.validate_dataset("mobile", [_api_sample()])
    assert contamination.accepted_count == 0
    assert contamination.contamination_rejections == 1


def test_checkpoint_save_replication_and_remote_backup(orchestrator):
    orch, fake_storage = orchestrator
    checkpoint = orch.save_checkpoint(
        "api",
        model_state={"weight": torch.ones(2, 2)},
        optimizer_state={"lr": 1e-3, "state": {}},
        scheduler_state={"step_size": 10},
        step=10,
        epoch=1,
        metrics={"validation_accuracy": 0.82, "validation_loss": 0.19},
        execution_target="vps",
        dataset_hash="dataset-a",
        force=True,
    )
    orch.wait_for_backups()

    assert checkpoint is not None
    checkpoint_dir = (
        orch.checkpoint_root / "agent_api" / checkpoint.checkpoint_id
    )
    assert (checkpoint_dir / "model.safetensors").exists()
    assert (checkpoint_dir / "optimizer.pt").exists()
    assert (checkpoint_dir / "scheduler.pt").exists()
    assert (checkpoint_dir / "metadata.json").exists()

    receipt = json.loads((checkpoint_dir / "backup_receipt.json").read_text(encoding="utf-8"))
    assert receipt["completed_locations"] >= 3
    assert (orch.secondary_backup_root / "agent_api" / checkpoint.checkpoint_id).exists()
    assert (orch.hybrid_root / "local_gpu" / "agent_api" / checkpoint.checkpoint_id).exists()
    assert fake_storage.writes


def test_resume_falls_back_to_previous_valid_checkpoint(orchestrator):
    orch, _ = orchestrator
    first = orch.save_checkpoint(
        "api",
        model_state={"weight": torch.zeros(2, 2)},
        optimizer_state={"lr": 1e-3},
        scheduler_state={"warmup": 3},
        step=10,
        epoch=1,
        metrics={"validation_accuracy": 0.81, "validation_loss": 0.21},
        execution_target="vps",
        force=True,
    )
    second = orch.save_checkpoint(
        "api",
        model_state={"weight": torch.ones(2, 2)},
        optimizer_state={"lr": 1e-4},
        scheduler_state={"warmup": 4},
        step=20,
        epoch=2,
        metrics={"validation_accuracy": 0.83, "validation_loss": 0.18},
        execution_target="vps",
        force=True,
    )
    orch.wait_for_backups()

    latest_model = orch.checkpoint_root / "agent_api" / second.checkpoint_id / "model.safetensors"
    latest_model.write_bytes(b"corrupted")

    resumed = orch.resume_latest("api", device="cpu")

    assert resumed.restored is True
    assert resumed.checkpoint_id == first.checkpoint_id
    assert resumed.step == 10


def test_feedback_loop_queues_incremental_training_on_local_gpu(orchestrator):
    orch, _ = orchestrator
    orch.set_runtime_availability(vps_available=False, local_gpu_available=True, cpu_available=True)
    sample = _api_sample()
    orch.record_prediction(
        "api",
        prediction_id="pred-1",
        sample=sample,
        prediction={"label": "safe"},
        checkpoint_id="step_10",
    )

    request = orch.record_feedback(
        "api",
        prediction_id="pred-1",
        verified_result={"label": "unsafe"},
        correction_sample=sample,
        was_correct=False,
    )

    assert request.target == "local_gpu"
    assert request.fallback_target == "cpu"
    request_path = orch.training_queue_root / "agent_api" / f"{request.request_id}.json"
    assert request_path.exists()
    assert (orch.agent_root / "agent_api" / "experience" / "feedback.jsonl").exists()


def test_training_safety_pauses_and_rolls_back(orchestrator):
    orch, _ = orchestrator
    checkpoint = orch.save_checkpoint(
        "api",
        model_state={"weight": torch.ones(2, 2)},
        optimizer_state={"lr": 1e-3},
        scheduler_state={"gamma": 0.95},
        step=15,
        epoch=1,
        metrics={"validation_accuracy": 0.90, "validation_loss": 0.12},
        execution_target="vps",
        force=True,
    )

    decision = orch.evaluate_training_safety(
        "api",
        epoch=4,
        train_loss=0.10,
        val_loss=0.55,
        accuracy=0.93,
        gradient_norm=150.0,
    )

    assert decision.pause_training is True
    assert decision.rollback_checkpoint_id == checkpoint.checkpoint_id
    assert "gradient_explosion" in decision.reasons


def test_startup_recovery_repairs_backups_and_reroutes_requests(
    tmp_path,
    monkeypatch,
    fake_safetensors,
):
    fake_storage = _FakeStorage()
    monkeypatch.setattr(
        "impl_v1.training.distributed.production_training_orchestrator.get_storage",
        lambda: fake_storage,
    )
    secure_root = tmp_path / "secure_data"
    orch = ProductionTrainingOrchestrator(
        secure_root=str(secure_root),
        checkpoint_step_interval=5,
        checkpoint_time_interval_sec=60,
        bootstrap_default_agents=False,
    )
    orch.register_agent(
        AgentIsolationProfile(
            agent_id="api",
            role="api",
            required_keywords=("api", "endpoint"),
            blocked_keywords=("mobile",),
        )
    )
    orch.set_runtime_availability(
        vps_available=True,
        local_gpu_available=False,
        cpu_available=True,
    )
    dataset_path = orch._agent_dataset_root("api") / "bug_dataset.jsonl"
    dataset_path.write_text(
        json.dumps(
            {
                "sample_id": "api-bug-1",
                "agent_id": "api",
                "source": "api",
                "bug_type": "api",
                "text": "API endpoint returns malformed response",
            }
        )
        + "\n",
        encoding="utf-8",
    )

    checkpoint = orch.save_checkpoint(
        "api",
        model_state={"weight": torch.ones(2, 2)},
        optimizer_state={"lr": 1e-3},
        scheduler_state={"gamma": 0.95},
        step=25,
        epoch=2,
        metrics={"validation_accuracy": 0.91, "validation_loss": 0.11},
        execution_target="vps",
        force=True,
    )
    orch.wait_for_backups()
    request = orch.queue_incremental_training(
        "api",
        reason="new_bug:api",
        dataset_path=str(dataset_path),
        bug_fingerprint="bug-1",
        preferred_target="vps",
    )

    checkpoint_dir = orch.checkpoint_root / "agent_api" / checkpoint.checkpoint_id
    receipt_path = checkpoint_dir / "backup_receipt.json"
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    secondary_dir = orch.secondary_backup_root / "agent_api" / checkpoint.checkpoint_id
    hybrid_dir = orch.hybrid_root / "local_gpu" / "agent_api" / checkpoint.checkpoint_id
    if secondary_dir.exists():
        import shutil

        shutil.rmtree(secondary_dir)
    if hybrid_dir.exists():
        import shutil

        shutil.rmtree(hybrid_dir)
    receipt["completed_locations"] = 1
    receipt["secondary_path"] = str(secondary_dir)
    receipt["hybrid_paths"] = {"local_gpu": str(hybrid_dir)}
    receipt["remote_paths"] = []
    receipt_path.write_text(json.dumps(receipt, indent=2), encoding="utf-8")
    orch.close()

    recovered = ProductionTrainingOrchestrator(
        secure_root=str(secure_root),
        checkpoint_step_interval=5,
        checkpoint_time_interval_sec=60,
        bootstrap_default_agents=False,
    )
    recovered.set_runtime_availability(
        vps_available=False,
        local_gpu_available=True,
        cpu_available=True,
    )
    report = recovered.recover_startup_state(device="cpu")
    recovered.wait_for_backups()

    api_report = next(item for item in report.agents if item.agent_id == "api")
    assert api_report.restored is True
    assert api_report.resumed_checkpoint_id == checkpoint.checkpoint_id
    assert checkpoint.checkpoint_id in api_report.repaired_backups
    assert request.request_id in api_report.pending_request_ids
    assert request.request_id in api_report.rerouted_request_ids

    request_path = recovered.training_queue_root / "agent_api" / f"{request.request_id}.json"
    request_payload = json.loads(request_path.read_text(encoding="utf-8"))
    assert request_payload["target"] == "local_gpu"
    assert request_payload["fallback_target"] == "cpu"

    repaired_receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    assert repaired_receipt["completed_locations"] >= 2
    recovered.close()


def test_default_bootstrap_registers_23_specialized_agents(
    tmp_path,
    monkeypatch,
    fake_safetensors,
):
    fake_storage = _FakeStorage()
    monkeypatch.setattr(
        "impl_v1.training.distributed.production_training_orchestrator.get_storage",
        lambda: fake_storage,
    )
    orch = ProductionTrainingOrchestrator(
        secure_root=str(tmp_path / "secure_data"),
        checkpoint_step_interval=5,
        checkpoint_time_interval_sec=60,
        bootstrap_default_agents=True,
    )
    try:
        agent_ids = orch.list_agent_ids()
        assert len(agent_ids) == 23
        assert all(
            orch.get_profile(agent_id).parameter_count == 130_000_000
            for agent_id in agent_ids
        )
    finally:
        orch.close()
