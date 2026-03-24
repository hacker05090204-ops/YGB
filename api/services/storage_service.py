from __future__ import annotations

from backend.storage.storage_bridge import (
    create_bounty,
    create_session,
    create_target,
    create_user,
    get_admin_stats,
    get_bounties_page,
    get_recent_activity,
    get_target,
    get_targets_page,
    get_user,
    get_user_bounties,
    get_users_page,
    log_activity,
    update_bounty_status,
)

from api.schemas.storage import (
    CreateBountyRequest,
    CreateSessionRequest,
    CreateTargetRequest,
    CreateUserRequest,
    UpdateBountyRequest,
)


def list_users(limit: int, offset: int) -> dict:
    users, total = get_users_page(limit=limit, offset=offset)
    return {"users": users, "total": total, "limit": limit, "offset": offset}


def add_user(request: CreateUserRequest) -> dict:
    new_user = create_user(request.name, request.email, request.role)
    log_activity(str(new_user["id"]), "USER_CREATED", f"User {request.name} created")
    return {"success": True, "user": new_user}


def get_single_user(user_id: str) -> dict:
    user = get_user(user_id)
    if user:
        return {"success": True, "user": user}
    return {"success": False, "error": "User not found"}


def list_user_bounties(user_id: str) -> dict:
    bounties = get_user_bounties(user_id)
    return {"bounties": bounties, "total": len(bounties)}


def list_targets(limit: int, offset: int) -> dict:
    targets, total = get_targets_page(limit=limit, offset=offset)
    return {"targets": targets, "total": total, "limit": limit, "offset": offset}


def add_target(request: CreateTargetRequest) -> dict:
    target = create_target(
        request.program_name,
        request.scope,
        request.link,
        request.platform,
        request.payout_tier,
    )
    log_activity(None, "TARGET_CREATED", f"Target {request.program_name} created")
    return {"success": True, "target": target}


def list_bounties(limit: int, offset: int) -> dict:
    bounties, total = get_bounties_page(limit=limit, offset=offset)
    return {"bounties": bounties, "total": total, "limit": limit, "offset": offset}


def add_bounty(request: CreateBountyRequest) -> dict:
    bounty = create_bounty(
        request.user_id,
        request.target_id,
        request.title,
        request.description,
        request.severity,
    )
    log_activity(request.user_id, "BOUNTY_SUBMITTED", f"Bounty: {request.title}")
    return {"success": True, "bounty": bounty}


def update_bounty(request: UpdateBountyRequest) -> dict:
    update_bounty_status(request.bounty_id, request.status, request.reward)
    log_activity(
        None, "BOUNTY_UPDATED", f"Bounty {request.bounty_id} -> {request.status}"
    )
    return {"success": True, "bounty_id": request.bounty_id, "status": request.status}


def add_session(request: CreateSessionRequest) -> dict:
    session = create_session(request.user_id, request.mode, request.target_scope)
    log_activity(request.user_id, "SESSION_STARTED", f"Mode: {request.mode}")
    return {"success": True, "session": session}


def list_activity(limit: int, offset: int) -> dict:
    activities = get_recent_activity(limit, offset)
    return {
        "activities": activities,
        "total": len(activities),
        "limit": limit,
        "offset": offset,
    }


def get_admin_statistics() -> dict:
    return {"success": True, "stats": get_admin_stats()}
