import asyncio
import json
import logging
import threading
import time
from pathlib import Path
from unittest.mock import MagicMock

import pytest


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


def test_resolve_hdd_root_raises_when_all_tiers_unavailable(monkeypatch):
    from backend.storage import tiered_storage as ts

    monkeypatch.setattr(ts, "_path_is_usable", lambda path: (False, "Unavailable"))

    with pytest.raises(ts.StorageCompletelyUnavailableError, match="No storage backend available\."):
        ts.resolve_hdd_root()


def test_init_dirs_logs_tier_availability(monkeypatch, caplog, tmp_path):
    from backend.storage import tiered_storage as ts

    ssd_root = tmp_path / "ssd"
    primary_root = tmp_path / "primary"
    fallback_root = tmp_path / "fallback"
    monkeypatch.setattr(ts, "SSD_ROOT", ssd_root)
    monkeypatch.setattr(ts, "PRIMARY_HDD_ROOT", primary_root)
    monkeypatch.setattr(ts, "FALLBACK_HDD_ROOT", fallback_root)
    monkeypatch.setattr(ts, "SSD_TRAINING_DIR", ssd_root / "training")
    monkeypatch.setattr(ts, "SSD_CHECKPOINTS", ssd_root / "checkpoints")
    monkeypatch.setattr(ts, "SSD_DATASETS", ssd_root / "datasets")
    monkeypatch.setattr(ts, "SSD_DB", ssd_root / "ygb.db")
    monkeypatch.setattr(ts, "STORAGE_WAL_PATH", ssd_root / ".wal.jsonl")

    def _fake_usable(path):
        if path == primary_root:
            return False, "PrimaryOffline"
        return True, "ok"

    monkeypatch.setattr(ts, "_path_is_usable", _fake_usable)

    with caplog.at_level(logging.INFO):
        ts._init_dirs()

    assert any(
        record.levelno == logging.INFO and "Storage tier availability" in record.message
        for record in caplog.records
    )


def test_storage_health_reports_fallback_truthfully(monkeypatch):
    from backend.storage import storage_bridge as sb

    original_engine = sb._engine
    original_lifecycle = sb._lifecycle
    original_dm = sb._disk_monitor
    try:
        mock_engine = MagicMock()
        mock_root = Path("C:/ygb_hdd_fallback")
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



def test_init_storage_creates_resolved_root_before_engine_boot(monkeypatch, tmp_path):
    from backend.storage import storage_bridge as sb

    storage_root = tmp_path / "missing-storage-root"
    fallback_root = tmp_path / "fallback-root"

    class _FakeEngine:
        def __init__(self, root: Path):
            self.root = root

    class _FakeLifecycleManager:
        def __init__(self, engine):
            self.engine = engine

        def start_sweep_thread(self):
            return None

    class _FakeDiskMonitor:
        def __init__(self, engine):
            self.engine = engine

        def start(self):
            return None

    original_engine = sb._engine
    original_lifecycle = sb._lifecycle
    original_dm = sb._disk_monitor
    original_video_streamer = sb._video_streamer
    original_active_root = sb._storage_active_root
    original_storage_mode = sb._storage_mode
    try:
        monkeypatch.setattr(
            sb,
            "resolve_hdd_root",
            lambda: (
                storage_root,
                {
                    "primary_root": str(storage_root),
                    "fallback_root": str(fallback_root),
                    "active_root": str(storage_root),
                    "primary_available": True,
                    "fallback_available": True,
                    "fallback_active": False,
                    "mode": "PRIMARY",
                    "reason": "primary root active",
                },
            ),
        )
        monkeypatch.setattr(sb, "LifecycleManager", _FakeLifecycleManager)
        monkeypatch.setattr(sb, "DiskMonitor", _FakeDiskMonitor)
        monkeypatch.setattr(sb, "VideoStreamer", lambda root: {"root": root})

        def _fake_get_engine(root: str):
            assert Path(root).exists()
            assert Path(root).is_dir()
            return _FakeEngine(Path(root))

        monkeypatch.setattr(sb, "get_engine", _fake_get_engine)

        result = sb.init_storage()

        assert storage_root.exists()
        assert storage_root.is_dir()
        assert result["status"] == "initialized"
        assert result["hdd_root"] == str(storage_root)
    finally:
        sb._engine = original_engine
        sb._lifecycle = original_lifecycle
        sb._disk_monitor = original_dm
        sb._video_streamer = original_video_streamer
        sb._storage_active_root = original_active_root
        sb._storage_mode = original_storage_mode



