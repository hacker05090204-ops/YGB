from __future__ import annotations

import threading
import time

import pytest

from scripts.expert_task_queue import (
    STATUS_AVAILABLE,
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


def test_expert_queue_claim_atomic(tmp_path):
    status_path = tmp_path / "experts_status.json"
    initialize_status_file(status_path)

    barrier = threading.Barrier(3)
    claims: list[dict | None] = []
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

    threads = [threading.Thread(target=worker, args=(idx,)) for idx in range(3)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    expert_ids = [int(item["expert_id"]) for item in claims if item is not None]

    assert len(expert_ids) == 3
    assert len(expert_ids) == len(set(expert_ids))


def test_expert_queue_claim_timeout(tmp_path):
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


def test_expert_queue_four_concurrent_claimers_receive_distinct_experts(tmp_path):
    status_path = tmp_path / "experts_status.json"
    initialize_status_file(status_path)

    worker_count = 4
    barrier = threading.Barrier(worker_count)
    claims: list[dict | None] = []
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

    threads = [threading.Thread(target=worker, args=(idx,)) for idx in range(worker_count)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    expert_ids = [int(item["expert_id"]) for item in claims if item is not None]
    assert len(expert_ids) == worker_count
    assert len(expert_ids) == len(set(expert_ids))


def test_expert_queue_release_requires_active_matching_claimer(tmp_path):
    status_path = tmp_path / "experts_status.json"
    initialize_status_file(status_path)

    claimed = claim_next_expert(
        "worker-a",
        status_path=status_path,
        claim_timeout_seconds=60.0,
    )
    assert claimed is not None
    expert_id = int(claimed["expert_id"])

    with pytest.raises(RuntimeError, match="is claimed by worker-a"):
        release_expert(
            expert_id,
            status_path=status_path,
            worker_id="worker-b",
            status=STATUS_FAILED,
            error="wrong_worker",
        )

    release_expert(
        expert_id,
        status_path=status_path,
        worker_id="worker-a",
        status=STATUS_AVAILABLE,
    )

    with pytest.raises(RuntimeError, match="is not actively claimed"):
        release_expert(
            expert_id,
            status_path=status_path,
            worker_id="worker-a",
            status=STATUS_FAILED,
            error="stale_release",
        )


def test_expert_queue_releases_persist_after_four_concurrent_claims(tmp_path):
    status_path = tmp_path / "experts_status.json"
    initialize_status_file(status_path)

    worker_count = 4
    claim_barrier = threading.Barrier(worker_count)
    claims: list[dict | None] = []
    claims_lock = threading.Lock()

    def claim_worker(worker_index: int) -> None:
        claim_barrier.wait()
        claim = claim_next_expert(
            f"worker-{worker_index}",
            status_path=status_path,
            claim_timeout_seconds=60.0,
        )
        with claims_lock:
            claims.append(claim)

    claim_threads = [
        threading.Thread(target=claim_worker, args=(idx,)) for idx in range(worker_count)
    ]
    for thread in claim_threads:
        thread.start()
    for thread in claim_threads:
        thread.join()

    claimed_records = [item for item in claims if item is not None]
    claimed_expert_ids = [int(item["expert_id"]) for item in claimed_records]
    assert len(claimed_expert_ids) == worker_count
    assert len(claimed_expert_ids) == len(set(claimed_expert_ids))

    release_barrier = threading.Barrier(worker_count)

    def release_worker(claimed: dict) -> None:
        release_barrier.wait()
        expert_id = int(claimed["expert_id"])
        worker_id = str(claimed["claimed_by"])
        release_expert(
            expert_id,
            status_path=status_path,
            worker_id=worker_id,
            status=STATUS_COMPLETED,
            val_f1=0.50 + (expert_id / 1000.0),
            checkpoint_path=f"checkpoints/expert_{expert_id}.safetensors",
        )

    release_threads = [
        threading.Thread(target=release_worker, args=(claimed,))
        for claimed in claimed_records
    ]
    for thread in release_threads:
        thread.start()
    for thread in release_threads:
        thread.join()

    first_load = load_status(status_path)
    second_load = load_status(status_path)
    for state in (first_load, second_load):
        for expert_id in claimed_expert_ids:
            record = _get_expert_record(state, expert_id)
            assert record["status"] == STATUS_COMPLETED
            assert record["claimed_by"] is None
            assert record["claimed_at"] is None
            assert record["claim_expires_at_epoch"] is None
            assert record["last_result_status"] == STATUS_COMPLETED
            assert int(record["completed_count"]) >= 1

