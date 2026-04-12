from __future__ import annotations

import asyncio
import copy
import json
import time
from pathlib import Path

import backend.api.system_status as system_status
from backend.api.system_status_store import SYSTEM_STATUS_PATH, refresh_system_status_file


def test_system_status_file_exists():
    refresh_system_status_file()
    assert SYSTEM_STATUS_PATH.exists()


def test_system_status_schema_valid():
    refresh_system_status_file()
    with open(SYSTEM_STATUS_PATH, encoding="utf-8") as handle:
        status = json.load(handle)

    assert status["schema_version"] == 2
    assert "last_updated" in status
    assert set(status) == {"schema_version", "last_updated", "training", "ingestion", "sync", "gpu"}
    assert isinstance(status["training"]["last_accuracy"], float)
    assert isinstance(status["training"]["precision_breach"], bool)
    assert isinstance(status["training"]["checkpoint_sha256"], str)
    assert isinstance(status["ingestion"]["sources_active"], list)
    assert isinstance(status["sync"]["peers_connected"], int)
    assert isinstance(status["gpu"]["available"], bool)


def test_precision_breach_matches_runtime_status():
    refresh_system_status_file()
    canonical = json.loads(SYSTEM_STATUS_PATH.read_text(encoding="utf-8"))
    runtime_status = json.loads(Path("data/runtime_status.json").read_text(encoding="utf-8"))
    assert canonical["training"]["precision_breach"] == runtime_status["precision_breach"]


def _reset_status_cache() -> None:
    with system_status._cache_lock:
        system_status._status_cache = {}
        system_status._cache_ts = 0.0
        system_status._cache_has_refresh = False
        system_status._refresh_in_progress = False


def _assembled_status(
    *,
    readiness: dict[str, object] | None = None,
    metrics: dict[str, object] | None = None,
    training: dict[str, object] | None = None,
    voice: dict[str, object] | None = None,
    storage: dict[str, object] | None = None,
    canonical: dict[str, object] | None = None,
    auth: dict[str, object] | None = None,
    governance: dict[str, object] | None = None,
    sync: dict[str, object] | None = None,
    reporting: dict[str, object] | None = None,
) -> dict[str, object]:
    return system_status._assemble_status_payload(
        readiness=readiness or {"ready": True},
        metrics=metrics or {"requests": 1},
        training=training or {"status": "IDLE"},
        voice=voice
        or {
            "pipeline_status": "ONLINE",
            "local_only": False,
            "no_whisper_dependency": False,
            "no_google_stt_dependency": False,
        },
        storage=storage or {"storage_active": True, "status": "ACTIVE"},
        canonical=canonical
        or {
            "schema_version": 2,
            "ingestion": {"last_cycle_time": "", "sources_active": []},
        },
        auth=auth or {"available": True, "status": "HEALTHY"},
        governance=governance
        or {"all_locked": True, "available": True, "status": "HEALTHY"},
        sync=sync
        or {
            "sync_mode": "STANDALONE",
            "sync_message": "Single-device mode. Set YGB_SYNC_PEERS for mesh sync.",
            "stale": False,
        },
        reporting=reporting or {"available": True, "status": "HEALTHY"},
    )


def test_second_status_call_returns_cache_hit_under_5ms():
    _reset_status_cache()
    system_status._store_status_cache(_assembled_status(), refreshed=True)

    first = asyncio.run(system_status.aggregated_system_status(user={"sub": "phase2-user"}))
    started = time.perf_counter()
    second = asyncio.run(system_status.aggregated_system_status(user={"sub": "phase2-user"}))
    elapsed_ms = (time.perf_counter() - started) * 1000

    assert first["cached"] is True
    assert second["cached"] is True
    assert second["cache_age_seconds"] >= 0.0
    assert elapsed_ms < 5.0


