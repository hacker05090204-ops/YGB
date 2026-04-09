from __future__ import annotations

import threading
import time

import numpy as np
import pytest

torch = pytest.importorskip("torch")

import training_controller
from impl_v1.phase49.moe import EXPERT_FIELDS, MoEBugClassifier, MoEConfig, NoisyTopKGate
from scripts import device_agent
from scripts.expert_task_queue import (
    STATUS_COMPLETED,
    STATUS_FAILED,
    claim_next_expert,
    initialize_status_file,
    load_status,
    release_expert,
)


def _get_expert_record(state: dict, expert_id: int) -> dict:
    return next(
        item for item in state["experts"] if int(item["expert_id"]) == int(expert_id)
    )


def test_claim_next_expert_returns_none_when_all_experts_claimed(tmp_path):
    status_path = tmp_path / "experts_status.json"
    initialize_status_file(status_path)

    claims = [
        claim_next_expert(
            f"worker-{idx}",
            status_path=status_path,
            claim_timeout_seconds=60.0,
        )
        for idx in range(len(EXPERT_FIELDS))
    ]

    assert all(claim is not None for claim in claims)
    assert (
        claim_next_expert(
            "worker-extra",
            status_path=status_path,
            claim_timeout_seconds=60.0,
        )
        is None
    )


def test_expired_claims_are_released_after_timeout(tmp_path):
    status_path = tmp_path / "experts_status.json"
    initialize_status_file(status_path)

    first_claim = claim_next_expert(
        "worker-a",
        status_path=status_path,
        claim_timeout_seconds=0.01,
    )
    assert first_claim is not None

    time.sleep(0.05)
    second_claim = claim_next_expert(
        "worker-b",
        status_path=status_path,
        claim_timeout_seconds=60.0,
    )

    assert second_claim is not None
    assert int(second_claim["expert_id"]) == int(first_claim["expert_id"])
    state = load_status(status_path)
    assert _get_expert_record(state, int(first_claim["expert_id"]))["status"] == "CLAIMED"


