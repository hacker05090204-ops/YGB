from unittest.mock import MagicMock


def test_resolve_hdd_root_falls_back_to_c_drive(monkeypatch):
    from backend.storage import tiered_storage as ts

    def _fake_usable(path):
        raw = str(path)
        if raw == str(ts.PRIMARY_HDD_ROOT):
            return False, "DriveNotFound"
        return True, "ok"

    monkeypatch.setattr(ts, "_path_is_usable", _fake_usable)
    active, topology = ts.resolve_hdd_root()

    assert str(active) == str(ts.FALLBACK_HDD_ROOT)
    assert topology["fallback_active"] is True
    assert topology["primary_available"] is False


def test_storage_health_reports_fallback_truthfully(monkeypatch):
    from backend.storage import storage_bridge as sb

    original_engine = sb._engine
    original_lifecycle = sb._lifecycle
    original_dm = sb._disk_monitor
    try:
        mock_engine = MagicMock()
        mock_root = MagicMock()
        mock_root.exists.return_value = True
        mock_engine.root = mock_root

        sb._engine = mock_engine
        sb._lifecycle = MagicMock()
        sb._disk_monitor = MagicMock()
        monkeypatch.setattr(
            sb,
            "get_storage_topology",
            lambda: {
                "primary_root": "D:/ygb_hdd",
                "fallback_root": "C:/ygb_hdd_fallback",
                "active_root": "C:/ygb_hdd_fallback",
                "primary_available": False,
                "fallback_available": True,
                "fallback_active": True,
                "mode": "FALLBACK",
                "reason": "Primary root unavailable",
            },
        )

        result = sb.get_storage_health()

        assert result["status"] == "DEGRADED"
        assert result["fallback_active"] is True
        assert result["storage_mode"] == "FALLBACK"
    finally:
        sb._engine = original_engine
        sb._lifecycle = original_lifecycle
        sb._disk_monitor = original_dm