def test_stale_cache_starts_background_refresh_and_returns_stale_snapshot(monkeypatch):
    _reset_status_cache()
    system_status._store_status_cache(_assembled_status(), refreshed=True)
    with system_status._cache_lock:
        system_status._cache_ts = time.monotonic() - (system_status.CACHE_TTL_SECONDS + 1.0)

    thread_events: list[str] = []

    class _FakeThread:
        def __init__(self, *, target, daemon):
            self._target = target
            self.daemon = daemon

        def start(self):
            thread_events.append("started")

    monkeypatch.setattr(system_status.threading, "Thread", _FakeThread)

    result = asyncio.run(system_status.aggregated_system_status(user={"sub": "phase2-user"}))

    assert thread_events == ["started"]
    assert result["cached"] is False
    assert result["cache_age_seconds"] > system_status.CACHE_TTL_SECONDS


def test_refresh_failure_keeps_previous_cache_and_clears_refresh_flag(monkeypatch):
    _reset_status_cache()
    payload = _assembled_status()
    system_status._store_status_cache(payload, refreshed=True)
    previous_cache = copy.deepcopy(system_status._status_cache)
    with system_status._cache_lock:
        system_status._refresh_in_progress = True

    def _boom() -> dict[str, object]:
        raise RuntimeError("refresh exploded")

    monkeypatch.setattr(system_status, "_compute_full_status", _boom)

    system_status._refresh_status_background()

    with system_status._cache_lock:
        assert system_status._status_cache == previous_cache
        assert system_status._refresh_in_progress is False


def test_storage_unavailable_forces_critical_overall_health():
    result = _assembled_status(storage={"storage_active": False, "status": "INACTIVE"})

    assert result["subsystems"]["storage"]["health"] == "CRITICAL"
    assert result["overall_health"] == "CRITICAL"


def test_standalone_sync_and_missing_voice_dependencies_remain_healthy():
    result = _assembled_status(
        voice={
            "pipeline_status": "OFFLINE",
            "local_only": True,
            "no_whisper_dependency": True,
            "no_google_stt_dependency": True,
        },
        sync={
            "sync_mode": "STANDALONE",
            "sync_message": "Single-device mode. Set YGB_SYNC_PEERS for mesh sync.",
            "stale": False,
        },
    )

    assert result["subsystems"]["voice"]["health"] == "INFORMATIONAL"
    assert result["subsystems"]["sync"]["health"] == "HEALTHY"
    assert result["overall_health"] == "HEALTHY"


def test_get_sync_status_includes_real_fields_and_standalone_is_healthy(monkeypatch):
    from backend.sync import health as sync_health
    from backend.sync import sync_engine as se

    class _Index:
        def get_file_count(self) -> int:
            return 7

        def get_total_bytes(self) -> int:
            return 77

    index = _Index()
    monkeypatch.setattr(sync_health, "get_sync_health", lambda: {
        "status": "DEGRADED",
        "last_sync": "",
        "peers": {"total": 0, "online": 0, "offline": 0, "devices": []},
    })
    monkeypatch.setattr(se, "get_local_sync_index", lambda: index)
    monkeypatch.setattr(se, "get_sync_mode", lambda: se.SyncMode.STANDALONE)
    monkeypatch.setattr(se, "get_last_sync_cycle", lambda: None)
    monkeypatch.setattr(se, "is_sync_configured", lambda: False)

    payload = system_status._get_sync_status()

    assert payload["status"] == "HEALTHY"
    assert payload["sync_mode"] == "STANDALONE"
    assert payload["mode"] == "STANDALONE"
    assert payload["configured"] is False
    assert payload["local_files"] == 7
    assert payload["local_bytes"] == 77
    assert payload["sync_message"] == "Single-device mode. Set YGB_SYNC_PEERS for mesh sync."
    assert payload["message"] == payload["sync_message"]
    assert payload["stale"] is False


def test_two_degraded_non_core_systems_produce_degraded_overall_health():
    result = _assembled_status(
        voice={"pipeline_status": "DEGRADED", "error": "voice runtime failure"},
        reporting={"status": "DEGRADED", "error": "report engine unavailable"},
    )

    assert result["subsystems"]["voice"]["health"] == "DEGRADED"
    assert result["subsystems"]["reporting"]["health"] == "DEGRADED"
    assert result["overall_health"] == "DEGRADED"