def test_simultaneous_claims_do_not_return_same_expert(tmp_path):
    status_path = tmp_path / "experts_status.json"
    initialize_status_file(status_path)

    barrier = threading.Barrier(8)
    claims = []
    claims_lock = threading.Lock()

    def worker(worker_index: int) -> None:
        barrier.wait()
        claim = claim_next_expert(
            f"worker-{worker_index}",
            status_path=status_path,
            claim_timeout_seconds=60.0,
        )
        with claims_lock:
            claims.append(claim)

    threads = [threading.Thread(target=worker, args=(idx,)) for idx in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    expert_ids = [int(item["expert_id"]) for item in claims if item is not None]
    assert len(expert_ids) == 8
    assert len(expert_ids) == len(set(expert_ids))


def test_release_expert_updates_best_val_f1_only_when_improved(tmp_path):
    status_path = tmp_path / "experts_status.json"
    initialize_status_file(status_path)

    claimed = claim_next_expert(
        "worker-a",
        status_path=status_path,
        claim_timeout_seconds=60.0,
    )
    assert claimed is not None
    expert_id = int(claimed["expert_id"])

    release_expert(
        expert_id,
        status_path=status_path,
        worker_id="worker-a",
        status=STATUS_FAILED,
        val_f1=0.80,
        val_precision=0.78,
        val_recall=0.82,
        checkpoint_path="checkpoints/better.safetensors",
    )

    reclaimed = claim_next_expert(
        "worker-b",
        status_path=status_path,
        claim_timeout_seconds=60.0,
    )
    assert reclaimed is not None
    assert int(reclaimed["expert_id"]) == expert_id

    release_expert(
        expert_id,
        status_path=status_path,
        worker_id="worker-b",
        status=STATUS_COMPLETED,
        val_f1=0.40,
        val_precision=0.39,
        val_recall=0.41,
        checkpoint_path="checkpoints/worse.safetensors",
    )

    state = load_status(status_path)
    record = _get_expert_record(state, expert_id)
    assert record["best_val_f1"] == pytest.approx(0.80)
    assert record["best_checkpoint_path"] == "checkpoints/better.safetensors"
    assert record["last_val_f1"] == pytest.approx(0.40)
    assert record["last_checkpoint_path"] == "checkpoints/worse.safetensors"


def test_moe_model_imports_and_runs_forward_without_error():
    config = MoEConfig(
        d_model=64,
        n_experts=len(EXPERT_FIELDS),
        top_k=2,
        expert_hidden_mult=2,
        dropout=0.0,
        gate_noise=0.0,
        aux_loss_coeff=0.01,
    )
    model = MoEBugClassifier(config, input_dim=32, output_dim=2)

    logits = model(torch.randn(4, 32))

    assert logits.shape == (4, 2)
    assert torch.isfinite(model.aux_loss)


def test_noisy_topk_gate_is_input_dependent_learned_routing():
    gate = NoisyTopKGate(d_model=2, n_experts=3, top_k=1, noise_scale=0.0)
    with torch.no_grad():
        gate.w_gate.weight.copy_(
            torch.tensor(
                [
                    [1.0, 0.0],
                    [0.0, 1.0],
                    [-1.0, -1.0],
                ],
                dtype=torch.float32,
            )
        )

    gates, indices, aux_loss = gate(
        torch.tensor(
            [
                [2.0, 0.1],
                [0.1, 2.0],
            ],
            dtype=torch.float32,
        )
    )

    assert int(indices[0, 0]) != int(indices[1, 0])
    assert torch.allclose(gates.sum(dim=1), torch.ones(2))
    assert torch.isfinite(aux_loss)


def test_build_configured_model_switches_between_moe_and_legacy(monkeypatch):
    config = training_controller.TrainingControllerConfig(
        input_dim=32,
        hidden_dim=64,
        num_classes=2,
    )

    monkeypatch.setenv("YGB_USE_MOE", "true")
    moe_model, _ = training_controller._build_configured_model(
        config=config,
        total_samples=128,
        effective_hidden_dim=64,
        device=torch.device("cpu"),
        nn_module=torch.nn,
    )
    assert moe_model.__class__.__name__ == "MoEBugClassifier"

    monkeypatch.setenv("YGB_USE_MOE", "false")
    legacy_model, _ = training_controller._build_configured_model(
        config=config,
        total_samples=128,
        effective_hidden_dim=64,
        device=torch.device("cpu"),
        nn_module=torch.nn,
    )
    assert legacy_model.__class__.__name__ == "BugClassifier"


def test_train_single_expert_returns_required_result_fields(monkeypatch):
    field_name = EXPERT_FIELDS[0]
    fake_dataset_state = training_controller.DatasetState(
        hash="dataset-hash",
        sample_count=12,
        feature_dim=32,
        num_classes=2,
        entropy=1.0,
        trainable=True,
        manifest_path="secure_data/dataset_manifest.json",
        enforcement_passed=True,
        dataset_source="INGESTION_PIPELINE",
        verification_passed=True,
        verification_code="DATASET_VALIDATED",
        verification_message="ok",
    )
    monkeypatch.setattr(
        training_controller,
        "phase2_dataset_finalization",
        lambda config: (
            fake_dataset_state,
            np.empty((0, config.input_dim), dtype=np.float32),
            np.empty((0,), dtype=np.int64),
        ),
    )
    monkeypatch.setattr(training_controller, "_load_real_ingestion_dataset", lambda config: object())

    samples = [
        {
            "endpoint": f"CVE-2024-00{i:02d}",
            "parameters": "id=1",
            "exploit_vector": "api rest injection",
            "impact": "CVSS:8.0|HIGH",
            "source_tag": "nvd",
            "fingerprint": f"fp-{i}",
            "reliability": 0.9,
        }
        for i in range(12)
    ]
    features = np.random.default_rng(7).normal(size=(12, 32)).astype(np.float32)
    labels = np.asarray([0] * 6 + [1] * 6, dtype=np.int64)
    monkeypatch.setattr(
        training_controller,
        "_materialize_ingestion_dataset",
        lambda dataset: (samples, features, labels),
    )
    monkeypatch.setattr(training_controller, "_route_ingestion_sample", lambda sample: field_name)

    fake_result = training_controller.TrainingResult(
        epochs_completed=1,
        final_loss=0.50,
        final_accuracy=0.75,
        best_accuracy=0.75,
        cluster_sps=10.0,
        merged_weight_hash="hash123",
        drift_aborted=False,
        per_epoch=[{"epoch": 1, "val_f1": 0.75}],
        val_accuracy=0.75,
        val_f1=0.75,
        val_precision=0.70,
        val_recall=0.80,
        best_val_loss=0.50,
        checkpoint_path="checkpoints/base.safetensors",
        status="COMPLETED",
    )
    monkeypatch.setattr(
        training_controller,
        "phase3_training_execution",
        lambda config, X, y, dataset_hash, save_moe_global_checkpoint=False: fake_result,
    )
    monkeypatch.setattr(
        training_controller,
        "_save_expert_checkpoint",
        lambda config, result, expert_id, field_name: (
            f"checkpoints/expert_{expert_id}_{field_name}_{result.val_f1:.3f}.safetensors"
        ),
    )

    result = training_controller.train_single_expert(0, field_name)

    assert result.status == "COMPLETED"
    assert result.val_f1 == pytest.approx(0.75)
    assert result.val_precision == pytest.approx(0.70)
    assert result.val_recall == pytest.approx(0.80)
    assert result.checkpoint_path.endswith("expert_0_web_vulns_0.750.safetensors")


def test_device_agent_marks_failed_on_exception(monkeypatch, tmp_path):
    status_path = tmp_path / "experts_status.json"
    released = {}

    monkeypatch.setattr(
        device_agent,
        "claim_next_expert",
        lambda worker_id, status_path, claim_timeout_seconds: {
            "expert_id": 0,
            "field_name": EXPERT_FIELDS[0],
        },
    )

    def _capture_release(
        expert_id,
        *,
        status_path,
        worker_id,
        status,
        val_f1=None,
        val_precision=None,
        val_recall=None,
        checkpoint_path="",
        error="",
    ):
        released.update(
            {
                "expert_id": expert_id,
                "worker_id": worker_id,
                "status": status,
                "error": error,
            }
        )
        return dict(released)

    monkeypatch.setattr(device_agent, "release_expert", _capture_release)

    def _raise_failure(expert_id, field_name):
        raise RuntimeError("boom")

    monkeypatch.setattr(device_agent, "train_single_expert", _raise_failure)

    with pytest.raises(RuntimeError, match="boom"):
        device_agent.run_device_agent("worker-x", status_path=status_path)

    assert released["status"] == STATUS_FAILED
    assert released["worker_id"] == "worker-x"
    assert "boom" in released["error"]