def test_storage_health_uses_actual_filesystem_state_for_root(monkeypatch, tmp_path):
    from backend.storage import storage_bridge as sb

    original_engine = sb._engine
    original_lifecycle = sb._lifecycle
    original_dm = sb._disk_monitor
    try:
        missing_root = tmp_path / "missing-root"
        sb._engine = type("Engine", (), {"root": missing_root})()
        sb._lifecycle = MagicMock()
        sb._disk_monitor = MagicMock()
        monkeypatch.setattr(
            sb,
            "get_storage_topology",
            lambda: {
                "primary_root": str(missing_root),
                "fallback_root": str(tmp_path / "fallback"),
                "active_root": str(missing_root),
                "primary_available": True,
                "fallback_available": True,
                "fallback_active": False,
                "mode": "PRIMARY",
                "reason": "primary root active",
            },
        )

        result = sb.get_storage_health()

        assert result["storage_active"] is False
        assert result["db_active"] is False
        assert result["status"] == "INACTIVE"
        assert "Storage root missing or inaccessible" in result["reason"]
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


def test_storage_health_degrades_when_disk_monitor_missing(monkeypatch, tmp_path):
    from backend.storage import storage_bridge as sb

    original_engine = sb._engine
    original_lifecycle = sb._lifecycle
    original_dm = sb._disk_monitor
    try:
        mock_engine = MagicMock()
        mock_root = tmp_path / "primary-root"
        mock_root.mkdir(parents=True, exist_ok=True)
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


def test_get_tier_health_returns_expected_shape(monkeypatch, tmp_path):
    from backend.storage import tiered_storage as ts

    monkeypatch.setattr(ts, "SSD_ROOT", tmp_path / "ssd")
    monkeypatch.setattr(ts, "PRIMARY_HDD_ROOT", tmp_path / "primary")
    monkeypatch.setattr(ts, "FALLBACK_HDD_ROOT", tmp_path / "fallback")
    monkeypatch.setattr(ts, "STORAGE_WAL_PATH", tmp_path / "ssd" / ".wal.jsonl")

    health = ts.get_tier_health()

    assert [entry.tier_name for entry in health] == [
        "ssd",
        "primary_hdd",
        "fallback_hdd",
    ]
    for entry in health:
        assert isinstance(entry, ts.StorageTierHealth)
        assert entry.available_bytes >= 0
        assert entry.used_bytes >= 0
        assert isinstance(entry.read_latency_ms, float)
        assert isinstance(entry.write_latency_ms, float)


def test_event_based_stop_signal_terminates_keepalive_wait(monkeypatch):
    from backend.storage import tiered_storage as ts

    stop_event = threading.Event()
    monkeypatch.setattr(ts, "_enforcement_stop_event", stop_event)

    def _signal_stop() -> None:
        time.sleep(0.05)
        stop_event.set()

    threading.Thread(target=_signal_stop, daemon=True).start()
    started_at = time.perf_counter()
    asyncio.run(ts._wait_for_stop_signal())

    assert time.perf_counter() - started_at < 1.0


def test_wal_replay_on_startup(monkeypatch, tmp_path):
    from backend.storage import tiered_storage as ts

    ssd_root = tmp_path / "ssd"
    primary_root = tmp_path / "primary"
    fallback_root = tmp_path / "fallback"
    wal_path = ssd_root / ".wal.jsonl"
    recovered_dir = tmp_path / "recovered-dir"

    monkeypatch.setattr(ts, "SSD_ROOT", ssd_root)
    monkeypatch.setattr(ts, "PRIMARY_HDD_ROOT", primary_root)
    monkeypatch.setattr(ts, "FALLBACK_HDD_ROOT", fallback_root)
    monkeypatch.setattr(ts, "SSD_TRAINING_DIR", ssd_root / "training")
    monkeypatch.setattr(ts, "SSD_CHECKPOINTS", ssd_root / "checkpoints")
    monkeypatch.setattr(ts, "SSD_DATASETS", ssd_root / "datasets")
    monkeypatch.setattr(ts, "SSD_DB", ssd_root / "ygb.db")
    monkeypatch.setattr(ts, "STORAGE_WAL_PATH", wal_path)

    wal_path.parent.mkdir(parents=True, exist_ok=True)
    wal_path.write_text(
        json.dumps(
            {
                "timestamp": "2026-01-01T00:00:00",
                "op": "ensure_dir",
                "key": str(recovered_dir),
            }
        )
        + "\n",
        encoding="utf-8",
    )

    ts._init_dirs()

    assert recovered_dir.exists()
    assert not wal_path.exists()


