"""
Tests for Database Persistence

Verifies:
- SQLite database creates file on disk
- CRUD operations work correctly
- Data persists across reconnection
- No in-memory-only storage
"""

import sys
import os
import pytest
import asyncio
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "api"))


@pytest.fixture
def temp_db(tmp_path):
    """Set up a temporary database for testing."""
    db_path = str(tmp_path / "test_ygb.db")
    os.environ["DATABASE_URL"] = f"sqlite:///{db_path}"
    return db_path


@pytest.fixture
def reset_db_module():
    """Reset the database module state between tests."""
    import api.database as db_mod
    original_db = db_mod._db
    db_mod._db = None
    yield db_mod
    db_mod._db = None


@pytest.mark.asyncio
async def test_database_creates_file(temp_db, reset_db_module):
    """Database file must be created on disk after init."""
    db = reset_db_module
    # Patch the path
    db.DB_PATH = temp_db
    db._db = None

    await db.init_database()

    assert Path(temp_db).exists(), "Database file not created on disk!"
    await db.close_pool()


@pytest.mark.asyncio
async def test_create_and_get_user(temp_db, reset_db_module):
    """Create a user and fetch it back."""
    db = reset_db_module
    db.DB_PATH = temp_db
    db._db = None

    await db.init_database()

    user = await db.create_user("TestUser", "test@example.com", "hunter")
    assert user["name"] == "TestUser"
    assert user["email"] == "test@example.com"
    assert user["id"] is not None

    fetched = await db.get_user(user["id"])
    assert fetched is not None
    assert fetched["name"] == "TestUser"

    await db.close_pool()


@pytest.mark.asyncio
async def test_data_persists_after_reconnect(temp_db, reset_db_module):
    """Data must survive closing and reopening the connection."""
    db = reset_db_module
    db.DB_PATH = temp_db
    db._db = None

    await db.init_database()

    user = await db.create_user("PersistUser", "persist@test.com")
    user_id = user["id"]
    await db.close_pool()

    # Reopen
    db._db = None
    await db.init_database()

    fetched = await db.get_user(user_id)
    assert fetched is not None
    assert fetched["name"] == "PersistUser"

    await db.close_pool()


@pytest.mark.asyncio
async def test_create_target(temp_db, reset_db_module):
    """Create a target and list all targets."""
    db = reset_db_module
    db.DB_PATH = temp_db
    db._db = None

    await db.init_database()

    target = await db.create_target("TestProgram", "*.test.com")
    assert target["program_name"] == "TestProgram"

    all_targets = await db.get_all_targets()
    assert len(all_targets) >= 1

    await db.close_pool()


@pytest.mark.asyncio
async def test_create_bounty(temp_db, reset_db_module):
    """Create a bounty linked to a user."""
    db = reset_db_module
    db.DB_PATH = temp_db
    db._db = None

    await db.init_database()

    user = await db.create_user("BountyHunter")
    bounty = await db.create_bounty(user["id"], title="XSS Found", severity="high")
    assert bounty["title"] == "XSS Found"
    assert bounty["severity"] == "high"

    user_bounties = await db.get_user_bounties(user["id"])
    assert len(user_bounties) == 1

    await db.close_pool()


@pytest.mark.asyncio
async def test_session_crud(temp_db, reset_db_module):
    """Create, get, and end sessions."""
    db = reset_db_module
    db.DB_PATH = temp_db
    db._db = None

    await db.init_database()

    user = await db.create_user("SessionUser")
    session = await db.create_session(
        user["id"], "READ_ONLY", "*.test.com",
        ip_address="192.168.1.1", user_agent="TestAgent"
    )
    assert session["status"] == "active"
    assert session["ip_address"] == "192.168.1.1"

    sessions = await db.get_user_sessions(user["id"])
    assert len(sessions) == 1

    await db.end_session(session["id"])
    sessions = await db.get_user_sessions(user["id"])
    assert sessions[0]["status"] == "ended"

    await db.close_pool()


@pytest.mark.asyncio
async def test_device_registration(temp_db, reset_db_module):
    """Register a device, re-register updates last_seen."""
    db = reset_db_module
    db.DB_PATH = temp_db
    db._db = None

    await db.init_database()

    user = await db.create_user("DeviceUser")
    device = await db.register_device(
        user["id"], "abc123hash", "10.0.0.1", "Chrome/120"
    )
    assert device["is_new"] is True

    # Re-register same device
    device2 = await db.register_device(
        user["id"], "abc123hash", "10.0.0.2", "Chrome/120"
    )
    assert device2["is_new"] is False

    devices = await db.get_user_devices(user["id"])
    assert len(devices) == 1  # Same device, not duplicated

    await db.close_pool()


@pytest.mark.asyncio
async def test_audit_log(temp_db, reset_db_module):
    """Activity logging works and is retrievable."""
    db = reset_db_module
    db.DB_PATH = temp_db
    db._db = None

    await db.init_database()

    await db.log_activity(None, "TEST_ACTION", "Test description")
    activity = await db.get_recent_activity(10)
    assert len(activity) >= 1
    assert activity[0]["action_type"] == "TEST_ACTION"

    await db.close_pool()


@pytest.mark.asyncio
async def test_admin_stats(temp_db, reset_db_module):
    """Admin stats returns real counts from DB."""
    db = reset_db_module
    db.DB_PATH = temp_db
    db._db = None

    await db.init_database()

    await db.create_user("StatsUser")
    await db.create_target("StatsTarget")

    stats = await db.get_admin_stats()
    assert stats["total_users"] >= 1
    assert stats["total_targets"] >= 1

    await db.close_pool()


@pytest.mark.asyncio
async def test_no_in_memory_only_storage(temp_db, reset_db_module):
    """Database must NOT use in-memory-only storage."""
    db = reset_db_module
    db.DB_PATH = temp_db
    db._db = None

    # Check that DB_PATH is not :memory:
    assert ":memory:" not in db.DB_PATH, "Database must not be in-memory only!"

    await db.init_database()
    assert Path(temp_db).stat().st_size > 0, "Database file must not be empty!"

    await db.close_pool()
