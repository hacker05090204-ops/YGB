"""
Pytest coverage for the HDD engine.

This test uses a real writable temporary directory instead of a hard-coded
drive letter so collection and execution remain portable when a specific HDD
volume is unavailable in the current workspace.
"""

import time
import uuid

from native.hdd_engine.hdd_engine import HDDEngine, LifecycleState


def test_hdd_engine_crud_and_cache(tmp_path):
    engine_root = tmp_path / "ygb_hdd"
    engine = HDDEngine(str(engine_root))

    assert engine.initialize() is True, f"root={engine.root}"

    stats = engine.get_stats()
    assert stats["initialized"] is True
    assert stats["hdd_root"] == str(engine_root)
    assert stats["disk_usage"]["total_bytes"] > 0

    uid = uuid.uuid4().hex[:8]
    user_id = f"test-{uid}"
    user = engine.create_entity(
        "users",
        user_id,
        {
            "name": "Full Test",
            "email": f"{uid}@ygb.dev",
            "role": "hunter",
        },
    )
    assert user["entity_id"] == user_id

    entity = engine.read_entity("users", user_id)
    assert entity is not None
    assert entity["latest"]["name"] == "Full Test"
    assert len(entity["records"]) == 1

    started = time.perf_counter()
    cached_entity = engine.read_entity("users", user_id)
    cache_ms = (time.perf_counter() - started) * 1000
    assert cached_entity == entity
    assert cache_ms < 5.0, f"cache_read_ms={cache_ms:.2f}"

    record = engine.append_record(
        "users",
        user_id,
        {"action": "login", "ip": "127.0.0.1"},
    )
    assert record["op"] == "UPDATE"

    updated_entity = engine.read_entity("users", user_id)
    assert updated_entity is not None
    assert len(updated_entity["records"]) == 2
    assert updated_entity["latest"]["action"] == "login"

    listed = engine.list_entities("users")
    assert any(meta["entity_id"] == user_id for meta in listed)

    assert engine.count_entities("users") >= 1

    assert engine.update_lifecycle("users", user_id, LifecycleState.ACTIVE) is True
    assert engine.update_lifecycle("users", user_id, LifecycleState.COMPLETED) is True

    metadata = engine.read_metadata("users", user_id)
    assert metadata is not None
    assert metadata["lifecycle_state"] == LifecycleState.COMPLETED.value

    engine.invalidate_cache()
    refreshed_metadata = engine.read_metadata("users", user_id)
    assert refreshed_metadata is not None
    assert refreshed_metadata["lifecycle_state"] == LifecycleState.COMPLETED.value

    target_id = f"tgt-{uuid.uuid4().hex[:8]}"
    target = engine.create_entity(
        "targets",
        target_id,
        {
            "program_name": "TestCorp",
            "scope": "*.testcorp.com",
            "payout_tier": "high",
        },
    )
    assert target["entity_id"] == target_id

    assert engine.count_entities("users") >= 1
    assert engine.count_entities("targets") >= 1

    disk = engine._get_disk_usage()
    assert disk["total_bytes"] > 0

    final_stats = engine.get_stats()
    assert final_stats["initialized"] is True
    assert final_stats["entity_counts"]["users"] >= 1
    assert final_stats["entity_counts"]["targets"] >= 1
    assert final_stats["total_entities"] >= 2
    assert final_stats["disk_usage"]["total_bytes"] > 0
