from __future__ import annotations

import json

import backend.agent.self_reflection as self_reflection_mod
from backend.agent.self_reflection import IDLE_THRESHOLD, MethodLibrary, SelfReflectionEngine


def test_idle_threshold_constant_is_300():
    assert IDLE_THRESHOLD == 300


def test_self_reflection_invents_and_persists_method_after_repeated_failures(tmp_path):
    root = tmp_path / "self-reflection"
    library = MethodLibrary(root=root)
    engine = SelfReflectionEngine(method_library=library, invention_threshold=4)

    for attempt in range(4):
        result = engine.observe_failure(
            "xss_basic",
            "basic payload filtered",
            reason=f"attempt_{attempt + 1}_blocked",
            context={"attempt": attempt + 1},
        )

    invented_methods = library.list_methods(invented_by="self_reflection")

    assert result["failure_count"] == 4
    assert len(invented_methods) >= 1
    assert all(method.invented_by == "self_reflection" for method in invented_methods)

    invented_method = invented_methods[0]
    assert invented_method.attack_family == "xss_basic"
    assert invented_method.failure_pattern == "basic payload filtered"
    assert invented_method.source_failure_count == 4
    assert result["invented_method"] is not None
    assert result["invented_method"].method_id == invented_method.method_id

    reloaded_library = MethodLibrary(root=root)
    persisted_methods = reloaded_library.list_methods(invented_by="self_reflection")
    assert [method.method_id for method in persisted_methods] == [invented_method.method_id]

    failure_key = engine.build_failure_key("xss_basic", "basic payload filtered")
    failure_summary = engine.get_failure_summary()
    assert failure_summary[failure_key]["count"] == 4
    assert failure_summary[failure_key]["invented_method_id"] == invented_method.method_id

    events = engine.list_reflection_events()
    assert any(event.event_type == "reflection" for event in events)
    assert any(
        event.event_type == "method_invented"
        and event.invented_method_id == invented_method.method_id
        for event in events
    )

    observations = engine.list_failure_observations()
    assert len(observations) == 4
    assert observations[-1].count_for_pattern == 4

    persisted_library_payload = json.loads(
        (root / "method_library.json").read_text(encoding="utf-8")
    )
    assert persisted_library_payload["methods"][0]["invented_by"] == "self_reflection"


def test_idle_reflection_rate_limits_and_expands_queue_fields(tmp_path, monkeypatch):
    root = tmp_path / "self-reflection"
    library = MethodLibrary(root=root)
    engine = SelfReflectionEngine(method_library=library, invention_threshold=1)

    engine.observe_failure(
        "csrf_basic",
        "csrf",
        "token required with same-site cookies",
        reason="idle_seed",
    )

    clock = iter(
        [
            1_000.0,
            1_000.0 + IDLE_THRESHOLD - 1,
            1_000.0 + IDLE_THRESHOLD + 1,
        ]
    )
    monkeypatch.setattr(self_reflection_mod.time, "time", lambda: next(clock))

    first = engine.idle_reflection(["web_vulns"], idle_seconds=IDLE_THRESHOLD)
    second = engine.idle_reflection(["web_vulns"], idle_seconds=IDLE_THRESHOLD)
    third = engine.idle_reflection(["web_vulns"], idle_seconds=IDLE_THRESHOLD + 1)

    invented_methods = library.list_methods(invented_by="self_reflection", field="csrf")

    assert first["triggered"] is True
    assert first["rate_limited"] is False
    assert "csrf" in first["checked_fields"]
    assert "csrf" in first["reflected_fields"]
    assert len(invented_methods) == 1

    assert second["rate_limited"] is True
    assert second["reason"] == "rate_limited"

    assert third["triggered"] is True
    assert len(library.list_methods(invented_by="self_reflection", field="csrf")) == 1
