"""YGB optimized SQLite database layer.

This module provides a high-performance SQLite backend that replaces the JSON-file
storage with proper database operations, transactions, and indexing.
Maintains 100% API compatibility with the original database.py.
"""

from __future__ import annotations

import asyncio
import json
import uuid
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import aiosqlite

logger = logging.getLogger(__name__)

DB_PATH = Path(__file__).parent.parent / "data" / "ygb.db"
CACHE_TTL_SECONDS = 10.0

# In-memory caches for hot data
_cache_lock = asyncio.Lock()
_record_cache: dict[Tuple[str, str], Tuple[float, dict[str, Any]]] = {}
_table_cache: dict[str, Tuple[float, List[dict[str, Any]]]] = {}


def _clone(value: Any) -> Any:
    """Deep clone a value for cache safety."""
    return json.loads(json.dumps(value))


def _now_iso() -> str:
    """Get current UTC time in ISO format."""
    return datetime.now(timezone.utc).isoformat()


def _record_sort_key(record: dict[str, Any]) -> str:
    """Extract sort key from record for consistent ordering."""
    return (
        record.get("submitted_at")
        or record.get("created_at")
        or record.get("started_at")
        or record.get("ended_at")
        or ""
    )


class Database:
    """Optimized SQLite database with async operations and caching."""

    def __init__(self, db_path: Path = DB_PATH):
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._connection: Optional[aiosqlite.Connection] = None
        self._lock = asyncio.Lock()

    async def connect(self) -> None:
        """Establish database connection with optimized settings."""
        if self._connection is not None:
            return

        self._connection = await aiosqlite.connect(str(self.db_path))
        self._connection.row_factory = aiosqlite.Row
        await self._connection.execute("PRAGMA journal_mode=WAL")
        await self._connection.execute("PRAGMA synchronous=NORMAL")
        await self._connection.execute("PRAGMA foreign_keys=ON")
        await self._connection.execute("PRAGMA busy_timeout=5000")
        await self._create_tables()
        logger.info(f"SQLite database connected: {self.db_path}")

    async def disconnect(self) -> None:
        """Close database connection."""
        if self._connection:
            await self._connection.close()
            self._connection = None

    async def _create_tables(self) -> None:
        """Create tables with proper indexing."""
        # Users table
        await self._connection.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                email TEXT,
                role TEXT DEFAULT 'researcher',
                avatar_url TEXT,
                total_bounties INTEGER DEFAULT 0,
                total_earnings REAL DEFAULT 0.0,
                created_at TEXT NOT NULL,
                last_active TEXT NOT NULL
            )
        """)

        # Targets table
        await self._connection.execute("""
            CREATE TABLE IF NOT EXISTS targets (
                id TEXT PRIMARY KEY,
                program_name TEXT NOT NULL,
                scope TEXT NOT NULL,
                link TEXT,
                platform TEXT,
                payout_tier TEXT DEFAULT 'MEDIUM',
                status TEXT DEFAULT 'ACTIVE',
                created_at TEXT NOT NULL
            )
        """)

        # Bounties table
        await self._connection.execute("""
            CREATE TABLE IF NOT EXISTS bounties (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                target_id TEXT NOT NULL,
                title TEXT NOT NULL,
                description TEXT,
                severity TEXT DEFAULT 'MEDIUM',
                status TEXT DEFAULT 'PENDING',
                reward REAL DEFAULT 0.0,
                submitted_at TEXT NOT NULL,
                resolved_at TEXT,
                FOREIGN KEY (user_id) REFERENCES users(id),
                FOREIGN KEY (target_id) REFERENCES targets(id)
            )
        """)

        # Sessions table
        await self._connection.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                mode TEXT NOT NULL,
                target_scope TEXT,
                progress INTEGER DEFAULT 0,
                status TEXT DEFAULT 'ACTIVE',
                started_at TEXT NOT NULL,
                ended_at TEXT,
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        """)

        # Activity log table
        await self._connection.execute("""
            CREATE TABLE IF NOT EXISTS activity_log (
                id TEXT PRIMARY KEY,
                user_id TEXT,
                action_type TEXT NOT NULL,
                description TEXT,
                metadata TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        """)

        # Create indexes for performance
        await self._connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_users_last_active ON users(last_active)"
        )
        await self._connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_bounties_user_id ON bounties(user_id)"
        )
        await self._connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_bounties_target_id ON bounties(target_id)"
        )
        await self._connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_bounties_status ON bounties(status)"
        )
        await self._connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_sessions_user_id ON sessions(user_id)"
        )
        await self._connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_sessions_status ON sessions(status)"
        )
        await self._connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_targets_status ON targets(status)"
        )
        await self._connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_activity_log_user_id ON activity_log(user_id)"
        )
        await self._connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_activity_log_created_at ON activity_log(created_at)"
        )

        await self._connection.commit()

    async def _execute(self, sql: str, params: tuple = ()) -> aiosqlite.Cursor:
        """Execute SQL with error handling and retry logic."""
        for attempt in range(3):
            try:
                return await self._connection.execute(sql, params)
            except aiosqlite.OperationalError as e:
                if "locked" in str(e) and attempt < 2:
                    await asyncio.sleep(0.1 * (attempt + 1))
                    continue
                raise
        raise RuntimeError("Failed to execute SQL after retries")

    async def _fetch_one(
        self, sql: str, params: tuple = ()
    ) -> Optional[dict[str, Any]]:
        """Fetch single row as dictionary."""
        cursor = await self._execute(sql, params)
        row = await cursor.fetchone()
        if row:
            return dict(row)
        return None

    async def _fetch_all(self, sql: str, params: tuple = ()) -> List[dict[str, Any]]:
        """Fetch all rows as list of dictionaries."""
        cursor = await self._execute(sql, params)
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]

    async def _invalidate_cache(
        self, table: str, record_id: Optional[str] = None
    ) -> None:
        """Invalidate cached data for a table."""
        async with _cache_lock:
            _table_cache.pop(table, None)
            if record_id is not None:
                _record_cache.pop((table, record_id), None)


