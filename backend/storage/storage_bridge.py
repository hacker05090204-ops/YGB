"""
Storage Bridge — Python Governance Layer
==========================================

Bridges the HDD storage engine to FastAPI.
Exposes all storage, lifecycle, video, and monitoring endpoints.

No mock data. No fallback. No SQLite. No JSON pseudo-database.
All data from HDD engine only.
"""

import os
import sys
import logging
import uuid
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from native.hdd_engine.hdd_engine import HDDEngine, LifecycleState, get_engine
from native.hdd_engine.lifecycle_manager import LifecycleManager
from native.hdd_engine.secure_wiper import secure_wipe, secure_wipe_entity
from native.hdd_engine.disk_monitor import DiskMonitor
from native.hdd_engine.video_streamer import VideoStreamer

logger = logging.getLogger("storage_bridge")


# =============================================================================
# SINGLETON INSTANCES
# =============================================================================

_engine: Optional[HDDEngine] = None
_lifecycle: Optional[LifecycleManager] = None
_disk_monitor: Optional[DiskMonitor] = None
_video_streamer: Optional[VideoStreamer] = None


def init_storage(hdd_root: Optional[str] = None) -> Dict[str, Any]:
    """
    Initialize the HDD storage engine and all subsystems.
    Call this once at application startup.
    """
    global _engine, _lifecycle, _disk_monitor, _video_streamer

    _engine = get_engine(hdd_root)

    _lifecycle = LifecycleManager(_engine)
    _lifecycle.start_sweep_thread()

    _disk_monitor = DiskMonitor(_engine)
    _disk_monitor.start()

    _video_streamer = VideoStreamer(str(_engine.root))

    logger.info(f"Storage bridge initialized at: {_engine.root}")

    return {
        "status": "initialized",
        "hdd_root": str(_engine.root),
        "subsystems": ["engine", "lifecycle", "disk_monitor", "video_streamer"],
    }


def shutdown_storage() -> None:
    """Shutdown all storage subsystems."""
    if _lifecycle:
        _lifecycle.stop_sweep_thread()
    if _disk_monitor:
        _disk_monitor.stop()
    logger.info("Storage bridge shutdown complete")


# =============================================================================
# USER OPERATIONS
# =============================================================================

def create_user(name: str, email: str = None, role: str = "hunter") -> Dict[str, Any]:
    """Create a new user entity on HDD."""
    user_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()

    data = {
        "name": name,
        "email": email,
        "role": role,
        "total_bounties": 0,
        "total_earnings": 0.0,
        "created_at": now,
        "last_active": now,
    }

    result = _engine.create_entity("users", user_id, data)
    return {"id": user_id, **data}


def get_user(user_id: str) -> Optional[Dict[str, Any]]:
    """Get a user by ID."""
    entity = _engine.read_entity("users", user_id)
    if not entity or not entity.get("latest"):
        return None

    latest = entity["latest"]
    return {
        "id": user_id,
        "name": latest.get("name", ""),
        "email": latest.get("email"),
        "role": latest.get("role", "hunter"),
        "total_bounties": latest.get("total_bounties", 0),
        "total_earnings": latest.get("total_earnings", 0.0),
        "created_at": latest.get("created_at", ""),
        "last_active": latest.get("last_active", ""),
    }


def get_all_users() -> List[Dict[str, Any]]:
    """Get all users."""
    metas = _engine.list_entities("users")
    users = []
    for meta in metas:
        user = get_user(meta["entity_id"])
        if user:
            users.append(user)
    return users


def update_user_stats(user_id: str, bounties: int = 0, earnings: float = 0.0):
    """Update user statistics via append."""
    entity = _engine.read_entity("users", user_id)
    if not entity or not entity.get("latest"):
        return

    latest = entity["latest"]
    _engine.append_record("users", user_id, {
        "name": latest.get("name", ""),
        "email": latest.get("email"),
        "role": latest.get("role", "hunter"),
        "total_bounties": latest.get("total_bounties", 0) + bounties,
        "total_earnings": latest.get("total_earnings", 0.0) + earnings,
        "created_at": latest.get("created_at", ""),
        "last_active": datetime.now(timezone.utc).isoformat(),
    })


# =============================================================================
# TARGET OPERATIONS
# =============================================================================

def create_target(
    program_name: str, scope: str = None, link: str = None,
    platform_name: str = "hackerone", payout_tier: str = "medium"
) -> Dict[str, Any]:
    """Create a new target."""
    target_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()

    data = {
        "program_name": program_name,
        "scope": scope,
        "link": link,
        "platform": platform_name,
        "payout_tier": payout_tier,
        "status": "active",
        "created_at": now,
    }

    _engine.create_entity("targets", target_id, data)
    return {"id": target_id, **data}


