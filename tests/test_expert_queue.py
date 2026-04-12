from __future__ import annotations

import threading
import time

from scripts.expert_task_queue import (
    claim_next_expert,
    initialize_status_file,
    load_status,
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

