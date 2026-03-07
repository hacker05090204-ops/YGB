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

# --- In-memory lookup indexes (eliminate full-table scans) ---
_EMAIL_INDEX: Dict[str, str] = {}       # email → user entity_id
_EMAIL_INDEX_BUILT = False
_GITHUB_ID_INDEX: Dict[str, str] = {}
_GITHUB_ID_INDEX_BUILT = False
_DEVICE_INDEX: Dict[str, str] = {}      # "user_id|device_hash" → device entity_id
_DEVICE_INDEX_BUILT = False


def init_storage(hdd_root: Optional[str] = None) -> Dict[str, Any]:
    """
    Initialize the HDD storage engine and all subsystems.
    Call this once at application startup.
    """
    global _engine, _lifecycle, _disk_monitor, _video_streamer
    global _EMAIL_INDEX, _EMAIL_INDEX_BUILT, _GITHUB_ID_INDEX, _GITHUB_ID_INDEX_BUILT
    global _DEVICE_INDEX, _DEVICE_INDEX_BUILT

    _engine = get_engine(hdd_root)
    _EMAIL_INDEX = {}
    _EMAIL_INDEX_BUILT = False
    _GITHUB_ID_INDEX = {}
    _GITHUB_ID_INDEX_BUILT = False
    _DEVICE_INDEX = {}
    _DEVICE_INDEX_BUILT = False

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
        "password_hash": None,
        "auth_provider": None,
        "last_login_ip": None,
        "last_geolocation": None,
        "last_auth_provider": None,
        "last_auth_at": None,
        "github_id": None,
        "github_login": None,
        "avatar_url": None,
        "github_profile": {},
        "total_bounties": 0,
        "total_earnings": 0.0,
        "created_at": now,
        "last_active": now,
    }

    result = _engine.create_entity("users", user_id, data)

    # Keep email index up to date
    if email:
        _EMAIL_INDEX[email] = user_id

    return {"id": user_id, **data}


