# test_g21_auto_update.py
"""Tests for G21 auto-update infrastructure gating."""

import inspect

import pytest

from impl_v1.phase49.governors.g21_auto_update import (
    AUTO_UPDATE_PROVISIONING_MESSAGE,
    AutoUpdater,
    RealBackendNotConfiguredError,
    UpdateContract,
    can_auto_update_execute,
    can_update_prevent_rollback,
    can_update_skip_signature,
    check_for_updates,
)


class TestUpdateContract:
    """Tests for the real update payload contract."""

    def test_contract_shape(self):
        update = UpdateContract(
            update_id="UPD-123",
            version="2.0.0",
            signature="a" * 64,
            download_url="https://updates.example.com/2.0.0",
            checksum_sha256="b" * 64,
        )
        assert update.update_id == "UPD-123"
        assert update.version == "2.0.0"
        assert update.signature == "a" * 64
        assert update.download_url.startswith("https://")
        assert update.checksum_sha256 == "b" * 64


class TestAutoUpdater:
    """Tests for fail-closed update governance."""

    def test_mock_update_parameter_is_absent(self):
        parameters = inspect.signature(check_for_updates).parameters
        assert "_mock_update" not in parameters

    def test_check_for_update_raises_real_backend_not_configured(self):
        updater = AutoUpdater()
        with pytest.raises(RealBackendNotConfiguredError, match=AUTO_UPDATE_PROVISIONING_MESSAGE):
            updater.check_for_update()

    def test_apply_update_raises_real_backend_not_configured(self):
        updater = AutoUpdater()
        update = UpdateContract(
            update_id="UPD-456",
            version="2.0.1",
            signature="c" * 64,
            download_url="https://updates.example.com/2.0.1",
            checksum_sha256="d" * 64,
        )
        with pytest.raises(RealBackendNotConfiguredError, match=AUTO_UPDATE_PROVISIONING_MESSAGE):
            updater.apply_update(update)


class TestCanAutoUpdateExecute:
    """Tests for auto-update execution guard."""

    def test_cannot_auto_execute(self):
        can_exec, reason = can_auto_update_execute()
        assert can_exec is False
        assert "approval" in reason.lower()


class TestCanUpdateSkipSignature:
    """Tests for mandatory signature verification guard."""

    def test_cannot_skip_signature(self):
        can_skip, reason = can_update_skip_signature()
        assert can_skip is False
        assert "signature" in reason.lower()


class TestCanUpdatePreventRollback:
    """Tests for rollback availability guard."""

    def test_cannot_prevent_rollback(self):
        can_prevent, reason = can_update_prevent_rollback()
        assert can_prevent is False
        assert "rollback" in reason.lower()
