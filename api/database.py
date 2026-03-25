"""YGB async local database layer.

This module keeps the existing JSON-file storage model, but moves file work off
the event loop, batches cross-record lookups, caches hot reads, and preserves
the current API surface used by the server.
"""

from __future__ import annotations

import asyncio
import copy
import json
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

DB_DIR = Path(__file__).parent.parent / "data" / "db"
TABLES = ("users", "targets", "bounties", "sessions", "activity_log")
CACHE_TTL_SECONDS = 10.0

_table_locks = {table: asyncio.Lock() for table in TABLES}
_cache_lock = asyncio.Lock()
_record_cache: dict[tuple[str, str], tuple[float, dict[str, Any]]] = {}
_table_cache: dict[str, tuple[float, list[dict[str, Any]]]] = {}


def _clone(value: Any) -> Any:
    return copy.deepcopy(value)


def _ensure_dirs_sync() -> None:
    for table in TABLES:
        (DB_DIR / table).mkdir(parents=True, exist_ok=True)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _record_sort_key(record: dict[str, Any]) -> str:
    return (
        record.get("submitted_at")
        or record.get("created_at")
        or record.get("started_at")
        or record.get("ended_at")
        or ""
    )


def _save_sync(table: str, record_id: str, data: dict[str, Any]) -> None:
    filepath = DB_DIR / table / f"{record_id}.json"
    with open(filepath, "w", encoding="utf-8") as handle:
        json.dump(data, handle, separators=(",", ":"), default=str)


def _load_sync(table: str, record_id: str) -> Optional[dict[str, Any]]:
    filepath = DB_DIR / table / f"{record_id}.json"
    if not filepath.exists():
        return None
    with open(filepath, "r", encoding="utf-8") as handle:
        return json.load(handle)


def _load_all_sync(table: str) -> list[dict[str, Any]]:
    table_dir = DB_DIR / table
    if not table_dir.exists():
        return []
    records: list[dict[str, Any]] = []
    for filepath in table_dir.glob("*.json"):
        try:
            with open(filepath, "r", encoding="utf-8") as handle:
                records.append(json.load(handle))
        except json.JSONDecodeError:
            continue
    records.sort(key=_record_sort_key, reverse=True)
    return records


async def _invalidate_cache(table: str, record_id: Optional[str] = None) -> None:
    async with _cache_lock:
        _table_cache.pop(table, None)
        if record_id is not None:
            _record_cache.pop((table, record_id), None)


async def _load_record(table: str, record_id: str) -> Optional[dict[str, Any]]:
    if not record_id:
        return None
    cache_key = (table, record_id)
    now = asyncio.get_running_loop().time()
    async with _cache_lock:
        cached = _record_cache.get(cache_key)
        if cached and (now - cached[0]) <= CACHE_TTL_SECONDS:
            return _clone(cached[1])

    record = await asyncio.to_thread(_load_sync, table, record_id)
    if record is None:
        return None

    async with _cache_lock:
        _record_cache[cache_key] = (now, _clone(record))
    return _clone(record)


async def _load_all(table: str) -> list[dict[str, Any]]:
    now = asyncio.get_running_loop().time()
    async with _cache_lock:
        cached = _table_cache.get(table)
        if cached and (now - cached[0]) <= CACHE_TTL_SECONDS:
            return _clone(cached[1])

    records = await asyncio.to_thread(_load_all_sync, table)
    async with _cache_lock:
        _table_cache[table] = (now, _clone(records))
    return _clone(records)


async def _save_record(table: str, record_id: str, data: dict[str, Any]) -> None:
    await asyncio.to_thread(_ensure_dirs_sync)
    await asyncio.to_thread(_save_sync, table, record_id, data)
    await _invalidate_cache(table, record_id)


async def _load_records_batch(
    table: str, record_ids: set[str]
) -> dict[str, dict[str, Any]]:
    if not record_ids:
        return {}
    loaded = await asyncio.gather(
        *(_load_record(table, record_id) for record_id in record_ids)
    )
    return {
        record_id: record
        for record_id, record in zip(record_ids, loaded)
        if record is not None
    }


@asynccontextmanager
async def _table_write(*tables: str):
    ordered = sorted(set(tables))
    for table in ordered:
        await _table_locks[table].acquire()
    try:
        yield
    finally:
        for table in reversed(ordered):
            _table_locks[table].release()


