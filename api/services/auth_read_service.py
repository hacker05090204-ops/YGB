"""Read-oriented auth services.

These helpers keep `server.py` thin for auth status/profile/session reads while
preserving the existing route contracts.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any, Callable, Dict

from fastapi import HTTPException, Response


def build_auth_provider_status(
    *,
    allow_password_login: bool,
    temporary_bypass_enabled: bool,
    temporary_auth_user: Callable[[], Dict[str, Any]],
    get_github_oauth_config: Callable[[], Dict[str, Any]],
    get_google_oauth_config: Callable[[], Dict[str, Any]],
    shared_oauth_candidate_files: Callable[[str], list],
    response: Response | None = None,
) -> Dict[str, Any]:
    github_cfg = get_github_oauth_config()
    google_cfg = get_google_oauth_config()
    if response is not None:
        response.headers["Cache-Control"] = "no-store"
    return {
        "password": {"enabled": allow_password_login},
        "temporary_bypass": {
            "enabled": temporary_bypass_enabled,
            "role": temporary_auth_user().get("role", "admin"),
        },
        "github": {
            "enabled": not github_cfg["missing"],
            "missing": github_cfg["missing"],
            "redirect_uri": github_cfg["redirect_uri"],
            "frontend_url": github_cfg["frontend_url"],
            "shared_candidates": [
                str(path) for path in shared_oauth_candidate_files("github")
            ],
        },
        "google": {
            "enabled": not google_cfg["missing"],
            "missing": google_cfg["missing"],
            "redirect_uri": google_cfg["redirect_uri"],
            "frontend_url": google_cfg["frontend_url"],
            "shared_candidates": [
                str(path) for path in shared_oauth_candidate_files("google")
            ],
        },
        "checked_at": datetime.now(UTC).isoformat(),
    }


def build_auth_profile_payload(
    *,
    user: Dict[str, Any],
    temporary_bypass_payload: Callable[[Dict[str, Any]], Dict[str, Any]],
    get_user: Callable[[str], Dict[str, Any] | None],
    get_user_devices: Callable[[str], list],
    get_recent_activity: Callable[..., list],
) -> Dict[str, Any]:
    if user.get("_temporary_bypass"):
        return temporary_bypass_payload(user)

    user_id = user.get("sub", "")
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid auth token payload")

    record = get_user(user_id)
    if not record:
        raise HTTPException(status_code=404, detail="User not found")

    base = {
        "success": True,
        "user": {
            "id": record["id"],
            "name": record.get("name", ""),
            "email": record.get("email"),
            "phone_number": record.get("phone_number"),
            "role": record.get("role", "hunter"),
        },
        "session_id": user.get("session_id"),
    }
    if record.get("role", "").lower() != "admin":
        return base

    devices = get_user_devices(user_id)
    latest_device = (
        max(devices, key=lambda d: d.get("last_seen", "")) if devices else None
    )
    github_profile = None
    for evt in get_recent_activity(limit=200):
        if evt.get("user_id") != user_id:
            continue
        if evt.get("action_type") != "LOGIN_SUCCESS_GITHUB":
            continue
        metadata = evt.get("metadata_json") or {}
        if isinstance(metadata, dict) and metadata.get("github_profile"):
            github_profile = metadata.get("github_profile")
            break

    return {
        **base,
        "network": {
            "ip_address": latest_device.get("ip_address") if latest_device else None,
            "geolocation": latest_device.get("location") if latest_device else None,
        },
        "device": latest_device,
        "github_profile": github_profile,
    }


def build_auth_me_response(
    *,
    user: Dict[str, Any],
    temporary_bypass_payload: Callable[[Dict[str, Any]], Dict[str, Any]],
    get_user: Callable[[str], Dict[str, Any] | None],
) -> Response:
    if user.get("_temporary_bypass"):
        return Response(
            content=json.dumps(temporary_bypass_payload(user)),
            media_type="application/json",
            headers={"Cache-Control": "no-store"},
        )

    user_id = user.get("sub", "")
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid auth token payload")

    record = get_user(user_id)
    if not record:
        raise HTTPException(status_code=404, detail="User not found")

    result = {
        "user_id": record["id"],
        "name": record.get("name", ""),
        "email": record.get("email"),
        "phone_number": record.get("phone_number"),
        "role": record.get("role", "hunter"),
        "github_login": record.get("github_login"),
        "google_email": record.get("google_email"),
        "google_picture": record.get("google_picture"),
        "avatar_url": record.get("avatar_url"),
        "auth_provider": record.get("auth_provider", "email"),
        "session_id": user.get("session_id"),
        "timestamp": datetime.now(UTC).isoformat(),
    }
    return Response(
        content=json.dumps(result),
        media_type="application/json",
        headers={"Cache-Control": "no-store"},
    )
