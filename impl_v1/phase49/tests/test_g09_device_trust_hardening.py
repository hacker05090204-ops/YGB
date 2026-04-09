from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

from impl_v1.phase49.governors import g09_device_trust as mod
from impl_v1.phase49.governors.g10_owner_alerts import AlertType, clear_alerts, get_all_alerts


def test_verification_challenge_expires(monkeypatch, tmp_path):
    monkeypatch.setenv("YGB_DEVICE_TRUST_REGISTRY_PATH", str(tmp_path / "registry.json"))
    monkeypatch.setenv("YGB_DEVICE_TRUST_CHALLENGE_PATH", str(tmp_path / "challenges.json"))
    mod.clear_registry()
    clear_alerts()

    mod.register_device("D1", "fp1", "1.1.1.1")
    mod.register_device("D2", "fp2", "1.1.1.2")
    mod.register_device("D3", "fp3", "1.1.1.3")
    _, challenge, password = mod.register_device("D4", "fp4", "1.1.1.4")

    expired = mod.VerificationChallenge(
        challenge_id=challenge.challenge_id,
        device_id=challenge.device_id,
        password_hash=challenge.password_hash,
        expires_at=(datetime.now(UTC) - timedelta(minutes=1)).isoformat(),
        status=mod.VerificationStatus.PENDING,
        attempts=challenge.attempts,
        max_attempts=challenge.max_attempts,
    )
    mod._pending_challenges[challenge.challenge_id] = expired

    success, reason = mod.verify_device(challenge.challenge_id, password)

    assert success is False
    assert "expired" in reason.lower()
    assert mod._pending_challenges[challenge.challenge_id].status == mod.VerificationStatus.FAILED


def test_register_device_persists_registry_and_challenges(monkeypatch, tmp_path):
    registry_path = tmp_path / "registry.json"
    challenge_path = tmp_path / "challenges.json"
    monkeypatch.setenv("YGB_DEVICE_TRUST_REGISTRY_PATH", str(registry_path))
    monkeypatch.setenv("YGB_DEVICE_TRUST_CHALLENGE_PATH", str(challenge_path))
    mod.clear_registry()
    clear_alerts()

    mod.register_device("D1", "fp1", "1.1.1.1")
    mod.register_device("D2", "fp2", "1.1.1.2")
    mod.register_device("D3", "fp3", "1.1.1.3")
    device, challenge, _ = mod.register_device("D4", "fp4", "1.1.1.4")

    registry_payload = json.loads(registry_path.read_text(encoding="utf-8"))
    challenge_payload = json.loads(challenge_path.read_text(encoding="utf-8"))

    assert any(entry["device_id"] == device.device_id for entry in registry_payload["devices"])
    assert any(entry["challenge_id"] == challenge.challenge_id for entry in challenge_payload["challenges"])


def test_verification_required_creates_owner_alert(monkeypatch, tmp_path):
    monkeypatch.setenv("YGB_DEVICE_TRUST_REGISTRY_PATH", str(tmp_path / "registry.json"))
    monkeypatch.setenv("YGB_DEVICE_TRUST_CHALLENGE_PATH", str(tmp_path / "challenges.json"))
    mod.clear_registry()
    clear_alerts()

    mod.register_device("D1", "fp1", "1.1.1.1")
    mod.register_device("D2", "fp2", "1.1.1.2")
    mod.register_device("D3", "fp3", "1.1.1.3")
    device, _, _ = mod.register_device("D4", "fp4", "1.1.1.4")

    alerts = get_all_alerts()

    assert any(
        alert.alert_type == AlertType.DEVICE_LIMIT and alert.device_id == device.device_id
        for alert in alerts
    )
