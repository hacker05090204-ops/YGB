"""
Tests for runtime artifact persistence.
"""

import json
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import backend.api.runtime_api as runtime_api
import backend.training.runtime_artifacts as artifacts


def test_local_bootstrap_creates_expected_files(tmp_path, monkeypatch):
    config_dir = tmp_path / "config"
    reports_dir = tmp_path / "reports"
    data_dir = tmp_path / "data"

    monkeypatch.setattr(artifacts, "CONFIG_DIR", str(config_dir))
    monkeypatch.setattr(artifacts, "REPORTS_DIR", str(reports_dir))
    monkeypatch.setattr(artifacts, "DATA_DIR", str(data_dir))
    monkeypatch.setattr(artifacts, "DEVICE_IDENTITY_PATH", str(config_dir / "device_identity.json"))
    monkeypatch.setattr(artifacts, "CLUSTER_ROLE_PATH", str(config_dir / "cluster_role.json"))
    monkeypatch.setattr(artifacts, "DEVICES_PATH", str(config_dir / "devices.json"))
    monkeypatch.setattr(artifacts, "WG_KEY_STATE_PATH", str(config_dir / "wg_key_state.json"))
    monkeypatch.setattr(artifacts, "PAIRING_LOG_PATH", str(reports_dir / "pairing_log.json"))
    monkeypatch.setattr(artifacts, "CLUSTER_HEALTH_PATH", str(reports_dir / "cluster_health.json"))
    monkeypatch.setattr(artifacts, "TRAINING_GATE_PATH", str(reports_dir / "training_gate.json"))
    monkeypatch.setattr(artifacts, "TRAINING_TELEMETRY_PATH", str(reports_dir / "training_telemetry.json"))
    monkeypatch.setattr(artifacts, "RUNTIME_STATE_PATH", str(reports_dir / "runtime_state.json"))
    monkeypatch.setattr(artifacts, "FIELD_RUNTIME_STATUS_PATH", str(data_dir / "runtime_status.json"))
    monkeypatch.setenv("YGB_HMAC_SECRET", "ab" * 32)

    result = artifacts.bootstrap_runtime_artifacts(force_refresh=True)

    assert result["bootstrap"]["mode"] == "single_node_local"
    assert (config_dir / "device_identity.json").exists()
    assert (config_dir / "cluster_role.json").exists()
    assert (config_dir / "devices.json").exists()
    assert (reports_dir / "pairing_log.json").exists()
    assert (reports_dir / "cluster_health.json").exists()
    assert (reports_dir / "training_gate.json").exists()
    assert (reports_dir / "training_telemetry.json").exists()
    assert (reports_dir / "runtime_state.json").exists()
    assert (data_dir / "runtime_status.json").exists()


def test_training_telemetry_validates(tmp_path, monkeypatch):
    telemetry_path = tmp_path / "training_telemetry.json"
    last_seen_path = tmp_path / "last_seen_timestamp.json"

    monkeypatch.setattr(artifacts, "TRAINING_TELEMETRY_PATH", str(telemetry_path))
    monkeypatch.setattr(runtime_api, "TELEMETRY_PATH", str(telemetry_path))
    monkeypatch.setattr(runtime_api, "LAST_SEEN_PATH", str(last_seen_path))
    monkeypatch.setenv("YGB_HMAC_SECRET", "cd" * 32)

    if telemetry_path.exists():
        telemetry_path.unlink()
    if last_seen_path.exists():
        last_seen_path.unlink()

    payload = artifacts.write_training_telemetry(
        epoch=3,
        batch_size=128,
        loss=0.1234,
        precision=0.9789,
        total_epochs=12,
        training_duration_seconds=17.5,
        samples_per_second=256.4,
        determinism_status=True,
        freeze_status=False,
        gpu_temperature=72.0,
        cpu_util=42.0,
        gpu_util=81.0,
    )

    assert payload["epoch"] == 3
    assert telemetry_path.exists()

    result = runtime_api.validate_telemetry()
    assert result["status"] == "ok"
    assert result["data"]["epoch"] == 3
    assert abs(result["data"]["precision"] - 0.9789) < 0.0001


