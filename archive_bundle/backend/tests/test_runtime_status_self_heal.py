import asyncio
import os
from pathlib import Path

from api import server as server_mod


def _write_placeholder_telemetry(tmp_path: Path) -> Path:
    reports_dir = tmp_path / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    telemetry_path = reports_dir / "training_telemetry.json"
    telemetry_path.write_text("{}", encoding="utf-8")
    os.utime(telemetry_path, (0, 0))
    return telemetry_path


def test_runtime_status_auto_repairs_idle_stale_telemetry(monkeypatch, tmp_path):
    _write_placeholder_telemetry(tmp_path)
    monkeypatch.setattr(server_mod, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(server_mod, "G38_AVAILABLE", False)
    monkeypatch.setattr(
        server_mod,
        "repair_runtime_artifacts_if_needed",
        lambda training_active: {
            "repaired": True,
            "issues": ["training_telemetry_idle_stale"],
        },
    )
    monkeypatch.setattr(
        server_mod,
        "_read_validated_telemetry",
        lambda path: (
            {
                "epoch": 0,
                "total_epochs": 0,
                "loss": 0.0,
                "precision": 0.0,
                "gpu_util": 0.0,
                "cpu_util": 0.0,
                "gpu_temperature": 0.0,
                "determinism_status": True,
                "freeze_status": False,
                "wall_clock_unix": 0,
                "monotonic_start_time": 0,
                "training_duration_seconds": 0.0,
                "hmac": "sig",
            },
            None,
        ),
    )

    result = asyncio.run(server_mod.runtime_status(user={"sub": "user-1"}))

    assert result["status"] == "idle"
    assert result["stale"] is False
    assert result["source"] == "telemetry_file_self_healed"
    assert result["auto_repaired"] is True


def test_runtime_status_keeps_stale_flag_when_training_is_active(monkeypatch, tmp_path):
    _write_placeholder_telemetry(tmp_path)
    monkeypatch.setattr(server_mod, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(server_mod, "G38_AVAILABLE", True)

    class _Trainer:
        def get_status(self):
            return {
                "is_training": True,
                "state": "TRAINING",
                "training_mode": "MANUAL",
                "samples_per_sec": 12.0,
                "dataset_size": 512,
                "events_count": 4,
            }

    monkeypatch.setattr(server_mod, "get_auto_trainer", lambda: _Trainer())
    monkeypatch.setattr(
        server_mod,
        "repair_runtime_artifacts_if_needed",
        lambda training_active: {"repaired": False, "issues": []},
    )
    monkeypatch.setattr(
        server_mod,
        "_read_validated_telemetry",
        lambda path: (
            {
                "epoch": 3,
                "total_epochs": 10,
                "loss": 0.2,
                "precision": 0.8,
                "gpu_util": 20.0,
                "cpu_util": 10.0,
                "gpu_temperature": 40.0,
                "determinism_status": True,
                "freeze_status": False,
                "wall_clock_unix": 1,
                "monotonic_start_time": 1,
                "training_duration_seconds": 5.0,
                "hmac": "sig",
            },
            None,
        ),
    )

    result = asyncio.run(server_mod.runtime_status(user={"sub": "user-1"}))

    assert result["status"] == "active"
    assert result["stale"] is True
    assert result["source"] == "telemetry_file"
