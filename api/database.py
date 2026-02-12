"""
YGB Database — SQLite on HDD

Production-grade persistent storage using aiosqlite.
Replaces the old JSON-file based database.

Models: users, sessions, devices, training_runs, audit_log

Configure via DATABASE_URL in .env (default: D:/ygb_data/ygb.db)
"""

import os
import uuid
import json
import aiosqlite
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Dict, List, Any

# Load env
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent / ".env")
except ImportError:
    pass

# Database path from env
_raw_url = os.getenv("DATABASE_URL", "sqlite:///D:/ygb_data/ygb.db")
# Strip sqlite:/// prefix if present
DB_PATH = _raw_url.replace("sqlite:///", "").replace("sqlite://", "")

# Connection pool (single connection with WAL mode for concurrency)
_db: Optional[aiosqlite.Connection] = None


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _uuid() -> str:
    return str(uuid.uuid4())


async def _get_db() -> aiosqlite.Connection:
    """Get or create the database connection."""
    global _db
    if _db is None:
        # Ensure directory exists
        db_dir = Path(DB_PATH).parent
        db_dir.mkdir(parents=True, exist_ok=True)

        _db = await aiosqlite.connect(DB_PATH)
        _db.row_factory = aiosqlite.Row
        await _db.execute("PRAGMA journal_mode=WAL")
        await _db.execute("PRAGMA foreign_keys=ON")
    return _db


# =============================================================================
# SCHEMA
# =============================================================================

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    email TEXT,
    role TEXT DEFAULT 'hunter',
    password_hash TEXT,
    avatar_url TEXT,
    total_bounties INTEGER DEFAULT 0,
    total_earnings REAL DEFAULT 0.0,
    created_at TEXT NOT NULL,
    last_active TEXT
);

CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY,
    user_id TEXT,
    mode TEXT,
    target_scope TEXT,
    progress REAL DEFAULT 0.0,
    status TEXT DEFAULT 'active',
    ip_address TEXT,
    user_agent TEXT,
    device_hash TEXT,
    started_at TEXT NOT NULL,
    ended_at TEXT,
    FOREIGN KEY (user_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS devices (
    id TEXT PRIMARY KEY,
    user_id TEXT,
    device_hash TEXT NOT NULL,
    ip_address TEXT,
    user_agent TEXT,
    location TEXT,
    first_seen TEXT NOT NULL,
    last_seen TEXT NOT NULL,
    is_trusted INTEGER DEFAULT 0,
    FOREIGN KEY (user_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS training_runs (
    id TEXT PRIMARY KEY,
    started_at TEXT NOT NULL,
    ended_at TEXT,
    epochs INTEGER,
    final_loss REAL,
    final_accuracy REAL,
    gpu_used INTEGER DEFAULT 0,
    dataset_size INTEGER,
    checkpoint_path TEXT
);

CREATE TABLE IF NOT EXISTS audit_log (
    id TEXT PRIMARY KEY,
    user_id TEXT,
    action_type TEXT NOT NULL,
    description TEXT,
    ip_address TEXT,
    metadata_json TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS targets (
    id TEXT PRIMARY KEY,
    program_name TEXT NOT NULL,
    scope TEXT,
    link TEXT,
    platform TEXT DEFAULT 'hackerone',
    payout_tier TEXT DEFAULT 'medium',
    status TEXT DEFAULT 'active',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS bounties (
    id TEXT PRIMARY KEY,
    user_id TEXT,
    target_id TEXT,
    title TEXT NOT NULL,
    description TEXT,
    severity TEXT DEFAULT 'medium',
    status TEXT DEFAULT 'pending',
    reward REAL DEFAULT 0.0,
    submitted_at TEXT NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users(id),
    FOREIGN KEY (target_id) REFERENCES targets(id)
);
"""


# =============================================================================
# INIT / CLOSE
# =============================================================================

async def init_database():
    """Initialize database and create tables."""
    db = await _get_db()
    await db.executescript(SCHEMA_SQL)
    await db.commit()
    print(f"✅ SQLite database initialized at: {DB_PATH}")


async def close_pool():
    """Close the database connection."""
    global _db
    if _db is not None:
        await _db.close()
        _db = None


# =============================================================================
# HELPERS
# =============================================================================

def _row_to_dict(row) -> Dict[str, Any]:
    """Convert an aiosqlite.Row to a dict."""
    if row is None:
        return {}
    return dict(row)


async def _fetch_all(query: str, params: tuple = ()) -> List[Dict[str, Any]]:
    """Execute a query and return all rows as dicts."""
    db = await _get_db()
    cursor = await db.execute(query, params)
    rows = await cursor.fetchall()
    return [_row_to_dict(r) for r in rows]


async def _fetch_one(query: str, params: tuple = ()) -> Optional[Dict[str, Any]]:
    """Execute a query and return one row as dict."""
    db = await _get_db()
    cursor = await db.execute(query, params)
    row = await cursor.fetchone()
    return _row_to_dict(row) if row else None


async def _execute(query: str, params: tuple = ()):
    """Execute a write query."""
    db = await _get_db()
    await db.execute(query, params)
    await db.commit()


# =============================================================================
# USER OPERATIONS
# =============================================================================

async def create_user(name: str, email: str = None, role: str = "hunter") -> Dict[str, Any]:
    """Create a new user in the database."""
    user_id = _uuid()
    now = _now_iso()
    await _execute(
        "INSERT INTO users (id, name, email, role, created_at, last_active) VALUES (?, ?, ?, ?, ?, ?)",
        (user_id, name, email, role, now, now)
    )
    return {
        "id": user_id, "name": name, "email": email, "role": role,
        "total_bounties": 0, "total_earnings": 0.0,
        "created_at": now, "last_active": now
    }


async def get_user(user_id: str) -> Optional[Dict[str, Any]]:
    """Get a user by ID."""
    return await _fetch_one("SELECT * FROM users WHERE id = ?", (user_id,))


async def get_all_users() -> List[Dict[str, Any]]:
    """Get all users."""
    return await _fetch_all("SELECT * FROM users ORDER BY created_at DESC")


async def update_user_stats(user_id: str, bounties: int = 0, earnings: float = 0.0):
    """Update user statistics."""
    await _execute(
        "UPDATE users SET total_bounties = total_bounties + ?, total_earnings = total_earnings + ?, last_active = ? WHERE id = ?",
        (bounties, earnings, _now_iso(), user_id)
    )


async def get_user_by_email(email: str) -> Optional[Dict[str, Any]]:
    """Get a user by email address."""
    return await _fetch_one("SELECT * FROM users WHERE email = ?", (email,))


async def update_user_password(user_id: str, password_hash: str):
    """Update user's password hash."""
    await _execute(
        "UPDATE users SET password_hash = ? WHERE id = ?",
        (password_hash, user_id)
    )


# =============================================================================
# TARGET OPERATIONS
# =============================================================================

async def create_target(program_name: str, scope: str = None, link: str = None,
                        platform: str = "hackerone", payout_tier: str = "medium") -> Dict[str, Any]:
    """Create a new target."""
    target_id = _uuid()
    now = _now_iso()
    await _execute(
        "INSERT INTO targets (id, program_name, scope, link, platform, payout_tier, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (target_id, program_name, scope, link, platform, payout_tier, now)
    )
    return {
        "id": target_id, "program_name": program_name, "scope": scope,
        "link": link, "platform": platform, "payout_tier": payout_tier,
        "status": "active", "created_at": now
    }


async def get_all_targets() -> List[Dict[str, Any]]:
    """Get all targets."""
    return await _fetch_all("SELECT * FROM targets ORDER BY created_at DESC")


async def get_target(target_id: str) -> Optional[Dict[str, Any]]:
    """Get a target by ID."""
    return await _fetch_one("SELECT * FROM targets WHERE id = ?", (target_id,))


# =============================================================================
# BOUNTY OPERATIONS
# =============================================================================

async def create_bounty(user_id: str, target_id: str = None, title: str = "",
                        description: str = "", severity: str = "medium") -> Dict[str, Any]:
    """Create a new bounty submission."""
    bounty_id = _uuid()
    now = _now_iso()
    await _execute(
        "INSERT INTO bounties (id, user_id, target_id, title, description, severity, submitted_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (bounty_id, user_id, target_id, title, description, severity, now)
    )
    # Update user stats
    await update_user_stats(user_id, bounties=1)
    return {
        "id": bounty_id, "user_id": user_id, "target_id": target_id,
        "title": title, "description": description, "severity": severity,
        "status": "pending", "reward": 0.0, "submitted_at": now
    }


async def get_user_bounties(user_id: str) -> List[Dict[str, Any]]:
    """Get all bounties for a user."""
    return await _fetch_all(
        "SELECT * FROM bounties WHERE user_id = ? ORDER BY submitted_at DESC",
        (user_id,)
    )


async def get_all_bounties() -> List[Dict[str, Any]]:
    """Get all bounties."""
    return await _fetch_all("SELECT * FROM bounties ORDER BY submitted_at DESC")


async def update_bounty_status(bounty_id: str, status: str, reward: float = None):
    """Update bounty status and optionally reward."""
    if reward is not None:
        await _execute(
            "UPDATE bounties SET status = ?, reward = ? WHERE id = ?",
            (status, reward, bounty_id)
        )
    else:
        await _execute(
            "UPDATE bounties SET status = ? WHERE id = ?",
            (status, bounty_id)
        )


# =============================================================================
# SESSION OPERATIONS
# =============================================================================

async def create_session(user_id: str, mode: str = "READ_ONLY",
                         target_scope: str = None, ip_address: str = None,
                         user_agent: str = None, device_hash: str = None) -> Dict[str, Any]:
    """Create a new session in the database."""
    session_id = _uuid()
    now = _now_iso()
    await _execute(
        """INSERT INTO sessions (id, user_id, mode, target_scope, ip_address, 
           user_agent, device_hash, started_at) 
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (session_id, user_id, mode, target_scope, ip_address, user_agent, device_hash, now)
    )
    return {
        "id": session_id, "user_id": user_id, "mode": mode,
        "target_scope": target_scope, "progress": 0.0, "status": "active",
        "ip_address": ip_address, "user_agent": user_agent,
        "device_hash": device_hash, "started_at": now
    }


async def get_user_sessions(user_id: str) -> List[Dict[str, Any]]:
    """Get all sessions for a user."""
    return await _fetch_all(
        "SELECT * FROM sessions WHERE user_id = ? ORDER BY started_at DESC",
        (user_id,)
    )


async def get_active_sessions() -> List[Dict[str, Any]]:
    """Get all active sessions."""
    return await _fetch_all(
        "SELECT s.*, u.name as user_name FROM sessions s LEFT JOIN users u ON s.user_id = u.id WHERE s.status = 'active' ORDER BY s.started_at DESC"
    )


async def update_session_progress(session_id: str, progress: float):
    """Update session progress."""
    await _execute(
        "UPDATE sessions SET progress = ? WHERE id = ?",
        (progress, session_id)
    )


async def end_session(session_id: str):
    """End a session."""
    await _execute(
        "UPDATE sessions SET status = 'ended', ended_at = ? WHERE id = ?",
        (_now_iso(), session_id)
    )


# =============================================================================
# DEVICE OPERATIONS
# =============================================================================

async def register_device(user_id: str, device_hash: str, ip_address: str = None,
                          user_agent: str = None, location: str = None) -> Dict[str, Any]:
    """Register a device or update last_seen if it exists."""
    existing = await _fetch_one(
        "SELECT * FROM devices WHERE user_id = ? AND device_hash = ?",
        (user_id, device_hash)
    )

    now = _now_iso()

    if existing:
        await _execute(
            "UPDATE devices SET last_seen = ?, ip_address = ?, location = ? WHERE id = ?",
            (now, ip_address, location, existing["id"])
        )
        existing["last_seen"] = now
        existing["is_new"] = False
        return existing

    device_id = _uuid()
    await _execute(
        "INSERT INTO devices (id, user_id, device_hash, ip_address, user_agent, location, first_seen, last_seen) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (device_id, user_id, device_hash, ip_address, user_agent, location, now, now)
    )
    return {
        "id": device_id, "user_id": user_id, "device_hash": device_hash,
        "ip_address": ip_address, "user_agent": user_agent, "location": location,
        "first_seen": now, "last_seen": now, "is_trusted": 0, "is_new": True
    }


async def get_user_devices(user_id: str) -> List[Dict[str, Any]]:
    """Get all devices for a user."""
    return await _fetch_all(
        "SELECT * FROM devices WHERE user_id = ? ORDER BY last_seen DESC",
        (user_id,)
    )


async def get_all_active_devices() -> List[Dict[str, Any]]:
    """Get all devices with recent activity (active sessions)."""
    return await _fetch_all(
        """SELECT d.*, u.name as user_name, 
           (SELECT COUNT(*) FROM sessions s WHERE s.device_hash = d.device_hash AND s.status = 'active') as active_sessions
           FROM devices d 
           LEFT JOIN users u ON d.user_id = u.id 
           ORDER BY d.last_seen DESC"""
    )


async def trust_device(device_id: str):
    """Mark a device as trusted."""
    await _execute("UPDATE devices SET is_trusted = 1 WHERE id = ?", (device_id,))


async def get_active_device_count(user_id: str) -> int:
    """Count active devices for a user."""
    result = await _fetch_one(
        "SELECT COUNT(DISTINCT device_hash) as count FROM sessions WHERE user_id = ? AND status = 'active'",
        (user_id,)
    )
    return result["count"] if result else 0


# =============================================================================
# TRAINING RUN OPERATIONS
# =============================================================================

async def create_training_run(epochs: int = 0, gpu_used: bool = False,
                              dataset_size: int = 0) -> Dict[str, Any]:
    """Record a new training run."""
    run_id = _uuid()
    now = _now_iso()
    await _execute(
        "INSERT INTO training_runs (id, started_at, epochs, gpu_used, dataset_size) VALUES (?, ?, ?, ?, ?)",
        (run_id, now, epochs, int(gpu_used), dataset_size)
    )
    return {"id": run_id, "started_at": now, "epochs": epochs}


async def complete_training_run(run_id: str, final_loss: float = None,
                                final_accuracy: float = None,
                                checkpoint_path: str = None):
    """Mark a training run as complete."""
    await _execute(
        "UPDATE training_runs SET ended_at = ?, final_loss = ?, final_accuracy = ?, checkpoint_path = ? WHERE id = ?",
        (_now_iso(), final_loss, final_accuracy, checkpoint_path, run_id)
    )


async def get_training_runs(limit: int = 20) -> List[Dict[str, Any]]:
    """Get recent training runs."""
    return await _fetch_all(
        "SELECT * FROM training_runs ORDER BY started_at DESC LIMIT ?",
        (limit,)
    )


# =============================================================================
# AUDIT LOG OPERATIONS
# =============================================================================

async def log_activity(user_id: str = None, action_type: str = "",
                       description: str = "", ip_address: str = None,
                       metadata: dict = None) -> Dict[str, Any]:
    """Log an activity in the audit trail."""
    log_id = _uuid()
    now = _now_iso()
    meta_json = json.dumps(metadata) if metadata else None
    await _execute(
        "INSERT INTO audit_log (id, user_id, action_type, description, ip_address, metadata_json, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (log_id, user_id, action_type, description, ip_address, meta_json, now)
    )
    return {"id": log_id, "action_type": action_type, "created_at": now}


async def get_recent_activity(limit: int = 50) -> List[Dict[str, Any]]:
    """Get recent activity log entries."""
    return await _fetch_all(
        "SELECT * FROM audit_log ORDER BY created_at DESC LIMIT ?",
        (limit,)
    )


# =============================================================================
# ADMIN STATS
# =============================================================================

async def get_admin_stats() -> Dict[str, Any]:
    """Get admin dashboard statistics from real data."""
    users = await _fetch_one("SELECT COUNT(*) as count FROM users")
    targets = await _fetch_one("SELECT COUNT(*) as count FROM targets")
    bounties = await _fetch_one("SELECT COUNT(*) as count FROM bounties")
    active_sessions = await _fetch_one(
        "SELECT COUNT(*) as count FROM sessions WHERE status = 'active'"
    )
    recent_activity = await _fetch_one(
        "SELECT COUNT(*) as count FROM audit_log WHERE created_at > datetime('now', '-24 hours')"
    )

    return {
        "total_users": users["count"] if users else 0,
        "total_targets": targets["count"] if targets else 0,
        "total_bounties": bounties["count"] if bounties else 0,
        "active_sessions": active_sessions["count"] if active_sessions else 0,
        "activity_24h": recent_activity["count"] if recent_activity else 0,
    }