def _slice_records(
    records: list[dict[str, Any]], limit: Optional[int], offset: int
) -> list[dict[str, Any]]:
    start = max(offset, 0)
    end = None if limit is None or limit < 0 else start + limit
    return records[start:end]


async def init_database() -> None:
    await asyncio.to_thread(_ensure_dirs_sync)
    print("✅ Local file database initialized at:", DB_DIR)


async def close_pool() -> None:
    async with _cache_lock:
        _record_cache.clear()
        _table_cache.clear()


async def create_user(
    name: str, email: str = None, role: str = "researcher"
) -> Dict[str, Any]:
    async with _table_write("users"):
        user_id = str(uuid.uuid4())
        user = {
            "id": user_id,
            "name": name,
            "email": email,
            "role": role,
            "avatar_url": None,
            "total_bounties": 0,
            "total_earnings": 0.0,
            "created_at": _now_iso(),
            "last_active": _now_iso(),
        }
        await _save_record("users", user_id, user)
        return _clone(user)


async def get_user(user_id: str) -> Optional[Dict[str, Any]]:
    return await _load_record("users", user_id)


async def get_all_users(
    limit: Optional[int] = None, offset: int = 0
) -> List[Dict[str, Any]]:
    users = await _load_all("users")
    return _slice_records(users, limit, offset)


async def update_user_stats(
    user_id: str,
    bounties: int = None,
    earnings: float = None,
    *,
    absolute: bool = False,
) -> None:
    async with _table_write("users"):
        user = await _load_record("users", user_id)
        if not user:
            return
        if bounties is not None:
            if absolute:
                user["total_bounties"] = max(0, bounties)
            else:
                user["total_bounties"] = max(
                    0, user.get("total_bounties", 0) + bounties
                )
        if earnings is not None:
            if absolute:
                user["total_earnings"] = max(0.0, float(earnings))
            else:
                user["total_earnings"] = max(
                    0.0, float(user.get("total_earnings", 0.0)) + float(earnings)
                )
        user["last_active"] = _now_iso()
        await _save_record("users", user_id, user)


async def create_target(
    program_name: str,
    scope: str,
    link: str = None,
    platform: str = None,
    payout_tier: str = "MEDIUM",
) -> Dict[str, Any]:
    async with _table_write("targets"):
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
        await _save_record("targets", target_id, target)
        return _clone(target)


async def get_all_targets(
    limit: Optional[int] = None, offset: int = 0
) -> List[Dict[str, Any]]:
    targets = await _load_all("targets")
    return _slice_records(targets, limit, offset)


async def get_target(target_id: str) -> Optional[Dict[str, Any]]:
    return await _load_record("targets", target_id)


async def create_bounty(
    user_id: str,
    target_id: str,
    title: str,
    description: str = None,
    severity: str = "MEDIUM",
) -> Dict[str, Any]:
    async with _table_write("bounties", "users"):
        bounty_id = str(uuid.uuid4())
        bounty = {
            "id": bounty_id,
            "user_id": user_id,
            "target_id": target_id,
            "title": title,
            "description": description,
            "severity": severity,
            "status": "PENDING",
            "reward": 0.0,
            "submitted_at": _now_iso(),
            "resolved_at": None,
        }
        await _save_record("bounties", bounty_id, bounty)

        user = await _load_record("users", user_id)
        if user:
            user["total_bounties"] = user.get("total_bounties", 0) + 1
            user["last_active"] = _now_iso()
            await _save_record("users", user_id, user)

        return _clone(bounty)


async def get_user_bounties(user_id: str) -> List[Dict[str, Any]]:
    all_bounties = await _load_all("bounties")
    user_bounties = [
        bounty for bounty in all_bounties if bounty.get("user_id") == user_id
    ]
    target_ids = {
        bounty.get("target_id", "")
        for bounty in user_bounties
        if bounty.get("target_id")
    }
    targets = await _load_records_batch("targets", target_ids)

    for bounty in user_bounties:
        target = targets.get(bounty.get("target_id", ""))
        if target:
            bounty["program_name"] = target.get("program_name")
            bounty["scope"] = target.get("scope")
            bounty["link"] = target.get("link")

    return user_bounties