def get_all_targets() -> List[Dict[str, Any]]:
    """Get all targets."""
    metas = _engine.list_entities("targets")
    targets = []
    for meta in metas:
        entity = _engine.read_entity("targets", meta["entity_id"])
        if entity and entity.get("latest"):
            latest = entity["latest"]
            targets.append({
                "id": meta["entity_id"],
                "program_name": latest.get("program_name", ""),
                "scope": latest.get("scope"),
                "link": latest.get("link"),
                "platform": latest.get("platform", "hackerone"),
                "payout_tier": latest.get("payout_tier", "medium"),
                "status": latest.get("status", "active"),
                "created_at": latest.get("created_at", ""),
            })
    return targets


def get_target(target_id: str) -> Optional[Dict[str, Any]]:
    """Get a target by ID."""
    entity = _engine.read_entity("targets", target_id)
    if not entity or not entity.get("latest"):
        return None
    latest = entity["latest"]
    return {
        "id": target_id,
        "program_name": latest.get("program_name", ""),
        "scope": latest.get("scope"),
        "link": latest.get("link"),
        "platform": latest.get("platform", "hackerone"),
        "payout_tier": latest.get("payout_tier", "medium"),
        "status": latest.get("status", "active"),
        "created_at": latest.get("created_at", ""),
    }


# =============================================================================
# BOUNTY OPERATIONS
# =============================================================================

def create_bounty(
    user_id: str, target_id: str = None, title: str = "",
    description: str = "", severity: str = "medium"
) -> Dict[str, Any]:
    """Create a new bounty submission."""
    bounty_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()

    # Get user name for display
    user = get_user(user_id)
    user_name = user["name"] if user else "Unknown"

    data = {
        "user_id": user_id,
        "user_name": user_name,
        "target_id": target_id,
        "title": title,
        "description": description,
        "severity": severity,
        "status": "pending",
        "reward": 0.0,
        "submitted_at": now,
    }

    _engine.create_entity("reports", bounty_id, data)
    update_user_stats(user_id, bounties=1)

    return {"id": bounty_id, **data}


def get_all_bounties() -> List[Dict[str, Any]]:
    """Get all bounties."""
    metas = _engine.list_entities("reports")
    bounties = []
    for meta in metas:
        entity = _engine.read_entity("reports", meta["entity_id"])
        if entity and entity.get("latest"):
            latest = entity["latest"]
            bounties.append({
                "id": meta["entity_id"],
                "user_id": latest.get("user_id", ""),
                "user_name": latest.get("user_name", ""),
                "target_id": latest.get("target_id"),
                "title": latest.get("title", ""),
                "description": latest.get("description", ""),
                "severity": latest.get("severity", "medium"),
                "status": latest.get("status", "pending"),
                "reward": latest.get("reward", 0.0),
                "submitted_at": latest.get("submitted_at", ""),
            })
    return bounties


def update_bounty_status(bounty_id: str, status: str, reward: float = None):
    """Update bounty status via append."""
    entity = _engine.read_entity("reports", bounty_id)
    if not entity or not entity.get("latest"):
        return

    latest = entity["latest"]
    update = {**latest, "status": status}
    if reward is not None:
        update["reward"] = reward
    _engine.append_record("reports", bounty_id, update)


# =============================================================================
# SESSION OPERATIONS
# =============================================================================

def create_session(
    user_id: str, mode: str = "READ_ONLY",
    target_scope: str = None, ip_address: str = None,
    user_agent: str = None, device_hash: str = None
) -> Dict[str, Any]:
    """Create a new session."""
    session_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()

    data = {
        "user_id": user_id,
        "mode": mode,
        "target_scope": target_scope,
        "progress": 0.0,
        "status": "active",
        "ip_address": ip_address,
        "user_agent": user_agent,
        "device_hash": device_hash,
        "started_at": now,
    }

    _engine.create_entity("sessions", session_id, data)
    return {"id": session_id, **data}


def get_active_sessions() -> List[Dict[str, Any]]:
    """Get all active sessions."""
    metas = _engine.list_entities("sessions", limit=1000)
    active = []
    for meta in metas:
        entity = _engine.read_entity("sessions", meta["entity_id"])
        if entity and entity.get("latest"):
            latest = entity["latest"]
            if latest.get("status") == "active":
                user = get_user(latest.get("user_id", ""))
                active.append({
                    "id": meta["entity_id"],
                    "user_name": user["name"] if user else "",
                    **latest,
                })
    return active


