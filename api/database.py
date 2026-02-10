"""
YGB Database Module — Local File Storage

Drop-in replacement for asyncpg PostgreSQL module.
Uses JSON files on local drive at data/db/ for persistence.
No external database dependencies required.
"""

import os
import json
import uuid
import threading
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from pathlib import Path

# Local database directory
DB_DIR = Path(__file__).parent.parent / "data" / "db"

# Thread lock for file operations
_lock = threading.Lock()


def _ensure_dirs():
    """Create database directories if they don't exist."""
    for table in ["users", "targets", "bounties", "sessions", "activity_log"]:
        (DB_DIR / table).mkdir(parents=True, exist_ok=True)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _save(table: str, record_id: str, data: dict):
    """Save a record to disk."""
    filepath = DB_DIR / table / f"{record_id}.json"
    with open(filepath, "w") as f:
        json.dump(data, f, indent=2, default=str)


def _load(table: str, record_id: str) -> Optional[dict]:
    """Load a record from disk."""
    filepath = DB_DIR / table / f"{record_id}.json"
    if not filepath.exists():
        return None
    with open(filepath, "r") as f:
        return json.load(f)


def _load_all(table: str) -> List[dict]:
    """Load all records from a table."""
    table_dir = DB_DIR / table
    if not table_dir.exists():
        return []
    records = []
    for filepath in table_dir.glob("*.json"):
        with open(filepath, "r") as f:
            records.append(json.load(f))
    # Sort by created_at descending
    records.sort(key=lambda x: x.get("created_at", ""), reverse=True)
    return records


# =============================================================================
# INIT / CLOSE
# =============================================================================

async def init_database():
    """Initialize local file database directories."""
    _ensure_dirs()
    print("✅ Local file database initialized at:", DB_DIR)


async def close_pool():
    """No-op for file-based database."""
    pass


# =============================================================================
# USER OPERATIONS
# =============================================================================

async def create_user(name: str, email: str = None, role: str = "researcher") -> Dict[str, Any]:
    """Create a new user."""
    with _lock:
        user_id = str(uuid.uuid4())
        user = {
            "id": user_id,
            "name": name,
            "email": email,
            "role": role,
            "avatar_url": None,
            "total_bounties": 0,
            "total_earnings": 0.00,
            "created_at": _now_iso(),
            "last_active": _now_iso(),
        }
        _ensure_dirs()
        _save("users", user_id, user)
        return user


async def get_user(user_id: str) -> Optional[Dict[str, Any]]:
    """Get a user by ID."""
    return _load("users", user_id)


async def get_all_users() -> List[Dict[str, Any]]:
    """Get all users."""
    return _load_all("users")


async def update_user_stats(user_id: str, bounties: int = None, earnings: float = None):
    """Update user statistics."""
    with _lock:
        user = _load("users", user_id)
        if user:
            if bounties is not None:
                user["total_bounties"] = bounties
            if earnings is not None:
                user["total_earnings"] = earnings
            user["last_active"] = _now_iso()
            _save("users", user_id, user)


# =============================================================================
# TARGET OPERATIONS
# =============================================================================

async def create_target(program_name: str, scope: str, link: str = None,
                        platform: str = None, payout_tier: str = "MEDIUM") -> Dict[str, Any]:
    """Create a new target."""
    with _lock:
        target_id = str(uuid.uuid4())
        target = {
            "id": target_id,
            "program_name": program_name,
            "scope": scope,
            "link": link,
            "platform": platform,
            "payout_tier": payout_tier,
            "status": "ACTIVE",
            "created_at": _now_iso(),
        }
        _ensure_dirs()
        _save("targets", target_id, target)
        return target


async def get_all_targets() -> List[Dict[str, Any]]:
    """Get all targets."""
    return _load_all("targets")


async def get_target(target_id: str) -> Optional[Dict[str, Any]]:
    """Get a target by ID."""
    return _load("targets", target_id)


# =============================================================================
# BOUNTY OPERATIONS
# =============================================================================

async def create_bounty(user_id: str, target_id: str, title: str,
                        description: str = None, severity: str = "MEDIUM") -> Dict[str, Any]:
    """Create a new bounty submission."""
    with _lock:
        bounty_id = str(uuid.uuid4())
        bounty = {
            "id": bounty_id,
            "user_id": user_id,
            "target_id": target_id,
            "title": title,
            "description": description,
            "severity": severity,
            "status": "PENDING",
            "reward": 0.00,
            "submitted_at": _now_iso(),
            "resolved_at": None,
        }
        _ensure_dirs()
        _save("bounties", bounty_id, bounty)

        # Update user bounty count
        user = _load("users", user_id)
        if user:
            user["total_bounties"] = user.get("total_bounties", 0) + 1
            _save("users", user_id, user)

        return bounty


