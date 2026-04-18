from __future__ import annotations

import time
from types import SimpleNamespace

from scripts.expert_task_queue import initialize_status_file, load_status
from scripts.opportunistic_trainer import (
    DeviceIdleDetector,
    IdleStatus,
    OpportunisticTrainer,
)


def _get_expert_record(state: dict, expert_id: int) -> dict:
    return next(
        item for item in state["experts"] if int(item["expert_id"]) == int(expert_id)
    )


class _FixedIdleDetector:
    def __init__(self, status: IdleStatus) -> None:
        self._status = status

    def sample(self) -> IdleStatus:
        return self._status

    def is_idle(self) -> bool:
        return self._status.is_idle


class _EmptyQueue:
    def __init__(self, experts: list[dict[str, object]]) -> None:
        self._state = {"experts": experts}

    def claim_next_expert(self, _worker_id: str, *, claim_timeout_seconds: float):
        del claim_timeout_seconds
        return None

    def load_status(self) -> dict[str, object]:
        return self._state


class _RecordingReflectionEngine:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def idle_reflection(self, fields, *, idle_seconds=None):
        payload = {
            "fields": list(fields),
            "idle_seconds": idle_seconds,
        }
        self.calls.append(payload)
        return {
            "triggered": True,
            "rate_limited": False,
            "reason": "reflected",
            "requested_fields": list(fields),
            "checked_fields": list(fields),
            "reflected_fields": ["auth"],
            "invented_method_ids": ["auth_device_flow_dead"],
            "idle_seconds": idle_seconds,
            "idle_threshold": 300.0,
            "seconds_until_next": 300.0,
        }


def _build_idle_status(*, is_idle: bool) -> IdleStatus:
    return IdleStatus(
        idle_seconds=120 if is_idle else 10,
        idle_method="test",
        cpu_percent=5.0 if is_idle else 75.0,
        power_connected=True,
        is_idle=is_idle,
        reason="ready" if is_idle else "busy",
        checked_at_epoch=time.time(),
        idle_seconds_threshold=60.0,
        cpu_percent_threshold=25.0,
    )


def test_device_idle_detector_is_idle_without_psutil(monkeypatch):
    import scripts.opportunistic_trainer as trainer_mod

    monkeypatch.setattr(trainer_mod, "get_idle_info", lambda: (120, "windows"))
    monkeypatch.setattr(trainer_mod, "is_power_connected", lambda: True)
    monkeypatch.setattr(trainer_mod, "psutil", None)

    detector = DeviceIdleDetector(
        idle_seconds_threshold=60.0,
        cpu_percent_threshold=15.0,
    )
    status = detector.get_status()

    assert status.is_idle is True
    assert status.idle_seconds == 120
    assert status.cpu_percent is None
    assert "cpu" in status.reason.lower()


def test_opportunistic_trainer_claims_trains_and_releases(tmp_path):
    status_path = tmp_path / "experts_status.json"
    initialize_status_file(status_path)

    def fake_train(expert_id: int, field_name: str):
        return SimpleNamespace(
            status="COMPLETED",
            val_f1=0.91,
            val_precision=0.92,
            val_recall=0.93,
            checkpoint_path=f"checkpoints/{expert_id}_{field_name}.safetensors",
        )

    trainer = OpportunisticTrainer(
        "worker-success",
        status_path=status_path,
        idle_detector=_FixedIdleDetector(_build_idle_status(is_idle=True)),
        train_expert_fn=fake_train,
        preferred_device="cpu",
        mixed_precision="fp32",
        poll_interval_seconds=0.0,
        error_backoff_seconds=0.0,
    )

    result = trainer.run_once()

    assert result["action"] == "trained"
    assert result["status"] == "COMPLETED"
    assert result["expert_id"] == 0

    state = load_status(status_path)
    record = _get_expert_record(state, 0)
    assert record["status"] == "COMPLETED"
    assert record["checkpoint_path"].endswith(
        f"{result['expert_id']}_{result['field_name']}.safetensors"
    )
    assert float(record["val_f1"]) == 0.91


def test_opportunistic_trainer_releases_failed_claim_on_exception(tmp_path):
    status_path = tmp_path / "experts_status.json"
    initialize_status_file(status_path)

    def fake_train(_expert_id: int, _field_name: str):
        raise RuntimeError("boom")

    trainer = OpportunisticTrainer(
        "worker-failure",
        status_path=status_path,
        idle_detector=_FixedIdleDetector(_build_idle_status(is_idle=True)),
        train_expert_fn=fake_train,
        preferred_device="cpu",
        mixed_precision="fp32",
        poll_interval_seconds=0.0,
        error_backoff_seconds=0.0,
    )

    result = trainer.run_once()

    assert result["action"] == "error"
    assert result["status"] == "FAILED"
    assert result["expert_id"] == 0
    assert "RuntimeError: boom" in result["error"]

    state = load_status(status_path)
    record = _get_expert_record(state, 0)
    assert record["status"] == "FAILED"
    assert "RuntimeError: boom" in record["last_error"]


def test_opportunistic_trainer_runs_idle_self_reflection_when_queue_empty(tmp_path):
    status_path = tmp_path / "experts_status.json"
    initialize_status_file(status_path)

    reflection_engine = _RecordingReflectionEngine()
    queue = _EmptyQueue(
        [
            {"expert_id": 0, "field_name": "web_vulns"},
            {"expert_id": 1, "field_name": "api_testing"},
            {"expert_id": 2, "field_name": "auth_bypass"},
        ]
    )
    idle_status = IdleStatus(
        idle_seconds=600,
        idle_method="test",
        cpu_percent=5.0,
        power_connected=True,
        is_idle=True,
        reason="ready",
        checked_at_epoch=time.time(),
        idle_seconds_threshold=60.0,
        cpu_percent_threshold=25.0,
    )

    trainer = OpportunisticTrainer(
        "worker-reflection",
        status_path=status_path,
        idle_detector=_FixedIdleDetector(idle_status),
        queue=queue,
        self_reflection_engine=reflection_engine,
        preferred_device="cpu",
        mixed_precision="fp32",
        poll_interval_seconds=0.0,
        error_backoff_seconds=0.0,
    )

    result = trainer.run_once()

    assert result["action"] == "queue_empty"
    assert result["status"] == "SKIPPED"
    assert result["idle_reflection"]["fields"] == [
        "web_vulns",
        "api_testing",
        "auth_bypass",
    ]
    assert result["idle_reflection"]["reason"] == "reflected"
    assert reflection_engine.calls == [
        {
            "fields": ["web_vulns", "api_testing", "auth_bypass"],
            "idle_seconds": 600,
        }
    ]