def end_session(session_id: str):
    """End a session."""
    entity = _engine.read_entity("sessions", session_id)
    if entity and entity.get("latest"):
        latest = entity["latest"]
        _engine.append_record("sessions", session_id, {
            **latest,
            "status": "ended",
            "ended_at": datetime.now(timezone.utc).isoformat(),
        })


# =============================================================================
# DEVICE OPERATIONS
# =============================================================================

def register_device(
    user_id: str, device_hash: str, ip_address: str = None,
    user_agent: str = None, location: str = None
) -> Dict[str, Any]:
    """Register a device."""
    device_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()

    data = {
        "user_id": user_id,
        "device_hash": device_hash,
        "ip_address": ip_address,
        "user_agent": user_agent,
        "location": location,
        "first_seen": now,
        "last_seen": now,
        "is_trusted": 0,
        "is_new": True,
    }

    _engine.create_entity("devices", device_id, data)
    return {"id": device_id, **data}


# =============================================================================
# AUTH-RELATED USER OPERATIONS
# =============================================================================

def get_user_by_email(email: str) -> Optional[Dict[str, Any]]:
    """Find a user by email address."""
    metas = _engine.list_entities("users", limit=10000)
    for meta in metas:
        entity = _engine.read_entity("users", meta["entity_id"])
        if entity and entity.get("latest"):
            latest = entity["latest"]
            if latest.get("email") == email:
                return {
                    "id": meta["entity_id"],
                    "name": latest.get("name", ""),
                    "email": latest.get("email"),
                    "role": latest.get("role", "hunter"),
                    "password_hash": latest.get("password_hash"),
                    "total_bounties": latest.get("total_bounties", 0),
                    "total_earnings": latest.get("total_earnings", 0.0),
                    "created_at": latest.get("created_at", ""),
                    "last_active": latest.get("last_active", ""),
                }
    return None


def update_user_password(user_id: str, password_hash: str):
    """Update user password hash via append."""
    entity = _engine.read_entity("users", user_id)
    if not entity or not entity.get("latest"):
        return
    latest = entity["latest"]
    _engine.append_record("users", user_id, {
        **latest,
        "password_hash": password_hash,
    })


def get_user_bounties(user_id: str) -> List[Dict[str, Any]]:
    """Get all bounties for a specific user."""
    all_bounties = get_all_bounties()
    return [b for b in all_bounties if b.get("user_id") == user_id]


def get_user_sessions(user_id: str) -> List[Dict[str, Any]]:
    """Get all sessions for a specific user."""
    metas = _engine.list_entities("sessions", limit=1000)
    sessions = []
    for meta in metas:
        entity = _engine.read_entity("sessions", meta["entity_id"])
        if entity and entity.get("latest"):
            latest = entity["latest"]
            if latest.get("user_id") == user_id:
                sessions.append({"id": meta["entity_id"], **latest})
    return sessions


def update_session_progress(session_id: str, progress: float):
    """Update session progress."""
    entity = _engine.read_entity("sessions", session_id)
    if entity and entity.get("latest"):
        _engine.append_record("sessions", session_id, {
            **entity["latest"],
            "progress": progress,
        })


def get_user_devices(user_id: str) -> List[Dict[str, Any]]:
    """Get all devices for a user."""
    metas = _engine.list_entities("devices", limit=1000)
    devices = []
    for meta in metas:
        entity = _engine.read_entity("devices", meta["entity_id"])
        if entity and entity.get("latest"):
            latest = entity["latest"]
            if latest.get("user_id") == user_id:
                devices.append({"id": meta["entity_id"], **latest})
    return devices


def get_all_active_devices() -> List[Dict[str, Any]]:
    """Get all devices (all are 'active' since we don't deactivate)."""
    metas = _engine.list_entities("devices", limit=1000)
    devices = []
    for meta in metas:
        entity = _engine.read_entity("devices", meta["entity_id"])
        if entity and entity.get("latest"):
            latest = entity["latest"]
            devices.append({"id": meta["entity_id"], **latest})
    return devices


def get_active_device_count(user_id: str) -> int:
    """Count active devices for a user."""
    return len(get_user_devices(user_id))


# =============================================================================
# AUDIT OPERATIONS
# =============================================================================

def log_activity(
    user_id: str = None, action_type: str = "",
    description: str = "", ip_address: str = None,
    metadata: dict = None
) -> Dict[str, Any]:
    """Log an activity to the audit trail."""
    log_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()

    data = {
        "user_id": user_id,
        "action_type": action_type,
        "description": description,
        "ip_address": ip_address,
        "metadata_json": metadata,
        "created_at": now,
    }

    _engine.create_entity("audit", log_id, data)
    return {"id": log_id, "action_type": action_type, "created_at": now}