def test_storage_bridge_read_failure_falls_back_to_next_tier(monkeypatch, caplog, tmp_path):
    from backend.storage import storage_bridge as sb

    class _PrimaryEngine:
        def __init__(self, root: Path):
            self.root = root

        def read_entity(self, entity_type: str, entity_id: str):
            raise OSError("primary tier unavailable")

    class _FallbackEngine:
        def __init__(self, root: Path):
            self.root = root

        def read_entity(self, entity_type: str, entity_id: str):
            return {
                "latest": {
                    "name": "Fallback User",
                    "email": "fallback@example.com",
                    "role": "hunter",
                    "created_at": "2026-01-01T00:00:00Z",
                    "last_active": "2026-01-01T00:00:00Z",
                }
            }

    original_engine = sb._engine
    original_audit_log = sb._audit_log
    original_active_root = sb._storage_active_root
    try:
        primary_root = tmp_path / "primary"
        fallback_root = tmp_path / "fallback"
        primary_root.mkdir(parents=True, exist_ok=True)
        fallback_root.mkdir(parents=True, exist_ok=True)
        sb._audit_log = sb.BridgeAuditLog()
        sb._engine = sb._wrap_engine(_PrimaryEngine(primary_root))
        sb._storage_active_root = str(primary_root)
        monkeypatch.setattr(
            sb,
            "get_storage_topology",
            lambda: {
                "primary_root": str(primary_root),
                "fallback_root": str(fallback_root),
                "active_root": str(primary_root),
                "primary_available": True,
                "fallback_available": True,
                "fallback_active": False,
                "mode": "PRIMARY",
                "reason": "primary active",
            },
        )
        monkeypatch.setattr(
            sb,
            "_get_read_engine_for_root",
            lambda root: _FallbackEngine(Path(root)),
        )

        with caplog.at_level(logging.WARNING):
            user = sb.get_user("user-1")

        assert user is not None
        assert user["name"] == "Fallback User"
        assert "Storage read failed on tier PRIMARY" in caplog.text
        audit = sb.get_audit_log()
        assert len(audit) == 2
        assert audit[0].tier == "PRIMARY"
        assert audit[0].result.startswith("error:")
        assert audit[1].tier == "FALLBACK"
        assert audit[1].result == "ok"
    finally:
        with sb._READ_ENGINE_CACHE_LOCK:
            sb._READ_ENGINE_CACHE.clear()
        sb._engine = original_engine
        sb._audit_log = original_audit_log
        sb._storage_active_root = original_active_root


def test_storage_bridge_audit_entries_are_created(monkeypatch, tmp_path):
    from backend.storage import storage_bridge as sb

    class _MemoryEngine:
        def __init__(self, root: Path):
            self.root = root
            self._entities = {}

        def create_entity(self, entity_type: str, entity_id: str, data):
            self._entities[(entity_type, entity_id)] = {"latest": dict(data)}
            return dict(data)

        def read_entity(self, entity_type: str, entity_id: str):
            return self._entities.get((entity_type, entity_id))

    original_engine = sb._engine
    original_audit_log = sb._audit_log
    original_email_index = dict(sb._EMAIL_INDEX)
    original_email_built = sb._EMAIL_INDEX_BUILT
    original_active_root = sb._storage_active_root
    try:
        storage_root = tmp_path / "storage"
        fallback_root = tmp_path / "fallback"
        storage_root.mkdir(parents=True, exist_ok=True)
        fallback_root.mkdir(parents=True, exist_ok=True)
        sb._audit_log = sb.BridgeAuditLog()
        sb._engine = sb._wrap_engine(_MemoryEngine(storage_root))
        sb._EMAIL_INDEX = {}
        sb._EMAIL_INDEX_BUILT = False
        sb._storage_active_root = str(storage_root)
        monkeypatch.setattr(
            sb,
            "get_storage_topology",
            lambda: {
                "primary_root": str(storage_root),
                "fallback_root": str(fallback_root),
                "active_root": str(storage_root),
                "primary_available": True,
                "fallback_available": True,
                "fallback_active": False,
                "mode": "PRIMARY",
                "reason": "primary active",
            },
        )

        created = sb.create_user("Alice", "alice@example.com")
        fetched = sb.get_user(created["id"])
        audit = sb.get_audit_log()

        assert fetched is not None
        assert fetched["email"] == "alice@example.com"
        assert [entry.op for entry in audit] == ["CREATE", "READ"]
        assert all(entry.latency_ms >= 0 for entry in audit)
    finally:
        sb._engine = original_engine
        sb._audit_log = original_audit_log
        sb._EMAIL_INDEX = original_email_index
        sb._EMAIL_INDEX_BUILT = original_email_built
        sb._storage_active_root = original_active_root


def test_storage_bridge_audit_log_rotates_at_ten_thousand():
    from backend.storage import storage_bridge as sb

    audit_log = sb.BridgeAuditLog()
    for idx in range(10001):
        audit_log.append(
            sb.BridgeAuditEntry(
                timestamp=f"2026-01-01T00:00:{idx:02d}Z",
                op="READ",
                tier="PRIMARY",
                key=f"users/{idx}",
                result="ok",
                latency_ms=1.0,
            )
        )

    entries = audit_log.get_entries()
    assert len(entries) == 5000
    assert entries[0].key == "users/5001"
    assert entries[-1].key == "users/10000"
