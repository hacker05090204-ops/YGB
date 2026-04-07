from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

import backend.startup.pipeline_bootstrap as pipeline_bootstrap_module


class _FakeGrabber:
    def __init__(self, config):
        self.config = config
        self.start_calls = 0
        self.stop_calls = 0

    def start_scheduled(self):
        self.start_calls += 1

    def stop(self):
        self.stop_calls += 1


class _FakeController:
    def __init__(self):
        self.start_calls = 0
        self.stop_calls = 0
        self.running = False
        self.config = SimpleNamespace(check_interval_seconds=60.0)

    def start(self):
        self.start_calls += 1
        self.running = True
        return True

    def stop(self, timeout=None):
        self.stop_calls += 1
        self.running = False
        return True

    def is_scheduled_running(self):
        return self.running


def test_bootstrap_pipeline_starts_autograbber_and_auto_train(monkeypatch):
    created: dict[str, object] = {}

    def _initialize_autograbber(config):
        grabber = _FakeGrabber(config)
        created["grabber"] = grabber
        return grabber

    controller = _FakeController()
    monkeypatch.setattr(
        pipeline_bootstrap_module,
        "initialize_autograbber",
        _initialize_autograbber,
    )
    monkeypatch.setattr(
        pipeline_bootstrap_module,
        "get_auto_train_controller",
        lambda: controller,
    )
    monkeypatch.setenv("YGB_AUTOGRABBER_GRAB_INTERVAL_SECONDS", "17")

    result = pipeline_bootstrap_module.bootstrap_pipeline()

    grabber = created["grabber"]
    assert isinstance(grabber, _FakeGrabber)
    assert grabber.start_calls == 1
    assert controller.start_calls == 1
    assert result.autograbber is grabber
    assert result.auto_train_controller is controller
    assert result.autograbber_config.sources == ["nvd", "cisa", "osv", "github"]
    assert result.autograbber_config.cycle_interval_seconds == 17
    assert result.autograbber_started is True
    assert result.auto_train_started is True


def test_bootstrap_pipeline_stops_autograbber_when_controller_start_fails(monkeypatch):
    created: dict[str, object] = {}

    def _initialize_autograbber(config):
        grabber = _FakeGrabber(config)
        created["grabber"] = grabber
        return grabber

    class _BrokenController:
        def __init__(self):
            self.start_calls = 0

        def start(self):
            self.start_calls += 1
            raise RuntimeError("controller start failed")

    monkeypatch.setattr(
        pipeline_bootstrap_module,
        "initialize_autograbber",
        _initialize_autograbber,
    )
    monkeypatch.setattr(
        pipeline_bootstrap_module,
        "get_auto_train_controller",
        _BrokenController,
    )

    with pytest.raises(RuntimeError, match="controller start failed"):
        pipeline_bootstrap_module.bootstrap_pipeline()

    grabber = created["grabber"]
    assert isinstance(grabber, _FakeGrabber)
    assert grabber.start_calls == 1
    assert grabber.stop_calls == 1


def test_api_server_lifespan_bootstraps_pipeline_on_startup():
    server_path = Path("api/server.py")
    content = server_path.read_text(encoding="utf-8")

    lifespan_idx = content.find("async def lifespan")
    bootstrap_call_idx = content.rfind("bootstrap_pipeline()")

    assert lifespan_idx != -1
    assert bootstrap_call_idx != -1
    assert bootstrap_call_idx > lifespan_idx