def get_recent_activity(limit: int = 50) -> List[Dict[str, Any]]:
    """Get recent activity."""
    metas = _engine.list_entities("audit", limit=limit)
    activities = []
    for meta in metas:
        entity = _engine.read_entity("audit", meta["entity_id"])
        if entity and entity.get("latest"):
            latest = entity["latest"]
            activities.append({
                "id": meta["entity_id"],
                "user_id": latest.get("user_id"),
                "action_type": latest.get("action_type", ""),
                "description": latest.get("description", ""),
                "ip_address": latest.get("ip_address"),
                "metadata_json": latest.get("metadata_json"),
                "created_at": latest.get("created_at", ""),
            })
    return activities


# =============================================================================
# TRAINING RUN OPERATIONS
# =============================================================================

def create_training_run(epochs: int = 0, gpu_used: bool = False,
                        dataset_size: int = 0) -> Dict[str, Any]:
    """Record a training run."""
    run_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()

    data = {
        "started_at": now,
        "epochs": epochs,
        "gpu_used": gpu_used,
        "dataset_size": dataset_size,
    }

    _engine.create_entity("training", run_id, data)
    return {"id": run_id, **data}


def complete_training_run(run_id: str, final_loss: float = None,
                          final_accuracy: float = None,
                          checkpoint_path: str = None):
    """Complete a training run."""
    entity = _engine.read_entity("training", run_id)
    if entity and entity.get("latest"):
        _engine.append_record("training", run_id, {
            **entity["latest"],
            "ended_at": datetime.now(timezone.utc).isoformat(),
            "final_loss": final_loss,
            "final_accuracy": final_accuracy,
            "checkpoint_path": checkpoint_path,
        })


def get_training_runs(limit: int = 20) -> List[Dict[str, Any]]:
    """Get recent training runs."""
    metas = _engine.list_entities("training", limit=limit)
    runs = []
    for meta in metas:
        entity = _engine.read_entity("training", meta["entity_id"])
        if entity and entity.get("latest"):
            runs.append({"id": meta["entity_id"], **entity["latest"]})
    return runs


# =============================================================================
# ADMIN STATS
# =============================================================================

def get_admin_stats() -> Dict[str, Any]:
    """Get admin dashboard statistics from HDD storage."""
    return {
        "total_users": _engine.count_entities("users"),
        "total_targets": _engine.count_entities("targets"),
        "total_bounties": _engine.count_entities("reports"),
        "active_sessions": len(get_active_sessions()),
        "activity_24h": _engine.count_entities("audit"),
    }


# =============================================================================
# STORAGE / LIFECYCLE / MONITORING ENDPOINTS
# =============================================================================

def get_storage_stats() -> Dict[str, Any]:
    """Get storage engine statistics."""
    return _engine.get_stats()


def get_lifecycle_status() -> Dict[str, Any]:
    """Get lifecycle status and deletion preview."""
    preview = _lifecycle.get_deletion_preview() if _lifecycle else []
    return {
        "deletion_preview": preview,
        "eligible_count": sum(1 for p in preview if p["would_delete"]),
    }


def get_disk_status() -> Dict[str, Any]:
    """Get disk monitor status."""
    if _disk_monitor:
        return {
            "status": _disk_monitor.get_disk_status(),
            "breakdown": _disk_monitor.get_storage_breakdown(),
            "index_health": _disk_monitor.check_index_health(),
            "alerts": _disk_monitor.get_alerts(),
        }
    return {"status": "not_initialized"}


def get_delete_preview(entity_type: str = None) -> List[Dict[str, Any]]:
    """Preview which entities would be deleted."""
    if _lifecycle:
        return _lifecycle.get_deletion_preview(entity_type)
    return []


# =============================================================================
# VIDEO BRIDGE
# =============================================================================

def store_video(user_id: str, session_id: str, data: bytes, filename: str = "video.webm"):
    """Store a video."""
    if _video_streamer:
        return _video_streamer.store_video(user_id, session_id, data, filename)
    return {"success": False, "reason": "Video streamer not initialized"}


def get_video_stream_token(user_id: str, session_id: str, filename: str = "video.webm"):
    """Get a signed streaming token."""
    if _video_streamer:
        token = _video_streamer.generate_stream_token(user_id, session_id, filename)
        return {"token": token} if token else {"error": "Video not found"}
    return {"error": "Not initialized"}


def stream_video(token: str, range_start: int = 0, range_end: int = None):
    """Stream a video using a signed token."""
    if _video_streamer:
        return _video_streamer.stream_video(token, range_start, range_end)
    return None


def list_videos(user_id: str = None):
    """List videos."""
    if _video_streamer:
        return _video_streamer.list_videos(user_id)
    return []
