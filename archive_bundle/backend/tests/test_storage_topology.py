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


def test_stop_enforcement_loop_stops_running_thread(monkeypatch):
    from backend.storage import tiered_storage as ts

    original_thread = ts._enforcement_thread
    original_stop_event = ts._enforcement_stop_event
    try:
        ts._enforcement_thread = None
        ts._enforcement_stop_event.clear()
        monkeypatch.setattr(ts, "enforce_ssd_cap", lambda: None)
        ts.start_enforcement_loop(interval_seconds=1)
        assert ts._enforcement_thread is not None
        assert ts._enforcement_thread.is_alive()
        ts.stop_enforcement_loop(join_timeout_seconds=1.0)
        assert not ts._enforcement_thread.is_alive()
    finally:
        ts._enforcement_thread = original_thread
        ts._enforcement_stop_event = original_stop_event


def test_storage_health_degrades_when_disk_monitor_missing(monkeypatch):
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
        sb._disk_monitor = None
        monkeypatch.setattr(
            sb,
            "get_storage_topology",
            lambda: {
                "primary_root": "D:/ygb_hdd",
                "fallback_root": "C:/ygb_hdd_fallback",
                "active_root": "D:/ygb_hdd",
                "primary_available": True,
                "fallback_available": True,
                "fallback_active": False,
                "mode": "PRIMARY",
                "reason": "Primary NAS root active",
            },
        )

        result = sb.get_storage_health()

        assert result["status"] == "DEGRADED"
        assert result["disk_monitor_ok"] is False
    finally:
        sb._engine = original_engine
        sb._lifecycle = original_lifecycle
        sb._disk_monitor = original_dm
