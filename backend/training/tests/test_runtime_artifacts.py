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

    result = artifacts.ensure_local_mode_a_bootstrap()

    assert result["mode"] == "single_node_local"
    assert (config_dir / "device_identity.json").exists()
    assert (config_dir / "cluster_role.json").exists()
    assert (config_dir / "devices.json").exists()
    assert (reports_dir / "pairing_log.json").exists()
    assert (reports_dir / "cluster_health.json").exists()


def test_training_telemetry_validates(tmp_path, monkeypatch):
    telemetry_path = tmp_path / "training_telemetry.json"
    last_seen_path = tmp_path / "last_seen_timestamp.json"

    monkeypatch.setattr(artifacts, "TRAINING_TELEMETRY_PATH", str(telemetry_path))
    monkeypatch.setattr(runtime_api, "TELEMETRY_PATH", str(telemetry_path))
    monkeypatch.setattr(runtime_api, "LAST_SEEN_PATH", str(last_seen_path))

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