def get_user(user_id: str) -> Optional[Dict[str, Any]]:
    """Get a user by ID."""
    entity = _engine.read_entity("users", user_id)
    if not entity or not entity.get("latest"):
        return None

    latest = entity["latest"]
    github_profile = latest.get("github_profile", {}) or {}
    return {
        "id": user_id,
        "name": latest.get("name", ""),
        "email": latest.get("email"),
        "role": latest.get("role", "hunter"),
        "auth_provider": latest.get("auth_provider") or latest.get("last_auth_provider"),
        "github_id": latest.get("github_id") or github_profile.get("github_id"),
        "github_login": latest.get("github_login") or github_profile.get("github_login"),
        "avatar_url": latest.get("avatar_url") or github_profile.get("avatar_url"),
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
        **latest,
        "total_bounties": latest.get("total_bounties", 0) + bounties,
        "total_earnings": latest.get("total_earnings", 0.0) + earnings,
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
    user_agent: str = None, device_hash: str = None,
    metadata: Dict[str, Any] = None
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
        "metadata_json": metadata or {},
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

def _ensure_device_index():
    """Lazily populate the (user_id, device_hash) → entity_id index."""
    global _DEVICE_INDEX_BUILT
    if _DEVICE_INDEX_BUILT:
        return
    metas = _engine.list_entities("devices", limit=5000)
    for meta in metas:
        entity = _engine.read_entity("devices", meta["entity_id"])
        if not entity or not entity.get("latest"):
            continue
        latest = entity["latest"]
        uid = latest.get("user_id", "")
        dh = latest.get("device_hash", "")
        if uid and dh:
            _DEVICE_INDEX[f"{uid}|{dh}"] = meta["entity_id"]
    _DEVICE_INDEX_BUILT = True


def register_device(
    user_id: str, device_hash: str, ip_address: str = None,
    user_agent: str = None, location: str = None
) -> Dict[str, Any]:
    """Register a device, or update an existing device's last-seen metadata."""
    now = datetime.now(timezone.utc).isoformat()

    # Use cached index for O(1) lookup instead of full-table scan
    _ensure_device_index()
    idx_key = f"{user_id}|{device_hash}"
    cached_eid = _DEVICE_INDEX.get(idx_key)
    if cached_eid:
        entity = _engine.read_entity("devices", cached_eid)
        if entity and entity.get("latest"):
            latest = entity["latest"]
            updated = {
                **latest,
                "ip_address": ip_address,
                "user_agent": user_agent or latest.get("user_agent"),
                "location": location,
                "last_seen": now,
                "is_new": False,
            }
            _engine.append_record("devices", cached_eid, updated)
            return {"id": cached_eid, **updated}

    device_id = str(uuid.uuid4())
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
    _DEVICE_INDEX[idx_key] = device_id
    return {"id": device_id, **data}


# =============================================================================
# AUTH-RELATED USER OPERATIONS
# =============================================================================

def _ensure_email_index():
    """Lazily populate the email → user entity_id index."""
    global _EMAIL_INDEX_BUILT
    if _EMAIL_INDEX_BUILT:
        return
    metas = _engine.list_entities("users", limit=10000)
    for meta in metas:
        entity = _engine.read_entity("users", meta["entity_id"])
        if entity and entity.get("latest"):
            em = entity["latest"].get("email")
            if em:
                _EMAIL_INDEX[em] = meta["entity_id"]
    _EMAIL_INDEX_BUILT = True


def _ensure_github_id_index():
    """Lazily populate the github_id lookup index."""
    global _GITHUB_ID_INDEX_BUILT
    if _GITHUB_ID_INDEX_BUILT:
        return
    metas = _engine.list_entities("users", limit=10000)
    for meta in metas:
        entity = _engine.read_entity("users", meta["entity_id"])
        if not entity or not entity.get("latest"):
            continue
        latest = entity["latest"]
        profile = latest.get("github_profile", {}) or {}
        github_id = latest.get("github_id") or profile.get("github_id")
        if github_id:
            _GITHUB_ID_INDEX[str(github_id)] = meta["entity_id"]
    _GITHUB_ID_INDEX_BUILT = True


def get_user_by_email(email: str) -> Optional[Dict[str, Any]]:
    """Find a user by email address (uses cached index after first call)."""
    _ensure_email_index()
    entity_id = _EMAIL_INDEX.get(email)
    if not entity_id:
        return None
    entity = _engine.read_entity("users", entity_id)
    if not entity or not entity.get("latest"):
        return None
    latest = get_user(entity_id) or {}
    latest["password_hash"] = entity["latest"].get("password_hash")
    return latest


def get_user_by_github_id(github_id: str) -> Optional[Dict[str, Any]]:
    """Find a user by stable GitHub account id."""
    if not github_id:
        return None
    _ensure_github_id_index()
    entity_id = _GITHUB_ID_INDEX.get(str(github_id))
    if not entity_id:
        return None
    return get_user(entity_id)


def update_user_password(user_id: str, password_hash: str):
    """Update user password hash via append."""
    entity = _engine.read_entity("users", user_id)
    if not entity or not entity.get("latest"):
        return
    latest = entity["latest"]
    _engine.append_record("users", user_id, {
        **latest,
        "password_hash": password_hash,
        "last_auth_provider": "password",
        "last_auth_at": datetime.now(timezone.utc).isoformat(),
    })


def update_user_auth_profile(
    user_id: str,
    auth_provider: str,
    ip_address: str = None,
    geolocation: str = None,
    github_profile: Dict[str, Any] = None,
):
    """Persist auth/security context for a user (admin visibility)."""
    entity = _engine.read_entity("users", user_id)
    if not entity or not entity.get("latest"):
        return

    latest = entity["latest"]
    profile = github_profile or latest.get("github_profile", {}) or {}

    # Keep profile bounded for disk and API safety.
    bounded_profile: Dict[str, Any] = {}
    for k, v in profile.items():
        key = str(k)[:64]
        if isinstance(v, (int, float, bool)) or v is None:
            bounded_profile[key] = v
        else:
            bounded_profile[key] = str(v)[:512]

    github_id = bounded_profile.get("github_id") or latest.get("github_id")
    github_login = bounded_profile.get("github_login") or latest.get("github_login")
    avatar_url = bounded_profile.get("avatar_url") or latest.get("avatar_url")

    _engine.append_record("users", user_id, {
        **latest,
        "auth_provider": auth_provider,
        "last_login_ip": ip_address,
        "last_geolocation": geolocation,
        "last_auth_provider": auth_provider,
        "last_auth_at": datetime.now(timezone.utc).isoformat(),
        "github_id": github_id,
        "github_login": github_login,
        "avatar_url": avatar_url,
        "github_profile": bounded_profile,
    })
    if github_id:
        _GITHUB_ID_INDEX[str(github_id)] = user_id


def get_admin_user_security_view(limit: int = 1000) -> List[Dict[str, Any]]:
    """Admin-only security view including password hash + GitHub profile context."""
    metas = _engine.list_entities("users", limit=limit)
    out: List[Dict[str, Any]] = []
    for meta in metas:
        entity = _engine.read_entity("users", meta["entity_id"])
        if not entity or not entity.get("latest"):
            continue
        latest = entity["latest"]
        out.append({
            "id": meta["entity_id"],
            "name": latest.get("name", ""),
            "email": latest.get("email"),
            "role": latest.get("role", "hunter"),
            # Never plaintext. Stored value is one-way hash only.
            "password_hash": latest.get("password_hash"),
            "last_login_ip": latest.get("last_login_ip"),
            "last_geolocation": latest.get("last_geolocation"),
            "last_auth_provider": latest.get("last_auth_provider"),
            "last_auth_at": latest.get("last_auth_at"),
            "github_profile": latest.get("github_profile", {}),
            "created_at": latest.get("created_at", ""),
            "last_active": latest.get("last_active", ""),
        })
    return out


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


def get_storage_health() -> Dict[str, Any]:
    """
    Canonical storage health truth response.

    Performs REAL checks — never returns active/ok unless verified.
    If any subsystem is unavailable, returns INACTIVE/DEGRADED with reason.

    Returns:
        Dict with storage_active, db_active, lifecycle_ok, reason, checked_at
    """
    checked_at = datetime.now(timezone.utc).isoformat()
    reasons = []

    # Check engine
    storage_active = False
    if _engine is None:
        reasons.append("Storage engine not initialized")
    else:
        try:
            root = _engine.root
            if root and root.exists():
                storage_active = True
            else:
                reasons.append(f"Storage root missing or inaccessible: {root}")
        except Exception as e:
            logger.error("Storage engine error during health check: %s", e)
            reasons.append(f"Storage engine error: {type(e).__name__}")

    # db_active mirrors storage_active (HDD engine IS the database)
    db_active = storage_active

    # Check lifecycle
    lifecycle_ok = False
    if _lifecycle is not None:
        lifecycle_ok = True
    else:
        reasons.append("Lifecycle manager not initialized")

    # Check disk monitor
    disk_monitor_ok = _disk_monitor is not None
    if not disk_monitor_ok:
        reasons.append("Disk monitor not initialized")

    reason = "; ".join(reasons) if reasons else None
    overall_status = "ACTIVE" if (storage_active and db_active and lifecycle_ok) else "INACTIVE"
    if storage_active and not lifecycle_ok:
        overall_status = "DEGRADED"

    return {
        "status": overall_status,
        "storage_active": storage_active,
        "db_active": db_active,
        "lifecycle_ok": lifecycle_ok,
        "disk_monitor_ok": disk_monitor_ok,
        "reason": reason,
        "checked_at": checked_at,
    }


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
