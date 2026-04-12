from __future__ import annotations

import asyncio

import pytest

from backend.auth import auth_guard
from backend.governance.clock_guard import ClockGuard
from backend.tasks.central_task_queue import FileBackedTaskQueue, TaskPriority
from backend.tasks.industrial_agent import bootstrap_demo


def _run(coro):
    return asyncio.run(coro)


def test_demo_task_enqueue_blocked_outside_test_only_context(tmp_path, monkeypatch):
    monkeypatch.delenv("YGB_ENABLE_TEST_ONLY_PATHS", raising=False)
    monkeypatch.setattr("backend.tasks.central_task_queue.sys.modules", {})
    queue = FileBackedTaskQueue(str(tmp_path / "queue"))

    with pytest.raises(RuntimeError, match="disabled outside test-only execution"):
        _run(
            queue.enqueue(
                "demo_ingest",
                {"url": "https://example.com/report/1"},
                priority=TaskPriority.HIGH,
                route="grabber",
            )
        )


def test_non_demo_task_still_enqueues_normally(tmp_path):
    queue = FileBackedTaskQueue(str(tmp_path / "queue"))
    task = _run(
        queue.enqueue(
            "ingest_url",
            {"url": "https://example.com/report/2"},
            priority=TaskPriority.HIGH,
            route="grabber",
        )
    )

    assert task.kind == "ingest_url"


def test_clock_guard_simulation_blocked_outside_test_only_context(monkeypatch):
    monkeypatch.delenv("YGB_CLOCK_SIMULATION", raising=False)
    guard = ClockGuard()

    with pytest.raises(RuntimeError, match="clock skew simulation is disabled"):
        guard.check_skew_simulated(1000.0, 1000.0)


def test_clock_guard_simulation_logs_critical_in_production(monkeypatch, caplog):
    monkeypatch.setenv("YGB_CLOCK_SIMULATION", "1")
    monkeypatch.setenv("YGB_ENV", "production")
    guard = ClockGuard()

    with caplog.at_level("CRITICAL"):
        result = guard.check_skew_simulated(1000.0, 1000.0)

    assert result.passed is True
    assert any("YGB_ENV=production" in record.message for record in caplog.records)


def test_temporary_auth_bypass_ignored_outside_test_only_context(monkeypatch):
    monkeypatch.setenv("YGB_TEMP_AUTH_BYPASS", "true")
    monkeypatch.setenv("YGB_ENV", "development")
    monkeypatch.delenv("YGB_ENABLE_TEST_ONLY_PATHS", raising=False)
    monkeypatch.setattr(auth_guard.sys, "modules", {})

    assert auth_guard.is_temporary_auth_bypass_enabled() is False


def test_bootstrap_demo_blocked_outside_test_only_context(monkeypatch):
    monkeypatch.delenv("YGB_ENABLE_TEST_ONLY_PATHS", raising=False)
    monkeypatch.setattr("backend.tasks.industrial_agent.sys.modules", {})

    with pytest.raises(RuntimeError, match="disabled outside test-only execution"):
        asyncio.run(bootstrap_demo())
