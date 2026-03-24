from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from backend.auth.auth_guard import require_admin, require_auth

from api.schemas.storage import (
    CreateBountyRequest,
    CreateSessionRequest,
    CreateTargetRequest,
    CreateUserRequest,
    UpdateBountyRequest,
)
from api.services import storage_service


def build_storage_router() -> APIRouter:
    router = APIRouter(tags=["storage"])

    @router.get("/api/db/users")
    def list_users(limit: int = 100, offset: int = 0, user=Depends(require_admin)):
        try:
            return storage_service.list_users(limit, offset)
        except Exception as exc:
            raise HTTPException(status_code=500, detail="Failed to list users") from exc

    @router.post("/api/db/users")
    def add_user(request: CreateUserRequest, admin_user=Depends(require_admin)):
        try:
            return storage_service.add_user(request)
        except Exception as exc:
            raise HTTPException(
                status_code=400, detail="Failed to create user"
            ) from exc

    @router.get("/api/db/users/{user_id}")
    def get_single_user(user_id: str, user=Depends(require_admin)):
        try:
            return storage_service.get_single_user(user_id)
        except Exception as exc:
            raise HTTPException(status_code=400, detail="Failed to fetch user") from exc

    @router.get("/api/db/users/{user_id}/bounties")
    def get_user_bounties_endpoint(user_id: str, user=Depends(require_admin)):
        try:
            return storage_service.list_user_bounties(user_id)
        except Exception:
            return {"bounties": [], "total": 0, "error": "Internal error"}

    @router.get("/api/db/targets")
    def list_targets(limit: int = 100, offset: int = 0, user=Depends(require_auth)):
        try:
            return storage_service.list_targets(limit, offset)
        except Exception:
            return {"targets": [], "total": 0, "error": "Internal error"}

    @router.post("/api/db/targets")
    def add_target(request: CreateTargetRequest, user=Depends(require_admin)):
        try:
            return storage_service.add_target(request)
        except Exception as exc:
            raise HTTPException(
                status_code=400, detail="Failed to create target"
            ) from exc

    @router.get("/api/db/bounties")
    def list_bounties(limit: int = 100, offset: int = 0, user=Depends(require_auth)):
        try:
            return storage_service.list_bounties(limit, offset)
        except Exception:
            return {"bounties": [], "total": 0, "error": "Internal error"}

    @router.post("/api/db/bounties")
    def add_bounty(request: CreateBountyRequest, user=Depends(require_admin)):
        try:
            return storage_service.add_bounty(request)
        except Exception as exc:
            raise HTTPException(
                status_code=400, detail="Failed to create bounty"
            ) from exc

    @router.put("/api/db/bounties")
    def update_bounty(request: UpdateBountyRequest, user=Depends(require_admin)):
        try:
            return storage_service.update_bounty(request)
        except Exception as exc:
            raise HTTPException(
                status_code=400, detail="Failed to update bounty"
            ) from exc

    @router.post("/api/db/sessions")
    def add_session(request: CreateSessionRequest, user=Depends(require_admin)):
        try:
            return storage_service.add_session(request)
        except Exception as exc:
            raise HTTPException(
                status_code=400, detail="Failed to create session"
            ) from exc

    @router.get("/api/db/activity")
    def list_activity(limit: int = 50, offset: int = 0, user=Depends(require_admin)):
        try:
            return storage_service.list_activity(limit, offset)
        except Exception:
            return {"activities": [], "total": 0, "error": "Internal error"}

    @router.get("/api/db/admin/stats")
    def get_admin_statistics(user=Depends(require_admin)):
        try:
            return storage_service.get_admin_statistics()
        except Exception:
            return {"success": False, "stats": None, "error": "Internal error"}

    return router