# Global database instance
_db: Optional[Database] = None


async def get_db() -> Database:
    """Get or create database instance."""
    global _db
    if _db is None:
        _db = Database()
        await _db.connect()
    return _db


# =============================================================================
# Public API - Maintains 100% compatibility with original database.py
# =============================================================================


async def init_database() -> None:
    """Initialize the database."""
    db = await get_db()
    logger.info("SQLite database initialized at:", DB_PATH)


async def close_pool() -> None:
    """Close database connection and clear caches."""
    global _db
    if _db:
        await _db.disconnect()
        _db = None

    async with _cache_lock:
        _record_cache.clear()
        _table_cache.clear()


async def create_user(
    name: str, email: str = None, role: str = "researcher"
) -> Dict[str, Any]:
    """Create a new user."""
    db = await get_db()
    user_id = str(uuid.uuid4())
    now = _now_iso()

    await db._execute(
        """INSERT INTO users (id, name, email, role, avatar_url, total_bounties, total_earnings, created_at, last_active)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (user_id, name, email, role, None, 0, 0.0, now, now),
    )
    await db._connection.commit()
    await db._invalidate_cache("users")

    return {
        "id": user_id,
        "name": name,
        "email": email,
        "role": role,
        "avatar_url": None,
        "total_bounties": 0,
        "total_earnings": 0.0,
        "created_at": now,
        "last_active": now,
    }


async def get_user(user_id: str) -> Optional[Dict[str, Any]]:
    """Get user by ID with caching."""
    if not user_id:
        return None

    cache_key = ("users", user_id)
    now = asyncio.get_running_loop().time()

    async with _cache_lock:
        cached = _record_cache.get(cache_key)
        if cached and (now - cached[0]) <= CACHE_TTL_SECONDS:
            return _clone(cached[1])

    db = await get_db()
    user = await db._fetch_one("SELECT * FROM users WHERE id = ?", (user_id,))

    if user:
        async with _cache_lock:
            _record_cache[cache_key] = (now, _clone(user))

    return user


async def get_all_users(
    limit: Optional[int] = None, offset: int = 0
) -> List[Dict[str, Any]]:
    """Get all users with pagination."""
    db = await get_db()

    # Check table cache first
    now = asyncio.get_running_loop().time()
    async with _cache_lock:
        cached = _table_cache.get("users")
        if cached and (now - cached[0]) <= CACHE_TTL_SECONDS:
            records = _clone(cached[1])
            start = max(offset, 0)
            end = None if limit is None or limit < 0 else start + limit
            return records[start:end]

    # Fetch from database
    query = "SELECT * FROM users ORDER BY created_at DESC"
    if limit is not None and limit >= 0:
        query += f" LIMIT {limit} OFFSET {offset}"
    elif offset > 0:
        query += f" LIMIT -1 OFFSET {offset}"

    users = await db._fetch_all(query)

    # Cache full table for subsequent requests
    if limit is None or limit < 0:
        async with _cache_lock:
            _table_cache["users"] = (now, _clone(users))

    return users


async def update_user_stats(
    user_id: str,
    bounties: int = None,
    earnings: float = None,
    *,
    absolute: bool = False,
) -> None:
    """Update user statistics."""
    db = await get_db()

    # Get current user stats
    user = await get_user(user_id)
    if not user:
        return

    # Calculate new values
    new_bounties = user.get("total_bounties", 0)
    new_earnings = user.get("total_earnings", 0.0)

    if bounties is not None:
        if absolute:
            new_bounties = max(0, bounties)
        else:
            new_bounties = max(0, new_bounties + bounties)

    if earnings is not None:
        if absolute:
            new_earnings = max(0.0, float(earnings))
        else:
            new_earnings = max(0.0, new_earnings + float(earnings))

    # Update in database
    now = _now_iso()
    await db._execute(
        """UPDATE users SET total_bounties = ?, total_earnings = ?, last_active = ? WHERE id = ?""",
        (new_bounties, new_earnings, now, user_id),
    )
    await db._connection.commit()
    await db._invalidate_cache("users", user_id)


async def create_target(
    program_name: str,
    scope: str,
    link: str = None,
    platform: str = None,
    payout_tier: str = "MEDIUM",
) -> Dict[str, Any]:
    """Create a new target."""
    db = await get_db()
    target_id = str(uuid.uuid4())
    now = _now_iso()

    await db._execute(
        """INSERT INTO targets (id, program_name, scope, link, platform, payout_tier, status, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (target_id, program_name, scope, link, platform, payout_tier, "ACTIVE", now),
    )
    await db._connection.commit()
    await db._invalidate_cache("targets")

    return {
        "id": target_id,
        "program_name": program_name,
        "scope": scope,
        "link": link,
        "platform": platform,
        "payout_tier": payout_tier,
        "status": "ACTIVE",
        "created_at": now,
    }


async def get_all_targets(
    limit: Optional[int] = None, offset: int = 0
) -> List[Dict[str, Any]]:
    """Get all targets with pagination."""
    db = await get_db()
    query = "SELECT * FROM targets ORDER BY created_at DESC"
    if limit is not None and limit >= 0:
        query += f" LIMIT {limit} OFFSET {offset}"
    elif offset > 0:
        query += f" LIMIT -1 OFFSET {offset}"

    return await db._fetch_all(query)


async def get_target(target_id: str) -> Optional[Dict[str, Any]]:
    """Get target by ID."""
    db = await get_db()
    return await db._fetch_one("SELECT * FROM targets WHERE id = ?", (target_id,))


async def create_bounty(
    user_id: str,
    target_id: str,
    title: str,
    description: str = None,
    severity: str = "MEDIUM",
) -> Dict[str, Any]:
    """Create a new bounty with transaction support."""
    db = await get_db()
    bounty_id = str(uuid.uuid4())
    now = _now_iso()

    # Use transaction for atomicity
    await db._execute("BEGIN TRANSACTION")
    try:
        # Create bounty
        await db._execute(
            """INSERT INTO bounties (id, user_id, target_id, title, description, severity, status, reward, submitted_at, resolved_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                bounty_id,
                user_id,
                target_id,
                title,
                description,
                severity,
                "PENDING",
                0.0,
                now,
                None,
            ),
        )

        # Update user's bounty count
        await db._execute(
            """UPDATE users SET total_bounties = total_bounties + 1, last_active = ? WHERE id = ?""",
            (now, user_id),
        )

        await db._connection.commit()
        await db._invalidate_cache("bounties")
        await db._invalidate_cache("users", user_id)

    except Exception:
        await db._connection.rollback()
        raise

    return {
        "id": bounty_id,
        "user_id": user_id,
        "target_id": target_id,
        "title": title,
        "description": description,
        "severity": severity,
        "status": "PENDING",
        "reward": 0.0,
        "submitted_at": now,
        "resolved_at": None,
    }


async def get_user_bounties(user_id: str) -> List[Dict[str, Any]]:
    """Get bounties for a specific user with target info."""
    db = await get_db()

    query = """
        SELECT b.*, t.program_name, t.scope, t.link
        FROM bounties b
        LEFT JOIN targets t ON b.target_id = t.id
        WHERE b.user_id = ?
        ORDER BY b.submitted_at DESC
    """
    return await db._fetch_all(query, (user_id,))


async def get_all_bounties(
    limit: Optional[int] = None, offset: int = 0
) -> List[Dict[str, Any]]:
    """Get all bounties with user and target info."""
    db = await get_db()

    query = """
        SELECT b.*, u.name as user_name, u.email as user_email,
               t.program_name, t.scope, t.link
        FROM bounties b
        LEFT JOIN users u ON b.user_id = u.id
        LEFT JOIN targets t ON b.target_id = t.id
        ORDER BY b.submitted_at DESC
    """

    if limit is not None and limit >= 0:
        query += f" LIMIT {limit} OFFSET {offset}"
    elif offset > 0:
        query += f" LIMIT -1 OFFSET {offset}"

    return await db._fetch_all(query)


async def update_bounty_status(
    bounty_id: str, status: str, reward: float = None
) -> None:
    """Update bounty status with transaction support."""
    db = await get_db()

    await db._execute("BEGIN TRANSACTION")
    try:
        # Get bounty to find user_id
        bounty = await db._fetch_one(
            "SELECT * FROM bounties WHERE id = ?", (bounty_id,)
        )
        if not bounty:
            await db._connection.rollback()
            return

        now = _now_iso()
        resolved_at = now if status == "PAID" and reward is not None else None

        # Update bounty
        if reward is not None:
            await db._execute(
                """UPDATE bounties SET status = ?, reward = ?, resolved_at = ? WHERE id = ?""",
                (status, float(reward), resolved_at, bounty_id),
            )

            # Update user's earnings
            await db._execute(
                """UPDATE users SET total_earnings = total_earnings + ?, last_active = ? WHERE id = ?""",
                (float(reward), now, bounty["user_id"]),
            )
            await db._invalidate_cache("users", bounty["user_id"])
        else:
            await db._execute(
                """UPDATE bounties SET status = ? WHERE id = ?""", (status, bounty_id)
            )

        await db._connection.commit()
        await db._invalidate_cache("bounties")

    except Exception:
        await db._connection.rollback()
        raise


async def create_session(
    user_id: str, mode: str, target_scope: str = None
) -> Dict[str, Any]:
    """Create a new session."""
    db = await get_db()
    session_id = str(uuid.uuid4())
    now = _now_iso()

    await db._execute(
        """INSERT INTO sessions (id, user_id, mode, target_scope, progress, status, started_at, ended_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (session_id, user_id, mode, target_scope, 0, "ACTIVE", now, None),
    )
    await db._connection.commit()
    await db._invalidate_cache("sessions")

    return {
        "id": session_id,
        "user_id": user_id,
        "mode": mode,
        "target_scope": target_scope,
        "progress": 0,
        "status": "ACTIVE",
        "started_at": now,
        "ended_at": None,
    }


async def get_user_sessions(user_id: str) -> List[Dict[str, Any]]:
    """Get sessions for a specific user."""
    db = await get_db()
    return await db._fetch_all(
        "SELECT * FROM sessions WHERE user_id = ? ORDER BY started_at DESC", (user_id,)
    )


async def update_session_progress(
    session_id: str, progress: int, status: str = None
) -> None:
    """Update session progress and status."""
    db = await get_db()

    now = _now_iso()
    ended_at = now if status == "COMPLETED" else None

    if status:
        await db._execute(
            """UPDATE sessions SET progress = ?, status = ?, ended_at = ? WHERE id = ?""",
            (progress, status, ended_at, session_id),
        )
    else:
        await db._execute(
            """UPDATE sessions SET progress = ? WHERE id = ?""", (progress, session_id)
        )

    await db._connection.commit()
    await db._invalidate_cache("sessions")


async def log_activity(
    user_id: str,
    action_type: str,
    description: str = None,
    metadata: dict = None,
) -> None:
    """Log user activity."""
    db = await get_db()
    activity_id = str(uuid.uuid4())
    now = _now_iso()

    await db._execute(
        """INSERT INTO activity_log (id, user_id, action_type, description, metadata, created_at)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (
            activity_id,
            user_id,
            action_type,
            description,
            json.dumps(metadata) if metadata else None,
            now,
        ),
    )
    await db._connection.commit()


async def get_recent_activity(limit: int = 50, offset: int = 0) -> List[Dict[str, Any]]:
    """Get recent activity with user info."""
    db = await get_db()

    query = """
        SELECT a.*, u.name as user_name
        FROM activity_log a
        LEFT JOIN users u ON a.user_id = u.id
        ORDER BY a.created_at DESC
        LIMIT ? OFFSET ?
    """

    activities = await db._fetch_all(query, (limit, offset))

    # Parse metadata JSON
    for activity in activities:
        if activity.get("metadata"):
            try:
                activity["metadata"] = json.loads(activity["metadata"])
            except json.JSONDecodeError:
                activity["metadata"] = None

    return activities


async def get_admin_stats() -> Dict[str, Any]:
    """Get admin statistics with optimized queries."""
    db = await get_db()
    now = datetime.now(timezone.utc)
    week_ago = (now - timedelta(days=7)).isoformat()

    # Parallel queries for performance
    users_count_task = db._fetch_one("SELECT COUNT(*) as count FROM users")
    active_users_task = db._fetch_one(
        "SELECT COUNT(*) as count FROM users WHERE last_active >= ?", (week_ago,)
    )
    bounties_count_task = db._fetch_one("SELECT COUNT(*) as count FROM bounties")
    pending_bounties_task = db._fetch_one(
        "SELECT COUNT(*) as count FROM bounties WHERE status = 'PENDING'"
    )
    paid_bounties_task = db._fetch_one(
        "SELECT COALESCE(SUM(reward), 0) as total FROM bounties WHERE status = 'PAID'"
    )
    targets_count_task = db._fetch_one("SELECT COUNT(*) as count FROM targets")
    active_targets_task = db._fetch_one(
        "SELECT COUNT(*) as count FROM targets WHERE status = 'ACTIVE'"
    )
    active_sessions_task = db._fetch_one(
        "SELECT COUNT(*) as count FROM sessions WHERE status = 'ACTIVE'"
    )

    results = await asyncio.gather(
        users_count_task,
        active_users_task,
        bounties_count_task,
        pending_bounties_task,
        paid_bounties_task,
        targets_count_task,
        active_targets_task,
        active_sessions_task,
    )

    return {
        "users": {
            "total": results[0]["count"],
            "active_last_7_days": results[1]["count"],
        },
        "bounties": {
            "total": results[2]["count"],
            "pending": results[3]["count"],
            "total_paid": float(results[4]["total"]),
        },
        "targets": {
            "total": results[5]["count"],
            "active": results[6]["count"],
        },
        "sessions": {
            "active": results[7]["count"],
        },
    }