async def get_all_bounties(
    limit: Optional[int] = None, offset: int = 0
) -> List[Dict[str, Any]]:
    all_bounties = await _load_all("bounties")
    page = _slice_records(all_bounties, limit, offset)
    user_ids = {bounty.get("user_id", "") for bounty in page if bounty.get("user_id")}
    target_ids = {
        bounty.get("target_id", "") for bounty in page if bounty.get("target_id")
    }

    users_task = _load_records_batch("users", user_ids)
    targets_task = _load_records_batch("targets", target_ids)
    users, targets = await asyncio.gather(users_task, targets_task)

    for bounty in page:
        user = users.get(bounty.get("user_id", ""))
        target = targets.get(bounty.get("target_id", ""))
        if user:
            bounty["user_name"] = user.get("name")
            bounty["user_email"] = user.get("email")
        if target:
            bounty["program_name"] = target.get("program_name")
            bounty["scope"] = target.get("scope")
            bounty["link"] = target.get("link")

    return page


async def update_bounty_status(
    bounty_id: str, status: str, reward: float = None
) -> None:
    async with _table_write("bounties", "users"):
        bounty = await _load_record("bounties", bounty_id)
        if not bounty:
            return
        bounty["status"] = status
        if reward is not None:
            bounty["reward"] = float(reward)
            bounty["resolved_at"] = _now_iso()
            user = await _load_record("users", bounty.get("user_id", ""))
            if user:
                user["total_earnings"] = float(user.get("total_earnings", 0.0)) + float(
                    reward
                )
                user["last_active"] = _now_iso()
                await _save_record("users", bounty["user_id"], user)
        await _save_record("bounties", bounty_id, bounty)


async def create_session(
    user_id: str, mode: str, target_scope: str = None
) -> Dict[str, Any]:
    async with _table_write("sessions"):
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
        await _save_record("sessions", session_id, session)
        return _clone(session)


async def get_user_sessions(user_id: str) -> List[Dict[str, Any]]:
    sessions = await _load_all("sessions")
    return [session for session in sessions if session.get("user_id") == user_id]


async def update_session_progress(
    session_id: str, progress: int, status: str = None
) -> None:
    async with _table_write("sessions"):
        session = await _load_record("sessions", session_id)
        if not session:
            return
        session["progress"] = progress
        if status:
            session["status"] = status
            if status == "COMPLETED":
                session["ended_at"] = _now_iso()
        await _save_record("sessions", session_id, session)


async def log_activity(
    user_id: str,
    action_type: str,
    description: str = None,
    metadata: dict = None,
) -> None:
    async with _table_write("activity_log"):
        activity_id = str(uuid.uuid4())
        activity = {
            "id": activity_id,
            "user_id": user_id,
            "action_type": action_type,
            "description": description,
            "metadata": metadata,
            "created_at": _now_iso(),
        }
        await _save_record("activity_log", activity_id, activity)


async def get_recent_activity(limit: int = 50, offset: int = 0) -> List[Dict[str, Any]]:
    activities = _slice_records(await _load_all("activity_log"), limit, offset)
    user_ids = {
        activity.get("user_id", "")
        for activity in activities
        if activity.get("user_id")
    }
    users = await _load_records_batch("users", user_ids)
    for activity in activities:
        user = users.get(activity.get("user_id", ""))
        if user:
            activity["user_name"] = user.get("name")
    return activities


async def get_admin_stats() -> Dict[str, Any]:
    users, bounties, targets, sessions = await asyncio.gather(
        _load_all("users"),
        _load_all("bounties"),
        _load_all("targets"),
        _load_all("sessions"),
    )

    week_ago = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
    active_users = sum(1 for user in users if user.get("last_active", "") >= week_ago)
    pending_bounties = sum(
        1 for bounty in bounties if bounty.get("status") == "PENDING"
    )
    total_paid = sum(
        float(bounty.get("reward", 0.0))
        for bounty in bounties
        if bounty.get("status") == "PAID"
    )
    active_targets = sum(1 for target in targets if target.get("status") == "ACTIVE")
    active_sessions = sum(
        1 for session in sessions if session.get("status") == "ACTIVE"
    )

    return {
        "users": {"total": len(users), "active_last_7_days": active_users},
        "bounties": {
            "total": len(bounties),
            "pending": pending_bounties,
            "total_paid": float(total_paid),
        },
        "targets": {"total": len(targets), "active": active_targets},
        "sessions": {"active": active_sessions},
    }