async def get_user_bounties(user_id: str) -> List[Dict[str, Any]]:
    """Get all bounties for a user."""
    all_bounties = _load_all("bounties")
    user_bounties = [b for b in all_bounties if b.get("user_id") == user_id]

    # Enrich with target info
    for b in user_bounties:
        target = _load("targets", b.get("target_id", ""))
        if target:
            b["program_name"] = target.get("program_name")
            b["scope"] = target.get("scope")
            b["link"] = target.get("link")

    return user_bounties


async def get_all_bounties() -> List[Dict[str, Any]]:
    """Get all bounties with user and target info."""
    all_bounties = _load_all("bounties")

    for b in all_bounties:
        user = _load("users", b.get("user_id", ""))
        target = _load("targets", b.get("target_id", ""))
        if user:
            b["user_name"] = user.get("name")
            b["user_email"] = user.get("email")
        if target:
            b["program_name"] = target.get("program_name")
            b["scope"] = target.get("scope")

    return all_bounties


async def update_bounty_status(bounty_id: str, status: str, reward: float = None):
    """Update bounty status and reward."""
    with _lock:
        bounty = _load("bounties", bounty_id)
        if bounty:
            bounty["status"] = status
            if reward is not None:
                bounty["reward"] = reward
                bounty["resolved_at"] = _now_iso()

                # Update user earnings
                user = _load("users", bounty.get("user_id", ""))
                if user:
                    user["total_earnings"] = user.get("total_earnings", 0) + reward
                    _save("users", bounty["user_id"], user)

            _save("bounties", bounty_id, bounty)


# =============================================================================
# SESSION OPERATIONS
# =============================================================================

async def create_session(user_id: str, mode: str, target_scope: str = None) -> Dict[str, Any]:
    """Create a new session."""
    with _lock:
        session_id = str(uuid.uuid4())
        session = {
            "id": session_id,
            "user_id": user_id,
            "mode": mode,
            "target_scope": target_scope,
            "progress": 0,
            "status": "ACTIVE",
            "started_at": _now_iso(),
            "ended_at": None,
        }
        _ensure_dirs()
        _save("sessions", session_id, session)
        return session


async def get_user_sessions(user_id: str) -> List[Dict[str, Any]]:
    """Get all sessions for a user."""
    all_sessions = _load_all("sessions")
    return [s for s in all_sessions if s.get("user_id") == user_id]


async def update_session_progress(session_id: str, progress: int, status: str = None):
    """Update session progress."""
    with _lock:
        session = _load("sessions", session_id)
        if session:
            session["progress"] = progress
            if status:
                session["status"] = status
                if status == "COMPLETED":
                    session["ended_at"] = _now_iso()
            _save("sessions", session_id, session)


# =============================================================================
# ACTIVITY LOG
# =============================================================================

async def log_activity(user_id: str, action_type: str, description: str = None, metadata: dict = None):
    """Log user activity."""
    with _lock:
        activity_id = str(uuid.uuid4())
        activity = {
            "id": activity_id,
            "user_id": user_id,
            "action_type": action_type,
            "description": description,
            "metadata": metadata,
            "created_at": _now_iso(),
        }
        _ensure_dirs()
        _save("activity_log", activity_id, activity)


async def get_recent_activity(limit: int = 50) -> List[Dict[str, Any]]:
    """Get recent activity log."""
    activities = _load_all("activity_log")

    # Enrich with user name
    for a in activities[:limit]:
        user = _load("users", a.get("user_id", ""))
        if user:
            a["user_name"] = user.get("name")

    return activities[:limit]


# =============================================================================
# ADMIN STATS
# =============================================================================

async def get_admin_stats() -> Dict[str, Any]:
    """Get admin dashboard statistics."""
    users = _load_all("users")
    bounties = _load_all("bounties")
    targets = _load_all("targets")
    sessions = _load_all("sessions")

    # Count active users (last 7 days)
    from datetime import timedelta
    week_ago = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
    active_users = sum(1 for u in users if u.get("last_active", "") >= week_ago)

    pending_bounties = sum(1 for b in bounties if b.get("status") == "PENDING")
    total_paid = sum(b.get("reward", 0) for b in bounties if b.get("status") == "PAID")
    active_targets = sum(1 for t in targets if t.get("status") == "ACTIVE")
    active_sessions = sum(1 for s in sessions if s.get("status") == "ACTIVE")

    return {
        "users": {
            "total": len(users),
            "active_last_7_days": active_users,
        },
        "bounties": {
            "total": len(bounties),
            "pending": pending_bounties,
            "total_paid": float(total_paid),
        },
        "targets": {
            "total": len(targets),
            "active": active_targets,
        },
        "sessions": {
            "active": active_sessions,
        },
    }
