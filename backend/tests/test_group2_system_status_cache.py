from __future__ import annotations

import asyncio
import time
from types import SimpleNamespace

import backend.api.system_status as system_status
import backend.startup.pipeline_bootstrap as pipeline_bootstrap_module


def _reset_status_cache() -> None:
    with system_status._cache_lock:
        system_status._status_cache = {}
        system_status._cache_ts = 0.0
        system_status._refresh_in_progress = False


def _base_status_payload() -> dict[str, object]:
    return {
        "overall_status": "HEALTHY",
        "overall_health": "HEALTHY",
        "timestamp": "2026-04-08T00:00:00+00:00",
        "last_checked": "2026-04-08T00:00:00+00:00",
        "uptime_s": 1.0,
        "boot_time": 1.0,
        "subsystems": {
            "readiness": {"health": "HEALTHY", "available": True},
            "storage": {"health": "HEALTHY", "available": True},
            "auth": {"health": "HEALTHY", "available": True},
            "governance": {"health": "HEALTHY", "available": True},
            "ingestion": {"health": "HEALTHY", "available": True},
            "training": {"health": "HEALTHY", "available": True},
            "voice": {"health": "HEALTHY", "available": True},
            "sync": {
                "health": "HEALTHY",
                "available": True,
                "sync_mode": "STANDALONE",
                "sync_message": "Single-device mode. Set YGB_SYNC_PEERS for mesh sync.",
            },
            "reporting": {"health": "HEALTHY", "available": True},
        },
        "metrics": {},
        "canonical_status": {"schema_version": 2},
        "sync_mode": "STANDALONE",
        "sync_message": "Single-device mode. Set YGB_SYNC_PEERS for mesh sync.",
    }


def test_second_request_returns_with_cache_hit_under_5ms(monkeypatch):
    _reset_status_cache()

    def _slow_compute() -> dict[str, object]:
        time.sleep(0.02)
        return _base_status_payload()

    monkeypatch.setattr(system_status, "_compute_full_status", _slow_compute)

    first = asyncio.run(system_status.aggregated_system_status(user={"sub": "user-1"}))
    started = time.perf_counter()
    second = asyncio.run(system_status.aggregated_system_status(user={"sub": "user-1"}))
    elapsed_ms = (time.perf_counter() - started) * 1000

    assert first["overall_health"] == "HEALTHY"
    assert second["cached"] is True
    assert "cache_age_seconds" in second
    assert elapsed_ms < 5.0


def test_cache_age_field_present_and_background_thread_started_on_stale_cache(monkeypatch):
    _reset_status_cache()
    with system_status._cache_lock:
        system_status._status_cache = _base_status_payload()
        system_status._cache_ts = time.monotonic() - (system_status.CACHE_TTL_SECONDS + 1)

    thread_events: list[str] = []

    class _FakeThread:
        def __init__(self, *, target, daemon):
            self._target = target
            self.daemon = daemon

        def start(self):
            thread_events.append("started")

    monkeypatch.setattr(system_status.threading, "Thread", _FakeThread)

    result = asyncio.run(system_status.aggregated_system_status(user={"sub": "user-1"}))

    assert "cache_age_seconds" in result
    assert thread_events == ["started"]


def test_standalone_sync_mode_keeps_overall_health_healthy(monkeypatch):
    def _fake_safe_call(name, _fn, *args, **kwargs):
        return {
            "readiness": {"ready": True},
            "metrics": {"requests": 1},
            "training": {"status": "idle"},
            "voice": {
                "pipeline_status": "OFFLINE",
                "local_only": True,
                "no_whisper_dependency": True,
                "no_google_stt_dependency": True,
            },
            "storage": {"storage_active": True},
            "canonical_status": {
                "schema_version": 2,
                "ingestion": {"last_cycle_time": "", "sources_active": []},
            },
            "auth": {"available": True},
            "governance": {"all_locked": True},
            "sync": {
                "sync_mode": "STANDALONE",
                "sync_message": "Single-device mode. Set YGB_SYNC_PEERS for mesh sync.",
                "stale": False,
            },
            "reporting": {"available": True},
        }[name]

    monkeypatch.setattr(system_status, "_safe_call", _fake_safe_call)

    result = system_status._compute_full_status()

    assert result["overall_health"] == "HEALTHY"
    assert result["sync_mode"] == "STANDALONE"
    assert result["sync_message"] == "Single-device mode. Set YGB_SYNC_PEERS for mesh sync."


def test_storage_down_marks_overall_health_critical(monkeypatch):
    def _fake_safe_call(name, _fn, *args, **kwargs):
        return {
            "readiness": {"ready": True},
            "metrics": {"requests": 1},
            "training": {"status": "idle"},
            "voice": {"status": "idle"},
            "storage": {"storage_active": False, "status": "INACTIVE"},
            "canonical_status": {
                "schema_version": 2,
                "ingestion": {"last_cycle_time": "", "sources_active": []},
            },
            "auth": {"available": True},
            "governance": {"all_locked": True},
            "sync": {
                "sync_mode": "STANDALONE",
                "sync_message": "Single-device mode. Set YGB_SYNC_PEERS for mesh sync.",
                "stale": False,
            },
            "reporting": {"available": True},
        }[name]

    monkeypatch.setattr(system_status, "_safe_call", _fake_safe_call)

    result = system_status._compute_full_status()

    assert result["overall_health"] == "CRITICAL"


def test_bootstrap_pipeline_seeds_system_status_cache(monkeypatch):
    created: dict[str, object] = {}

    class _FakeGrabber:
        def __init__(self, config):
            self.config = config

        def start_scheduled(self):
            created["grabber_started"] = True

        def stop(self):
            created["grabber_stopped"] = True

    class _FakeController:
        def __init__(self):
            self.config = SimpleNamespace(check_interval_seconds=30.0)

        def start(self):
            return True

        def is_scheduled_running(self):
            return True

    seed_calls: list[bool] = []
    monkeypatch.setattr(
        pipeline_bootstrap_module,
        "initialize_autograbber",
        lambda config: _FakeGrabber(config),
    )
    monkeypatch.setattr(
        pipeline_bootstrap_module,
        "get_auto_train_controller",
        lambda: _FakeController(),
    )
    monkeypatch.setattr(
        pipeline_bootstrap_module,
        "seed_system_status_cache",
        lambda: seed_calls.append(True) or True,
    )

    result = pipeline_bootstrap_module.bootstrap_pipeline()

    assert result.autograbber_started is True
    assert result.auto_train_started is True
    assert seed_calls == [True]