def test_idle_artifact_repair_refreshes_stale_files(tmp_path, monkeypatch):
    config_dir = tmp_path / "config"
    reports_dir = tmp_path / "reports"
    data_dir = tmp_path / "data"

    monkeypatch.setattr(artifacts, "CONFIG_DIR", str(config_dir))
    monkeypatch.setattr(artifacts, "REPORTS_DIR", str(reports_dir))
    monkeypatch.setattr(artifacts, "DATA_DIR", str(data_dir))
    monkeypatch.setattr(artifacts, "DEVICE_IDENTITY_PATH", str(config_dir / "device_identity.json"))
    monkeypatch.setattr(artifacts, "CLUSTER_ROLE_PATH", str(config_dir / "cluster_role.json"))
    monkeypatch.setattr(artifacts, "DEVICES_PATH", str(config_dir / "devices.json"))
    monkeypatch.setattr(artifacts, "WG_KEY_STATE_PATH", str(config_dir / "wg_key_state.json"))
    monkeypatch.setattr(artifacts, "PAIRING_LOG_PATH", str(reports_dir / "pairing_log.json"))
    monkeypatch.setattr(artifacts, "CLUSTER_HEALTH_PATH", str(reports_dir / "cluster_health.json"))
    monkeypatch.setattr(artifacts, "TRAINING_GATE_PATH", str(reports_dir / "training_gate.json"))
    monkeypatch.setattr(artifacts, "TRAINING_TELEMETRY_PATH", str(reports_dir / "training_telemetry.json"))
    monkeypatch.setattr(artifacts, "RUNTIME_STATE_PATH", str(reports_dir / "runtime_state.json"))
    monkeypatch.setattr(artifacts, "FIELD_RUNTIME_STATUS_PATH", str(data_dir / "runtime_status.json"))
    monkeypatch.setenv("YGB_HMAC_SECRET", "ef" * 32)

    artifacts.bootstrap_runtime_artifacts(force_refresh=True)

    stale_epoch = 7
    artifacts.write_training_telemetry(
        epoch=stale_epoch,
        batch_size=64,
        loss=0.25,
        precision=0.5,
        total_epochs=10,
        training_duration_seconds=12.0,
        samples_per_second=20.0,
        determinism_status=True,
        freeze_status=False,
        gpu_temperature=55.0,
        cpu_util=10.0,
        gpu_util=15.0,
    )
    os.utime(artifacts.TRAINING_TELEMETRY_PATH, (0, 0))
    os.utime(artifacts.RUNTIME_STATE_PATH, (0, 0))

    result = artifacts.repair_runtime_artifacts_if_needed(
        training_active=False,
        idle_max_age_seconds=1,
    )

    assert result["repaired"] is True
    assert "training_telemetry_idle_stale" in result["issues"]
    refreshed = json.loads(Path(artifacts.TRAINING_TELEMETRY_PATH).read_text(encoding="utf-8"))
    assert refreshed["epoch"] == 0


def test_idle_artifact_repair_does_not_override_active_training(tmp_path, monkeypatch):
    reports_dir = tmp_path / "reports"
    telemetry_path = reports_dir / "training_telemetry.json"
    runtime_path = reports_dir / "runtime_state.json"
    reports_dir.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(artifacts, "TRAINING_TELEMETRY_PATH", str(telemetry_path))
    monkeypatch.setattr(artifacts, "RUNTIME_STATE_PATH", str(runtime_path))
    monkeypatch.setenv("YGB_HMAC_SECRET", "12" * 32)

    payload = artifacts.write_training_telemetry(
        epoch=9,
        batch_size=64,
        loss=0.15,
        precision=0.85,
        total_epochs=20,
        training_duration_seconds=30.0,
        samples_per_second=40.0,
        determinism_status=True,
        freeze_status=False,
        gpu_temperature=60.0,
        cpu_util=15.0,
        gpu_util=25.0,
    )
    os.utime(artifacts.TRAINING_TELEMETRY_PATH, (0, 0))

    result = artifacts.repair_runtime_artifacts_if_needed(
        training_active=True,
        idle_max_age_seconds=1,
    )

    assert result["repaired"] is False
    preserved = json.loads(Path(artifacts.TRAINING_TELEMETRY_PATH).read_text(encoding="utf-8"))
    assert preserved["epoch"] == payload["epoch"]
