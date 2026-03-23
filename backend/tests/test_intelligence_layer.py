from __future__ import annotations

import socket
import urllib.request
from unittest.mock import patch

import pytest

from api import intelligence_layer as intelligence_module
from api.intelligence_layer import IntelligenceLayer


@pytest.fixture(scope="module")
def layer() -> IntelligenceLayer:
    return IntelligenceLayer()


def test_analyze_target_description_makes_zero_network_calls(layer: IntelligenceLayer) -> None:
    calls = []

    def fail(*args, **kwargs):
        calls.append((args, kwargs))
        raise AssertionError("network call attempted")

    with patch.object(urllib.request, "urlopen", fail), patch.object(socket, "create_connection", fail):
        result = layer.analyze_target_description(
            description="web application login form with account settings",
            technology_stack=["python", "django"],
            scope="example.com",
        )

    assert calls == []
    assert 0.0 <= result.confidence <= 1.0


def test_execute_guard_checked_before_any_inference(
    layer: IntelligenceLayer,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    called = {"run_model": False}

    def fake_run_model(_features):
        called["run_model"] = True
        return 0.99

    monkeypatch.setattr(intelligence_module, "can_ai_execute", lambda: (True, "blocked"))
    monkeypatch.setattr(layer, "_run_model", fake_run_model)

    with pytest.raises(RuntimeError, match="can_ai_execute"):
        layer.analyze_target_description(
            description="admin dashboard login flow",
            technology_stack=["django"],
            scope="example.com",
        )

    assert called["run_model"] is False


def test_requires_human_verification_is_always_true(layer: IntelligenceLayer) -> None:
    result = layer.analyze_target_description(
        description="password reset and session management flow",
        technology_stack=["python", "django"],
        scope="example.com",
    )

    assert result.requires_human_verification is True


def test_text_only_analysis_without_stack_info(layer: IntelligenceLayer) -> None:
    result = layer.analyze_target_description(
        description="standalone text description of a login form and profile area",
        technology_stack=[],
        scope="",
    )

    assert 0.0 <= result.confidence <= 1.0
    assert isinstance(result.pattern_matches, list)
    assert isinstance(result.suggested_focus_areas, list)
